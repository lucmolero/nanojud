"""Leitor conservador do detalhe público legado de 2º grau do TJMG."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .exceptions import (
    AcessoRestrito,
    ConsultaIndisponivel,
    DocumentoNaoEncontrado,
    ProcessoNaoEncontrado,
    URLInvalida,
)
from .utils import classificar_polo, limpar, normalizar_chave, validar_numero_cnj, validar_timeout
from .version import __version__

HOST = "www4.tjmg.jus.br"
DETAIL_URL = (
    "https://www4.tjmg.jus.br/juridico/sf/proc_movimentacoes2.jsp?listaProcessos={identificador}"
)
DETAIL_ENDPOINTS = {
    "movimentacoes": f"https://{HOST}/juridico/sf/proc_movimentacoes2.jsp",
    "complemento": f"https://{HOST}/juridico/sf/proc_complemento2.jsp",
    "partes": f"https://{HOST}/juridico/sf/proc_partes_advogados2.jsp",
}
DOCUMENT_ENDPOINT = f"https://{HOST}/juridico/sf/downloadPeca2"
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
_CNJ_PATTERN = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
_TJMG_NUMBER_PATTERN = re.compile(r"\b\d\.\d{4}\.\d{2}\.\d{6}-\d/\d{3}\b")
_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_RESTRICTED_MARKERS = ("captcha", "confirmação de segurança", "confirmacao de seguranca")
_NOT_FOUND_MARKERS = (
    "processo não encontrado",
    "processo nao encontrado",
    "nenhum registro encontrado",
)


def _validar_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.path not in {urlparse(item).path for item in DETAIL_ENDPOINTS.values()}
    ):
        raise URLInvalida("A URL não pertence à consulta processual oficial do TJMG.")


def _session(session: requests.Session | None) -> requests.Session:
    if session is not None:
        return session
    criada = requests.Session()
    criada.headers.update(
        {
            "User-Agent": f"Mozilla/5.0 (compatible; nanojud/{__version__})",
            "Accept": "text/html,application/xhtml+xml",
        }
    )
    return criada


def _pagina_html(
    session: requests.Session, endpoint: str, identificador: str, timeout: float
) -> BeautifulSoup:
    url = f"{endpoint}?listaProcessos={identificador}"
    _validar_url(url)
    try:
        response = session.get(url, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(
            f"Falha de comunicação com o TJMG: {type(exc).__name__}."
        ) from exc
    if response.status_code in (401, 403, 412):
        raise AcessoRestrito(f"A consulta legada do TJMG retornou HTTP {response.status_code}.")
    if response.status_code == 404:
        raise ProcessoNaoEncontrado("O TJMG não localizou o identificador na consulta legada.")
    if 300 <= response.status_code < 400:
        raise ConsultaIndisponivel("O TJMG redirecionou a consulta; o destino não foi seguido.")
    if response.status_code >= 400:
        raise ConsultaIndisponivel(
            f"A consulta legada do TJMG retornou HTTP {response.status_code}."
        )
    return BeautifulSoup(response.text, "html.parser")


def _validar_identidade_pagina(
    soup: BeautifulSoup, numero_cnj: str, identificador: str, *, exigir_grau: bool = False
) -> str:
    texto = limpar(soup.get_text(" ", strip=True))
    texto_lower = texto.casefold()
    if any(marker in texto_lower for marker in _RESTRICTED_MARKERS):
        raise AcessoRestrito("A página do TJMG exige confirmação interativa.")
    if any(marker in texto_lower for marker in _NOT_FOUND_MARKERS):
        raise ProcessoNaoEncontrado("O TJMG não retornou registro para o identificador informado.")
    if exigir_grau and "2ª instância" not in texto_lower and "segunda instância" not in texto_lower:
        raise ConsultaIndisponivel("A página do TJMG não confirmou que é um detalhe de 2º grau.")
    if numero_cnj not in set(_CNJ_PATTERN.findall(texto)):
        raise ConsultaIndisponivel("O TJMG não confirmou o CNJ consultado no detalhe público.")
    numero_tjmg = next(iter(_TJMG_NUMBER_PATTERN.findall(texto)), "")
    if not numero_tjmg:
        raise ConsultaIndisponivel("O TJMG não confirmou o número sequencial do processo.")
    if re.sub(r"\D", "", numero_tjmg) != identificador:
        raise ConsultaIndisponivel(
            "O número sequencial TJMG diverge do identificador interno informado."
        )
    return numero_tjmg


def _parse_movements(soup: BeautifulSoup) -> list[dict[str, Any]]:
    movimentos: list[dict[str, Any]] = []
    for row in soup.select("table.corpo tr"):
        cells = [limpar(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        date_index = next(
            (i for i, value in enumerate(cells) if _DATE_PATTERN.fullmatch(value)), None
        )
        if date_index is None or date_index == 0:
            continue
        movimentos.append(
            {
                "titulo": cells[0],
                "data": cells[date_index],
                "teor": " | ".join(
                    value for i, value in enumerate(cells[1:], 1) if i != date_index
                ),
            }
        )
    return movimentos


def _parse_public_documents(soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
    """Extrai somente vínculos de download explicitamente publicados na página."""
    documentos: list[dict[str, Any]] = []
    vistos: set[tuple[str, str]] = set()
    for link in soup.select("a[onclick]"):
        onclick = str(link.get("onclick", ""))
        match = re.search(
            r"(?:window\.open\s*\()?\s*['\"]([^'\"]*downloadPeca2\?[^'\"]+)['\"]",
            onclick,
            re.IGNORECASE,
        )
        if not match:
            continue
        candidate = urljoin(page_url, match.group(1).replace("&amp;", "&"))
        parsed = urlparse(candidate)
        query = parse_qs(parsed.query, strict_parsing=False)
        codigo = (query.get("codigoDocumento") or [""])[0]
        ano = (query.get("anoCriacaoDoc") or [""])[0]
        if (
            parsed.scheme != "https"
            or parsed.hostname != HOST
            or parsed.path != urlparse(DOCUMENT_ENDPOINT).path
            or not re.fullmatch(r"\d{1,20}", codigo)
            or not re.fullmatch(r"\d{4}", ano)
        ):
            continue
        chave = (codigo, ano)
        if chave in vistos:
            continue
        vistos.add(chave)
        download_url = (
            f"{DOCUMENT_ENDPOINT}?{urlencode({'codigoDocumento': codigo, 'anoCriacaoDoc': ano})}"
        )
        documentos.append(
            {
                "cd_documento": codigo,
                "titulo": limpar(link.get_text(" ", strip=True)) or "Documento processual",
                "href": download_url,
                "status_acesso": "publico_candidato",
                "metadados": {"ano_criacao_doc": ano},
            }
        )
    return documentos


def _document_bytes(response: Any, max_bytes: int) -> tuple[bytes, str]:
    status = response.status_code
    if status in (401, 403, 412):
        response.close()
        raise AcessoRestrito(f"O download TJMG retornou HTTP {status}.")
    if status == 404:
        response.close()
        raise DocumentoNaoEncontrado("O TJMG não localizou o documento vinculado.")
    if 300 <= status < 400:
        response.close()
        raise ConsultaIndisponivel("O TJMG redirecionou o documento; o destino não foi seguido.")
    if status != 200:
        response.close()
        raise ConsultaIndisponivel(f"O download TJMG retornou HTTP {status}.")
    content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
    allowed = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if content_type not in allowed:
        response.close()
        raise ConsultaIndisponivel("O TJMG não retornou um tipo de documento suportado.")
    content_length = response.headers.get("Content-Length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        response.close()
        raise ConsultaIndisponivel("O documento TJMG excede o limite de bytes configurado.")
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ConsultaIndisponivel("O documento TJMG excede o limite de bytes configurado.")
            chunks.append(chunk)
    finally:
        response.close()
    content = b"".join(chunks)
    signatures = {
        "application/pdf": content.startswith(b"%PDF"),
        "application/msword": content.startswith(bytes.fromhex("d0cf11e0a1b11ae1")),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            content.startswith(b"PK\x03\x04")
        ),
    }
    if not content or not signatures[content_type]:
        raise ConsultaIndisponivel("O arquivo TJMG não corresponde ao MIME declarado.")
    return content, content_type


def obter_documento_publico(
    numero: str,
    identificador_tjmg: str,
    cd_documento: str,
    ano_criacao_doc: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> tuple[bytes, str]:
    """Obtém em memória documento vinculado à página pública do TJMG 2G legado."""
    numero_cnj = validar_numero_cnj(numero, segmento="8", tribunal="13")
    if not isinstance(identificador_tjmg, str) or not re.fullmatch(r"\d{17}", identificador_tjmg):
        raise ValueError("identificador_tjmg deve conter 17 dígitos.")
    if not isinstance(cd_documento, str) or not re.fullmatch(r"\d{1,20}", cd_documento):
        raise ValueError("cd_documento deve conter de 1 a 20 dígitos.")
    if not isinstance(ano_criacao_doc, str) or not re.fullmatch(r"\d{4}", ano_criacao_doc):
        raise ValueError("ano_criacao_doc deve conter quatro dígitos.")
    timeout = validar_timeout(timeout)
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= MAX_DOCUMENT_BYTES
    ):
        raise ValueError(f"max_bytes deve estar entre 1 e {MAX_DOCUMENT_BYTES}.")
    cliente = _session(session)
    soup = _pagina_html(cliente, DETAIL_ENDPOINTS["movimentacoes"], identificador_tjmg, timeout)
    _validar_identidade_pagina(soup, numero_cnj, identificador_tjmg, exigir_grau=True)
    documentos = _parse_public_documents(soup, DETAIL_URL.format(identificador=identificador_tjmg))
    if not any(
        doc["cd_documento"] == cd_documento
        and doc["metadados"]["ano_criacao_doc"] == ano_criacao_doc
        for doc in documentos
    ):
        raise DocumentoNaoEncontrado(
            "O documento não está vinculado à página pública deste processo."
        )
    query = urlencode({"codigoDocumento": cd_documento, "anoCriacaoDoc": ano_criacao_doc})
    url = f"{DOCUMENT_ENDPOINT}?{query}"
    _validar_url_documento(url)
    try:
        response = cliente.get(url, timeout=timeout, allow_redirects=False, stream=True)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(
            f"Falha de comunicação com o TJMG: {type(exc).__name__}."
        ) from exc
    try:
        return _document_bytes(response, max_bytes)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(
            f"Falha de comunicação com o TJMG: {type(exc).__name__}."
        ) from exc


def _validar_url_documento(url: str) -> None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, strict_parsing=True)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.path != urlparse(DOCUMENT_ENDPOINT).path
        or set(query) != {"codigoDocumento", "anoCriacaoDoc"}
        or len(query["codigoDocumento"]) != 1
        or len(query["anoCriacaoDoc"]) != 1
        or not re.fullmatch(r"\d{1,20}", query["codigoDocumento"][0])
        or not re.fullmatch(r"\d{4}", query["anoCriacaoDoc"][0])
    ):
        raise URLInvalida("A URL não corresponde ao endpoint oficial de documentos do TJMG.")


def _parse_basic_fields(soup: BeautifulSoup) -> dict[str, str]:
    campos: dict[str, str] = {}
    for cell in soup.select("table.corpo td, table.corpo th"):
        texto = limpar(cell.get_text(" ", strip=True))
        match = re.match(r"^([^:]{1,60}):\s*(.+)$", texto)
        if not match:
            continue
        chave = normalizar_chave(match.group(1))
        valor = limpar(match.group(2))
        if chave and valor:
            campos[chave] = valor
    return campos


def _text_without_tables(elemento: Any) -> list[str]:
    copia = BeautifulSoup(str(elemento), "html.parser")
    for tabela in copia.find_all("table"):
        tabela.decompose()
    return [
        limpar(linha) for linha in copia.get_text("\n", strip=True).splitlines() if limpar(linha)
    ]


def _lawyers_from_cell(celula: Any) -> list[str]:
    advogados: list[str] = []
    for tabela in celula.find_all("table"):
        for linha in tabela.find_all("tr"):
            if linha.find_parent("table") is not tabela:
                continue
            celulas = linha.find_all(["td", "th"], recursive=False)
            if len(celulas) < 2 or not normalizar_chave(
                celulas[0].get_text(" ", strip=True)
            ).startswith("advogado"):
                continue
            tabelas_dados = celulas[1].find_all("table")
            if tabelas_dados:
                for tabela_dados in tabelas_dados:
                    for linha_dado in tabela_dados.find_all("tr"):
                        if linha_dado.find_parent("table") is not tabela_dados:
                            continue
                        valores = [
                            limpar(c.get_text(" ", strip=True))
                            for c in linha_dado.find_all(["td", "th"], recursive=False)
                        ]
                        valor = " — ".join(item for item in valores if item)
                        if valor:
                            advogados.append(valor)
            else:
                advogados.extend(
                    valor
                    for linha_texto in celulas[1].get_text("\n", strip=True).splitlines()
                    if (valor := limpar(linha_texto))
                    and normalizar_chave(valor) not in {"advogado", "advogado s"}
                )
    return list(dict.fromkeys(advogados))


def _parse_parties(soup: BeautifulSoup) -> dict[str, list[dict[str, Any]]] | None:
    partes: list[dict[str, Any]] = []
    for tabela in soup.select("table.corpo"):
        if tabela.find_parent("table", class_="corpo") is not None:
            continue
        for linha in tabela.find_all("tr"):
            if linha.find_parent("table") is not tabela:
                continue
            celulas = linha.find_all(["td", "th"], recursive=False)
            if len(celulas) < 2:
                continue
            primeiro = limpar(celulas[0].get_text(" ", strip=True))
            if ":" not in primeiro:
                continue
            tipo = limpar(primeiro.split(":", 1)[0])
            tipo_normalizado = normalizar_chave(tipo)
            if tipo_normalizado.startswith("advogado"):
                if partes:
                    partes[-1]["advogados"].extend(_lawyers_from_cell(celulas[1]))
                continue
            if not tipo or tipo_normalizado in {"numero tjmg", "numeracao unica"}:
                continue
            nomes = [
                nome
                for nome in _text_without_tables(celulas[1])
                if not normalizar_chave(nome).startswith(("cpf", "cnpj", "advogado", "oab"))
            ]
            advogados = _lawyers_from_cell(celulas[1])
            if not nomes and not advogados:
                continue
            tipo = re.sub(r"\s*\([^)]*\)", "", tipo)
            partes.append({"tipo": tipo, "nomes": nomes, "advogados": advogados})
    if not partes:
        return None

    ativos: list[dict[str, Any]] = []
    passivos: list[dict[str, Any]] = []
    desconhecidos: list[dict[str, Any]] = []
    for parte in partes:
        polo = classificar_polo(parte["tipo"])
        (ativos if polo == "ativo" else passivos if polo == "passivo" else desconhecidos).append(
            parte
        )
    return {
        "principais": partes,
        "todas": partes,
        "polo_ativo": ativos,
        "polo_passivo": passivos,
        "polo_desconhecido": desconhecidos,
    }


def consultar_processo(
    numero: str,
    identificador_tjmg: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Lê páginas públicas legadas de TJMG 2G usando CNJ e ID interno.

    O identificador não é derivável do CNJ. A função confirma também o número
    sequencial TJMG exibido na página para evitar misturar recursos do mesmo CNJ.
    A paginação e a completude não foram comprovadas; o retorno permanece parcial.
    """
    numero_cnj = validar_numero_cnj(numero, segmento="8", tribunal="13")
    if not isinstance(identificador_tjmg, str) or not re.fullmatch(r"\d{17}", identificador_tjmg):
        raise ValueError("identificador_tjmg deve conter 17 dígitos.")
    timeout = validar_timeout(timeout)
    cliente = _session(session)
    url = DETAIL_URL.format(identificador=identificador_tjmg)
    _validar_url(url)

    detalhe = _pagina_html(cliente, DETAIL_ENDPOINTS["movimentacoes"], identificador_tjmg, timeout)
    numero_tjmg = _validar_identidade_pagina(
        detalhe, numero_cnj, identificador_tjmg, exigir_grau=True
    )
    movimentos = _parse_movements(detalhe)
    if not movimentos:
        raise ConsultaIndisponivel("O TJMG confirmou o CNJ, mas não retornou movimentos legíveis.")
    documentos = _parse_public_documents(detalhe, url)

    avisos = [
        "Consulta de detalhe legada requer identificador interno do TJMG.",
        "Paginação e completude do histórico não foram comprovadas.",
    ]
    dados_basicos: dict[str, Any] = {"numero": numero_cnj, "numero_tjmg": numero_tjmg, "url": url}
    try:
        complemento = _pagina_html(
            cliente, DETAIL_ENDPOINTS["complemento"], identificador_tjmg, timeout
        )
        _validar_identidade_pagina(complemento, numero_cnj, identificador_tjmg)
        campos = _parse_basic_fields(complemento)
        if campos:
            dados_basicos["campos_rotulados"] = campos
            for campo, chave in {
                "camara": "orgao_julgador",
                "classe": "classe",
                "assunto": "assunto",
                "relator": "relator",
                "comarca_origem": "foro",
                "vara_origem": "vara",
                "distribuicao": "distribuicao",
            }.items():
                if campos.get(campo):
                    dados_basicos[chave] = campos[campo]
    except (AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado) as exc:
        avisos.append(f"Página auxiliar de dados básicos indisponível: {exc}")

    partes = None
    try:
        pagina_partes = _pagina_html(
            cliente, DETAIL_ENDPOINTS["partes"], identificador_tjmg, timeout
        )
        _validar_identidade_pagina(pagina_partes, numero_cnj, identificador_tjmg)
        partes = _parse_parties(pagina_partes)
        if partes is None:
            avisos.append(
                "Página auxiliar confirmou a identidade, mas não apresentou partes legíveis."
            )
    except (AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado) as exc:
        avisos.append(f"Página auxiliar de partes indisponível: {exc}")

    return {
        "status": "partial",
        "origem": {
            "tribunal": "TJMG",
            "grau": "2G",
            "sistema": "consulta_legada",
            "consulta": "publica",
            "url_final": url,
            "movimentacoes_completas": False,
            "partes_completas": False,
            "documentos_completos": False,
        },
        "dados_basicos": dados_basicos,
        **({"partes": partes} if partes is not None else {}),
        "movimentacoes": movimentos,
        "movimentacoes_completas": False,
        "documentos": {"publicos_candidatos_unicos": documentos},
        "avisos": avisos,
    }
