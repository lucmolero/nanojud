"""Cliente e parser eSAJ/TJSP."""

from __future__ import annotations

import importlib
import json
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, unquote_plus, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .exceptions import (
    AcessoRestrito,
    ConsultaIndisponivel,
    DownloadIndisponivel,
    ProcessoNaoEncontrado,
    URLInvalida,
)
from .models import (
    DadosBasicos,
    Documento,
    Documentos,
    Extrato,
    Movimentacao,
    Parte,
    Partes,
    StatusAutorizacao,
)
from .normalization import normalizar_data
from .utils import (
    classificar_polo,
    limpar,
    nome_arquivo_seguro,
    normalizar_chave,
    tamanho_pdf_existente_valido,
    validar_inteiro,
    validar_numero_cnj,
    validar_timeout,
)
from .version import __version__

MovimentoDeEntrada = dict[str, Any] | Movimentacao


class ESAJSession(requests.Session):
    """Sessão HTTP e-SAJ que preserva o timeout padrão para leituras encadeadas."""

    timeout: float


ESAJ_BASE = "https://esaj.tjsp.jus.br/cpopg"
PASTA_BASE = "https://esaj.tjsp.jus.br/pastadigital/"
MOVIMENTACOES_AJAX_URL = f"{ESAJ_BASE}/carregarMovimentacoesAjax.do"
LIMITE_MOVIMENTACOES = 100
LIMITE_RESUMO = 5  # uma página: basta para a última movimentação
PAUSA_PAGINAS = 0.5
# O eSAJ recusa consultas com menos de ~1 s de intervalo, por IP (não por sessão).
INTERVALO_CONSULTAS = 1.1
ESPERA_BLOQUEIO = 1.5
TENTATIVAS_BLOQUEIO = 3
MAX_PAGINAS_MOVIMENTACOES = 1000
MAX_DOCUMENT_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_IN_MEMORY_DOCUMENT_BYTES = 8 * 1024 * 1024
RAW_HTML_DIR = Path.cwd() / "esaj_raw" / "tjsp" / "cpopg"
USER_AGENT = (
    f"Mozilla/5.0 (compatible; nanojud/{__version__}; +https://github.com/lucmolero/nanojud)"
)


def _garantir_dependencias() -> None:
    if requests is None or BeautifulSoup is None:
        raise ConsultaIndisponivel("requests/beautifulsoup4 não estão disponíveis no ambiente.")


def criar_session(timeout: float = 30.0) -> ESAJSession:
    """Cria sessão HTTP com cabeçalhos conservadores para consulta pública."""
    _garantir_dependencias()
    timeout = validar_timeout(timeout)
    session = ESAJSession()
    session.timeout = timeout
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{ESAJ_BASE}/open.do",
        }
    )
    return session


def texto_id(soup: BeautifulSoup, id_: str) -> str:
    tag = soup.find(id=id_)
    return limpar(tag.get_text(" ", strip=True)) if tag else ""


def salvar_html_bruto(html: str, numero: str, pasta: Path = RAW_HTML_DIR) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{nome_arquivo_seguro(numero)}.html"
    arquivo.write_text(html, encoding="utf-8")
    return arquivo


def montar_url_busca(numero: str) -> str:
    numero = validar_numero_cnj(numero)
    sequencial, dv_ano, foro = numero[:7], numero[8:15], numero[-4:]
    params = {
        "conversationId": "",
        "cbPesquisa": "NUMPROC",
        "numeroDigitoAnoUnificado": f"{sequencial}-{dv_ano}",
        "foroNumeroUnificado": foro,
        "dadosConsulta.valorConsultaNuUnificado": numero,
        "dadosConsulta.valorConsulta": "",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
    }
    return f"{ESAJ_BASE}/search.do?{urlencode(params)}"


def _validar_url_esaj(entrada: str, prefixos: tuple[str, ...] = ("/cpopg/",)) -> None:
    parsed = urlparse(entrada)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "esaj.tjsp.jus.br"
        or not parsed.path.startswith(prefixos)
    ):
        raise URLInvalida("URL deve ser https://esaj.tjsp.jus.br/cpopg/.")


def _get(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    if kwargs.get("timeout") is None:
        kwargs["timeout"] = getattr(session, "timeout", 30.0)
    kwargs["timeout"] = validar_timeout(kwargs["timeout"])
    try:
        response = session.get(url, **kwargs)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(
            f"Falha de comunicação com o eSAJ ({type(exc).__name__})."
        ) from exc

    status_code = getattr(response, "status_code", 0)
    if status_code in {401, 403}:
        raise AcessoRestrito(f"eSAJ retornou HTTP {status_code}.")
    if status_code == 429 or status_code >= 500:
        raise ConsultaIndisponivel(f"eSAJ retornou HTTP {status_code}.")
    if status_code == 404:
        raise ProcessoNaoEncontrado("Página de processo não encontrada no eSAJ.")
    return response


def _seguir_lista_se_preciso(
    session: requests.Session, response: requests.Response, timeout: float | None = None
) -> requests.Response:
    """Segue página de lista quando o eSAJ não redireciona direto ao detalhe."""
    soup = BeautifulSoup(response.text, "html.parser")
    if soup.find(id="numeroProcesso"):
        return response

    links = soup.select("a.linkProcesso")
    if not links:
        return response

    match_foro = re.search(r"foroNumeroUnificado=(\d+)", response.url)
    foro_pedido = match_foro.group(1).lstrip("0") if match_foro else ""
    href = ""
    for link in links:
        candidato = str(link.get("href") or "")
        match = re.search(r"processo\.foro=(\d+)", candidato)
        if foro_pedido and match and match.group(1).lstrip("0") == foro_pedido:
            href = candidato
            break
    href = href or str(links[0].get("href") or "")
    kwargs: dict[str, Any] = {"allow_redirects": True}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return _get(session, urljoin(f"{ESAJ_BASE}/", href), **kwargs)


_ritmo_lock = threading.Lock()
_ultima_consulta = 0.0


def _aguardar_ritmo() -> None:
    """Garante o intervalo mínimo entre consultas de processo em todo o processo Python."""
    global _ultima_consulta
    with _ritmo_lock:
        espera = _ultima_consulta + INTERVALO_CONSULTAS - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        _ultima_consulta = time.monotonic()


def _pagina_bloqueada(response: requests.Response) -> bool:
    """O eSAJ devolve a tela de busca com o aviso de consultas simultâneas, sem o processo."""
    return "consultas simult" in str(getattr(response, "text", "")).lower()


def carregar_pagina(
    session: requests.Session,
    entrada: str,
    timeout: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """Carrega processo por CNJ ou URL pública do eSAJ/TJSP.

    Consultas em sequência muito rápida recebem do eSAJ o aviso de "múltiplas consultas
    simultâneas" no lugar do processo; a página é tentada de novo após uma pausa, e se o
    bloqueio persistir o erro é de indisponibilidade (nunca "processo não encontrado").
    """
    for tentativa in range(TENTATIVAS_BLOQUEIO):
        response = _carregar_pagina_uma_vez(session, entrada, timeout)
        if not _pagina_bloqueada(response):
            return response
        if tentativa + 1 < TENTATIVAS_BLOQUEIO:
            sleep(ESPERA_BLOQUEIO)
    raise ConsultaIndisponivel(
        "O eSAJ recusou a consulta por múltiplas consultas simultâneas; "
        "aguarde alguns segundos e tente de novo."
    )


def _carregar_pagina_uma_vez(
    session: requests.Session, entrada: str, timeout: float | None = None
) -> requests.Response:
    if entrada.lower().startswith(("http://", "https://")):
        _validar_url_esaj(entrada)
        kwargs: dict[str, Any] = {"allow_redirects": True}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return _seguir_lista_se_preciso(session, _get(session, entrada, **kwargs), timeout=timeout)

    numero = validar_numero_cnj(entrada)
    open_kwargs: dict[str, Any] = {}
    search_kwargs: dict[str, Any] = {"allow_redirects": True}
    if timeout is not None:
        open_kwargs["timeout"] = timeout
        search_kwargs["timeout"] = timeout
    _aguardar_ritmo()
    _get(session, f"{ESAJ_BASE}/open.do", **open_kwargs)
    response = _get(session, montar_url_busca(numero), **search_kwargs)
    return _seguir_lista_se_preciso(session, response, timeout=timeout)


MSG_SEM_INFORMACOES = (
    "O eSAJ não retornou informações para este número. Pode ser processo sigiloso, "
    "de outro sistema ou número inexistente."
)


def detectar_estado_pagina(soup: BeautifulSoup, response: requests.Response) -> None:
    if texto_id(soup, "numeroProcesso"):
        return

    texto = limpar(soup.get_text(" ", strip=True)).lower()
    if soup.find(id="captcha") or "captcha" in texto:
        raise AcessoRestrito("eSAJ retornou página com captcha.")
    if "senha do processo" in texto or "liberar auto por senha" in texto:
        raise AcessoRestrito("Processo ou documento exige senha/autorização.")
    sinais_nao_encontrado = [
        "não existem informações disponíveis",
        "processo não encontrado",
        "não foi encontrado nenhum processo",
    ]
    if any(sinal in texto for sinal in sinais_nao_encontrado):
        raise ProcessoNaoEncontrado(MSG_SEM_INFORMACOES)
    if not soup.find(id="numeroProcesso"):
        raise ProcessoNaoEncontrado(MSG_SEM_INFORMACOES)


def processo_codigo(url: str) -> str:
    match = re.search(r"processo\.codigo=([^&]+)", url)
    return match.group(1) if match else ""


def extrair_campos_rotulados(container: Any) -> dict[str, str]:
    campos: dict[str, str] = {}
    if not container:
        return campos
    for label in container.find_all(class_=lambda c: c and "unj-label" in c):
        chave = normalizar_chave(label.get_text(" ", strip=True))
        if not chave:
            continue
        parent = label.find_parent()
        valor = ""
        if parent:
            partes = []
            for child in parent.children:
                if child is label:
                    continue
                texto = (
                    child.get_text(" ", strip=True) if hasattr(child, "get_text") else str(child)
                )
                texto = limpar(texto)
                if texto:
                    partes.append(texto)
            valor = limpar(" ".join(partes))
        if valor:
            campos[chave] = valor
    return campos


def _etiquetas(soup: BeautifulSoup) -> list[str]:
    """Etiquetas do cabeçalho do processo (situação, segredo de justiça, prioridades...)."""
    container = soup.find(id="containerDadosPrincipaisProcesso")
    textos = [limpar(t.get_text(" ", strip=True)) for t in (container or soup).select(".unj-tag")]
    return list(dict.fromkeys(texto for texto in textos if texto))


def extrair_dados_basicos(soup: BeautifulSoup, url_final: str) -> DadosBasicos:
    campos_rotulados: dict[str, str] = {}
    for container_id in ("containerDadosPrincipaisProcesso", "maisDetalhes"):
        campos_rotulados.update(extrair_campos_rotulados(soup.find(id=container_id)))

    dados: DadosBasicos = {
        "numero": texto_id(soup, "numeroProcesso"),
        "codigo_esaj": processo_codigo(url_final),
        "classe": texto_id(soup, "classeProcesso"),
        "assunto": texto_id(soup, "assuntoProcesso") or campos_rotulados.get("assunto", ""),
        "foro": texto_id(soup, "foroProcesso") or campos_rotulados.get("foro", ""),
        "vara": texto_id(soup, "varaProcesso") or campos_rotulados.get("vara", ""),
        "juiz": texto_id(soup, "juizProcesso") or campos_rotulados.get("juiz", ""),
        "distribuicao": texto_id(soup, "dataHoraDistribuicaoProcesso"),
        "controle": texto_id(soup, "numeroControleProcesso"),
        "area": texto_id(soup, "areaProcesso") or campos_rotulados.get("area", ""),
        "valor_acao": texto_id(soup, "valorAcaoProcesso"),
        "url": url_final,
        "campos_rotulados": campos_rotulados,
        "situacao": texto_id(soup, "labelSituacaoProcesso"),
        "etiquetas": _etiquetas(soup),
    }

    dependencia = re.search(r"Depend[êe]ncia\s*\(([^)]+)\)", dados["distribuicao"], re.I)
    if dependencia:
        dados["processo_dependencia"] = dependencia.group(1)

    outros_assuntos = []
    for label in soup.find_all(string=re.compile(r"Outros assuntos", re.I)):
        container = label.find_parent()
        if container and container.parent:
            for span in container.parent.find_all("span"):
                texto = limpar(span.get_text(" ", strip=True))
                if texto and texto.lower() != "outros assuntos":
                    outros_assuntos.append(texto)
    dados["outros_assuntos"] = sorted(set(outros_assuntos))
    return dados


def extrair_partes_tabela(tabela: Any) -> list[Parte]:
    partes: list[Parte] = []
    if not tabela:
        return partes

    tipo_atual = ""
    for row in tabela.find_all("tr"):
        label_tag = row.find("span", {"class": "label"})
        if label_tag:
            tipo_atual = limpar(label_tag.get_text(" ", strip=True))
            continue

        tipo_tag = row.find(class_=lambda c: c and "tipoDeParticipacao" in c)
        nome_tag = row.find(
            "td",
            class_=lambda c: c and ("nomeParteEAdvogado" in c or "nomeParteEAdvogados" in c),
        )
        if not nome_tag:
            continue

        tipo = limpar(tipo_tag.get_text(" ", strip=True)) if tipo_tag else tipo_atual
        linhas = [limpar(x) for x in nome_tag.get_text("\n", strip=True).splitlines()]
        linhas = [x for x in linhas if x]
        nomes: list[str] = []
        advogados: list[str] = []
        proximo_e_advogado = False
        for item in linhas:
            if re.match(r"^Advogad[oa]:", item, re.I):
                resto = limpar(re.sub(r"^Advogad[oa]:", "", item, flags=re.I))
                if resto:
                    advogados.append(resto)
                    proximo_e_advogado = False
                else:
                    proximo_e_advogado = True
                continue
            if proximo_e_advogado:
                advogados.append(item)
                proximo_e_advogado = False
            elif "OAB" in item.upper():
                advogados.append(item)
            else:
                nomes.append(item)

        if nomes or advogados or tipo:
            partes.append({"tipo": tipo, "nomes": nomes, "advogados": advogados})
    return partes


def extrair_partes(soup: BeautifulSoup) -> Partes:
    principais = extrair_partes_tabela(soup.find("table", id="tablePartesPrincipais"))
    todas = extrair_partes_tabela(soup.find("table", id="tableTodasPartes"))
    if not todas:
        tabela_todas = soup.find("table", {"class": lambda c: bool(c and "todasPartes" in c)})
        todas = extrair_partes_tabela(tabela_todas)

    todas = todas or principais  # processos pequenos só trazem a tabela de partes principais
    base_para_polos = todas
    polo_ativo: list[Parte] = []
    polo_passivo: list[Parte] = []
    polo_desconhecido: list[Parte] = []
    for parte in base_para_polos:
        polo = classificar_polo(parte.get("tipo", ""))
        if polo == "ativo":
            polo_ativo.append(parte)
        elif polo == "passivo":
            polo_passivo.append(parte)
        else:
            polo_desconhecido.append(parte)
    return {
        "principais": principais,
        "todas": todas,
        "polo_ativo": polo_ativo,
        "polo_passivo": polo_passivo,
        "polo_desconhecido": polo_desconhecido,
    }


def classificar_documento(href: str) -> Literal["publico_candidato", "restrito_por_senha", "outro"]:
    if href == "#liberarAutoPorSenha":
        return "restrito_por_senha"
    if "abrirDocumentoVinculadoMovimentacao.do" in href:
        return "publico_candidato"
    return "outro"


def extrair_sequencial_documento(link: Any) -> str:
    onclick = link.get("onclick") or ""
    match = re.search(r",\s*(\d+)\s*,\s*['\"]", onclick)
    return match.group(1) if match else ""


def extrair_cd_documento(link: Any, href: str) -> str:
    match = re.search(r"cdDocumento=(\d+)", href)
    if match:
        return match.group(1)
    id_ = link.get("id") or ""
    match = re.search(r"linkMovVincProc(?:-2)?-(\d+)", id_)
    return match.group(1) if match else ""


def titulo_documento(link: Any, href: str) -> str:
    texto = limpar(link.get_text(" ", strip=True))
    title = limpar(link.get("title", ""))
    if texto and texto.lower() != "visualizar documento em inteiro teor":
        return texto
    query = parse_qs(urlparse(href).query)
    recurso = query.get("nmRecursoAcessado", [""])[0]
    if recurso:
        return limpar(unquote_plus(recurso))
    return title or texto


def extrair_documentos_da_movimentacao(tr: Any) -> list[Documento]:
    docs: dict[str, Documento] = {}
    for link in tr.select("a.linkMovVincProc"):
        href = link.get("href") or ""
        if not href:
            continue
        cd_documento = extrair_cd_documento(link, href)
        key = cd_documento or href
        doc = docs.setdefault(
            key,
            {
                "cd_documento": cd_documento,
                "id_recurso": str(link.get("id") or ""),
                "sequencial_movimentacao": extrair_sequencial_documento(link),
                "titulo": "",
                "href": urljoin(f"{ESAJ_BASE}/", href),
                "status_acesso": classificar_documento(href),
            },
        )
        titulo = titulo_documento(link, href)
        if titulo and (
            not doc["titulo"] or doc["titulo"].lower() == "visualizar documento em inteiro teor"
        ):
            doc["titulo"] = titulo
        if not doc["sequencial_movimentacao"]:
            doc["sequencial_movimentacao"] = extrair_sequencial_documento(link)
    return list(docs.values())


def extrair_metadados_movimentacao(texto: str) -> dict[str, Any]:
    metadados: dict[str, Any] = {}
    padroes = {
        "relacao": r"Rela[çc][ãa]o\s*:?\s*([^\n]+?)(?=\s+Data|\s+Teor|\s+Advogados|$)",
        "data_disponibilizacao": r"Data da Disponibiliza[çc][ãa]o\s*:\s*(\d{2}/\d{2}/\d{4})",
        "data_publicacao": r"Data da Publica[çc][ãa]o\s*:\s*(\d{2}/\d{2}/\d{4})",
        "numero_diario": r"N[úu]mero do Di[áa]rio\s*:\s*([^\s]+)",
        "pagina_diario": r"P[áa]gina\s*:\s*([^\s]+)",
        "tipo_peticao": r"Tipo da Peti[çc][ãa]o\s*:\s*([^\n]+?)(?=\s+Data|\s+Advogados|$)",
    }
    for chave, padrao in padroes.items():
        match = re.search(padrao, texto, re.I)
        if match:
            metadados[chave] = limpar(match.group(1))
    teor = re.search(r"Teor do ato\s*:\s*(.+?)(?=\s+Advogados\(s\):|$)", texto, re.I)
    if teor:
        metadados["teor_do_ato"] = limpar(teor.group(1))
    advogados = re.search(r"Advogados\(s\):\s*(.+)$", texto, re.I)
    if advogados:
        metadados["advogados_publicacao"] = [
            limpar(item) for item in advogados.group(1).split(",") if limpar(item)
        ]
    metadados["folhas_citadas"] = sorted(
        set(re.findall(r"(?:fls?\.?|folha(?:s)?)\s*(\d+(?:/\d+)*)", texto, re.I))
    )
    return metadados


def extrair_titulo_teor_movimentacao(desc_tag: Any) -> tuple[str, str, str]:
    primeiro_link = desc_tag.find("a")
    texto_completo = limpar(desc_tag.get_text(" ", strip=True))
    if primeiro_link:
        titulo = limpar(primeiro_link.get_text(" ", strip=True))
        teor = (
            limpar(texto_completo[len(titulo) :])
            if texto_completo.startswith(titulo)
            else texto_completo
        )
        return titulo, teor, texto_completo

    partes_titulo = []
    for child in desc_tag.children:
        if getattr(child, "name", None) in {"br", "span"}:
            break
        texto = child.get_text(" ", strip=True) if hasattr(child, "get_text") else str(child)
        if limpar(texto):
            partes_titulo.append(texto)
    titulo = limpar(" ".join(partes_titulo))
    teor = (
        limpar(texto_completo[len(titulo) :])
        if titulo and texto_completo.startswith(titulo)
        else texto_completo
    )
    return titulo, teor, texto_completo


def extrair_movimentacoes(soup: BeautifulSoup) -> list[Movimentacao]:
    tabela = soup.find(["table", "tbody"], id="tabelaTodasMovimentacoes") or soup.find(
        ["table", "tbody"], id="tabelaUltimasMovimentacoes"
    )
    if not tabela:
        return []
    return _movimentos_das_linhas(tabela)


def _movimentos_das_linhas(container: Any, ordem_inicial: int = 0) -> list[Movimentacao]:
    movimentos: list[Movimentacao] = []
    linhas = container.find_all("tr", class_=lambda c: c and "containerMovimentacao" in c)
    for idx, tr in enumerate(linhas, ordem_inicial + 1):
        data_tag = tr.find("td", class_=lambda c: c and "dataMovimentacao" in c)
        desc_tag = tr.find("td", class_=lambda c: c and "descricaoMovimentacao" in c)
        if not desc_tag:
            continue
        titulo, teor, texto_completo = extrair_titulo_teor_movimentacao(desc_tag)
        movimentos.append(
            {
                "ordem": idx,
                "data": limpar(data_tag.get_text(" ", strip=True)) if data_tag else "",
                "titulo": titulo,
                "teor": teor,
                "texto": texto_completo,
                "metadados": extrair_metadados_movimentacao(texto_completo),
                "documentos": extrair_documentos_da_movimentacao(tr),
            }
        )
    return movimentos


def codigo_para_movimentacoes(html: str, url_final: str) -> str:
    """Código interno do processo usado pelo carregamento sob demanda de movimentações."""
    match = re.search(r"codigoProcesso:\s*'([^']+)'", html)
    return match.group(1) if match else processo_codigo(url_final)


def _proximo_cursor(fragmento: Any) -> str:
    linha = fragmento.find(id="trCursorMovimentacoes")
    if linha and linha.get("data-cursor"):
        return str(linha["data-cursor"])
    campo = fragmento.find(id="cursorMovimentacoesPaginado")
    return str(campo.get("value") or "") if campo else ""


def carregar_movimentacoes_ajax(
    session: requests.Session,
    codigo_processo: str,
    limite: int | None = LIMITE_MOVIMENTACOES,
    pausa: float = PAUSA_PAGINAS,
    timeout: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    desde: str = "",
    ate_documentos: set[str] | None = None,
) -> tuple[list[Movimentacao], bool, str]:
    """Pagina carregarMovimentacoesAjax.do (cursor opaco, 5 linhas por página).

    Retorna (movimentos, completo, aviso). ``limite`` vazio ou 0 busca tudo. ``desde``
    (YYYY-MM-DD) para a paginação ao chegar em movimentos mais antigos, que vêm por último.
    ``ate_documentos`` (códigos de documento) para assim que todos aparecerem nas linhas lidas.
    Falha de rede no meio devolve o que já foi coletado com ``completo=False``.
    """
    movimentos: list[Movimentacao] = []
    cursor = ""
    cursores_vistos: set[str] = set()
    for _ in range(MAX_PAGINAS_MOVIMENTACOES):
        params = {"processo.codigo": codigo_processo}
        if cursor:
            params["cursor"] = cursor
        kwargs: dict[str, Any] = {"params": params}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            response = _get(session, MOVIMENTACOES_AJAX_URL, **kwargs)
        except (ConsultaIndisponivel, AcessoRestrito, ProcessoNaoEncontrado) as exc:
            return movimentos, False, f"Movimentações incompletas: {exc}"
        fragmento = BeautifulSoup(response.text, "html.parser")
        movimentos.extend(_movimentos_das_linhas(fragmento, len(movimentos)))
        cursor = _proximo_cursor(fragmento)
        if desde and _passou_de(movimentos, desde):
            return _a_partir_de(movimentos, desde), True, ""
        if ate_documentos and ate_documentos <= _codigos_de_documentos(movimentos):
            return movimentos, True, ""
        if not cursor:
            return movimentos, True, ""
        if limite and len(movimentos) >= limite:
            aviso = f"Movimentações limitadas a {limite}; o eSAJ tem mais registros."
            return movimentos[:limite], False, aviso
        if cursor in cursores_vistos:
            break
        cursores_vistos.add(cursor)
        sleep(pausa)
    return movimentos, False, "Movimentações incompletas: paginação não terminou."


def _codigos_de_documentos(movimentos: list[Movimentacao]) -> set[str]:
    return {doc.get("cd_documento", "") for m in movimentos for doc in m.get("documentos", [])}


def _a_partir_de(movimentos: list[Movimentacao], desde: str) -> list[Movimentacao]:
    """Mantém movimentos sem data legível e os de data >= ``desde`` (ISO)."""
    return [m for m in movimentos if (normalizar_data(m.get("data"))["iso"] or desde) >= desde]


def _passou_de(movimentos: list[Movimentacao], desde: str) -> bool:
    datas = [normalizar_data(m.get("data"))["iso"] for m in movimentos]
    datas = [d for d in datas if d]
    return bool(datas) and datas[-1] < desde


def tabela_apos_titulo(soup: BeautifulSoup, titulo_regex: str) -> Any:
    titulo = soup.find(["h2", "h3"], string=re.compile(titulo_regex, re.I))
    if titulo:
        return titulo.find_next("table")

    titulo_esperado = normalizar_chave(titulo_regex)
    for tag in soup.find_all(["h2", "h3"]):
        titulo_atual = normalizar_chave(tag.get_text(" ", strip=True))
        if titulo_esperado and titulo_esperado in titulo_atual:
            return tag.find_next("table")
    return None


def linhas_dados_tabela(tabela: Any) -> list[list[Any]]:
    if not tabela:
        return []
    linhas = []
    for tr in tabela.find_all("tr"):
        tds = tr.find_all("td")
        if tds:
            linhas.append(tds)
    return linhas


def extrair_tabela_data_descricao(tabela: Any) -> list[dict[str, str]]:
    itens = []
    for tds in linhas_dados_tabela(tabela):
        if len(tds) < 2:
            continue
        itens.append(
            {
                "data": limpar(tds[0].get_text(" ", strip=True)),
                "descricao": limpar(tds[1].get_text(" ", strip=True)),
            }
        )
    return itens


def extrair_relacionados(soup: BeautifulSoup) -> dict[str, list[dict[str, str]]]:
    incidentes = []
    tabela_incidentes = tabela_apos_titulo(soup, r"Incidentes")
    for tds in linhas_dados_tabela(tabela_incidentes):
        if len(tds) < 2:
            continue
        link = tds[1].find("a", class_="incidente")
        texto = limpar(tds[1].get_text(" ", strip=True))
        match = re.search(r"\((\d{7}-\d{2}\.\d{4}\.8\.26\.\d{4})\)", texto)
        incidente = {
            "recebido_em": limpar(tds[0].get_text(" ", strip=True)),
            "classe": limpar(link.get_text(" ", strip=True)) if link else texto,
            "numero": match.group(1) if match else "",
            "href": urljoin(f"{ESAJ_BASE}/", link.get("href", "")) if link else "",
        }
        if any(incidente.values()):  # a tabela real tem uma linha de espaçamento vazia
            incidentes.append(incidente)

    apensos = []
    tabela_apensos = tabela_apos_titulo(soup, r"Apensos")
    for tds in linhas_dados_tabela(tabela_apensos):
        if len(tds) < 4:
            continue
        link = tds[0].find("a", class_="processoApensado")
        apensos.append(
            {
                "numero": limpar(tds[0].get_text(" ", strip=True)),
                "classe": limpar(tds[1].get_text(" ", strip=True)),
                "apensamento": limpar(tds[2].get_text(" ", strip=True)),
                "motivo": limpar(tds[3].get_text(" ", strip=True)),
                "href": urljoin(f"{ESAJ_BASE}/", link.get("href", "")) if link else "",
            }
        )
    return {"incidentes": incidentes, "apensos": apensos}


def extrair_audiencias(soup: BeautifulSoup) -> list[dict[str, str]]:
    audiencias = []
    for tds in linhas_dados_tabela(tabela_apos_titulo(soup, "Audiencias")):
        if len(tds) < 4:
            continue
        audiencias.append(
            {
                "data": limpar(tds[0].get_text(" ", strip=True)),
                "audiencia": limpar(tds[1].get_text(" ", strip=True)),
                "situacao": limpar(tds[2].get_text(" ", strip=True)),
                "qt_pessoas": limpar(tds[3].get_text(" ", strip=True)),
            }
        )
    return audiencias


def extrair_peticoes_diversas(soup: BeautifulSoup) -> list[dict[str, str]]:
    return extrair_tabela_data_descricao(tabela_apos_titulo(soup, "Peticoes diversas"))


def extrair_request_scope(text: str) -> str | None:
    marker = "var requestScope = "
    start = text.find(marker)
    if start < 0:
        return None
    index = text.find("[", start)
    if index < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for cursor in range(index, len(text)):
        char = text[cursor]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[index : cursor + 1]
    return None


def obter_metadados_pasta_documento(
    session: requests.Session, doc: Documento, *, timeout: float | None = None
) -> dict[str, Any]:
    # o extrato pode vir de um JSON externo; nunca requisitar fora do eSAJ
    _validar_url_esaj(doc["href"], ("/cpopg/", "/pastadigital/"))
    timeout = validar_timeout(getattr(session, "timeout", 30.0) if timeout is None else timeout)
    viewer = _get(session, doc["href"], timeout=timeout, allow_redirects=True)
    scope_json = extrair_request_scope(viewer.text)
    if not scope_json:
        return {"status": "sem_request_scope", "url_final": viewer.url}
    scope = json.loads(scope_json)
    raiz = scope[0] if scope else {}
    data = raiz.get("data", {})
    children = raiz.get("children") or []
    paginas = []
    for child in children:
        pagina = child.get("data", {})
        parametros_pdf = pagina.get("parametros", "")
        parametros = parse_qs(parametros_pdf)
        paginas.append(
            {
                "titulo": pagina.get("title", ""),
                "indice_pagina": pagina.get("indicePagina"),
                "nu_paginas": pagina.get("nuPaginas"),
                "num_inicial": (parametros.get("numInicial") or [""])[0],
                "num_final": (parametros.get("numFinal") or [""])[0],
                "nu_pagina": (parametros.get("nuPagina") or [""])[0],
                "id_documento": (parametros.get("idDocumento") or [""])[0],
                "documento_sigiloso": pagina.get("documentoSigiloso"),
                "sigilo_externo": (parametros.get("sigiloExterno") or [""])[0],
                "cd_formato_doc": pagina.get("cdFormatoDoc")
                or (parametros.get("cdFormatoDoc") or [""])[0],
                "possui_documento_original": pagina.get("possuiDocumentoOriginal"),
                "parametros_pdf": parametros_pdf,
            }
        )
    return {
        "status": "ok",
        "url_final": viewer.url,
        "titulo": data.get("title", ""),
        "cd_documento": data.get("cdDocumento", ""),
        "cd_formato_doc": data.get("cdFormatoDoc", ""),
        "sigilo_absoluto": data.get("sigiloAbsoluto"),
        "fl_peticao_inicial": data.get("flPeticaoInicial"),
        "fl_protocolado": data.get("flProtocolado"),
        "total_paginas_no_documento": len(paginas),
        "paginas": paginas,
    }


def iterar_docs_publicos(
    movimentos: Sequence[MovimentoDeEntrada],
) -> Iterator[Documento]:
    vistos = set()
    for movimento in movimentos:
        for doc in movimento.get("documentos", []):
            cd_documento = doc.get("cd_documento")
            if doc.get("status_acesso") != "publico_candidato" or not cd_documento:
                continue
            if cd_documento in vistos:
                continue
            vistos.add(cd_documento)
            yield doc


def _documentos_restritos(movimentos: Sequence[MovimentoDeEntrada]) -> list[Documento]:
    documentos: list[Documento] = []
    for movimento in movimentos:
        for doc in movimento.get("documentos", []):
            if doc.get("status_acesso") == "restrito_por_senha":
                documentos.append(doc)
    return documentos


def _documentos_para_tentativa(restritos: list[Documento]) -> list[Documento]:
    documentos: list[Documento] = []
    recursos_vistos: set[str] = set()
    for doc in restritos:
        recurso = str(doc.get("id_recurso") or "")
        if not recurso or recurso in recursos_vistos:
            continue
        recursos_vistos.add(recurso)
        documentos.append(doc)
    return documentos


def _formulario_senha(
    session: requests.Session, url_processo: str, timeout: float
) -> tuple[str, dict[str, str], str, str] | None:
    pagina = carregar_pagina(session, url_processo, timeout=timeout)
    form = BeautifulSoup(pagina.text, "html.parser").find("form", id="popupSenha")
    if form is None or form.find("input", attrs={"name": "senhaProcesso"}) is None:
        return None

    action = urljoin(pagina.url, str(form.get("action") or pagina.url))
    _validar_url_esaj(action)
    campos_ocultos = _campos_ocultos_formulario_senha(form)
    nome_botao, valor_botao = _botao_formulario_senha(form)
    return action, campos_ocultos, nome_botao, valor_botao


def _campos_ocultos_formulario_senha(form: Any) -> dict[str, str]:
    return {
        str(item.get("name")): str(item.get("value") or "")
        for item in form.select('input[type="hidden"][name]')
    }


def _botao_formulario_senha(form: Any) -> tuple[str, str]:
    botao = form.find("input", id="btEnviarSenha")
    if botao is None:
        return "", ""
    return str(botao.get("name") or ""), str(botao.get("value") or "")


def _marcar_autorizacao_recurso(
    restritos: list[Documento], recurso: str, status: StatusAutorizacao
) -> None:
    for doc in restritos:
        if str(doc.get("id_recurso") or "") == recurso:
            doc["status_autorizacao"] = status


def _status_redirecionamento_senha(resposta: Any, action: str) -> StatusAutorizacao | None:
    location = str((getattr(resposta, "headers", {}) or {}).get("Location") or "")
    if not (300 <= resposta.status_code < 400 and location):
        return None
    destino = urlparse(urljoin(action, location))
    if destino.path.startswith(("/esaj/api/auth/", "/sajcas/login")):
        return "identificacao_do_advogado_necessaria"
    if destino.scheme != "https" or destino.netloc != "esaj.tjsp.jus.br":
        return "redirecionamento_externo_nao_seguido"
    return None


def _status_resposta_http_senha(
    status_code: int,
) -> tuple[StatusAutorizacao, int | None] | None:
    if status_code in {401, 403}:
        return "identificacao_do_advogado_necessaria", None
    if status_code >= 400:
        return "erro_http_do_portal", status_code
    return None


def _senha_invalida_no_retorno(texto: str) -> bool:
    conteudo = limpar(BeautifulSoup(texto, "html.parser").get_text(" ", strip=True)).casefold()
    return any(
        sinal in conteudo for sinal in ("senha incorreta", "senha invalida", "senha inválida")
    )


def _csrf_retorno_senha(texto: str) -> str | None:
    form = BeautifulSoup(texto, "html.parser").find("form", id="popupSenha")
    csrf = form.select_one('input[type="hidden"][name="_csrf"]') if form else None
    return str(csrf.get("value") or "") if csrf else None


def _classificar_retorno_senha(
    resposta: Any, action: str, restritos: list[Documento], recurso: str
) -> tuple[dict[str, Any] | None, str | None]:
    status = _status_redirecionamento_senha(resposta, action)
    http_status = None
    if status is None:
        falha_http = _status_resposta_http_senha(resposta.status_code)
        if falha_http:
            status, http_status = falha_http
    if status is None and _senha_invalida_no_retorno(resposta.text):
        status = "senha_invalida"
    if status:
        _marcar_autorizacao_recurso(restritos, recurso, status)
        resultado: dict[str, Any] = {"status": status, "documentos_liberados": 0}
        if http_status is not None:
            resultado["http_status"] = http_status
        return resultado, None
    return None, _csrf_retorno_senha(resposta.text)


def _postar_senha_recurso(
    session: requests.Session,
    action: str,
    campos_ocultos: dict[str, str],
    nome_botao: str,
    valor_botao: str,
    restritos: list[Documento],
    doc: Documento,
    senha_processo: str,
    timeout: float,
) -> tuple[dict[str, Any] | None, str | None]:
    recurso = str(doc.get("id_recurso") or "")
    dados = dict(campos_ocultos)
    dados["senhaProcesso"] = senha_processo
    dados["idRecursoQueProvocouLiberacaoPorSenha"] = recurso
    if nome_botao:
        dados[nome_botao] = valor_botao
    _aguardar_ritmo()
    try:
        resposta = session.post(action, data=dados, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        _marcar_autorizacao_recurso(restritos, recurso, "erro_de_comunicacao")
        return {
            "status": "erro_de_comunicacao",
            "tipo_erro": type(exc).__name__,
            "documentos_liberados": 0,
        }, None
    return _classificar_retorno_senha(resposta, action, restritos, recurso)


def _submeter_senhas_restritas(
    session: requests.Session,
    action: str,
    campos_ocultos: dict[str, str],
    nome_botao: str,
    valor_botao: str,
    restritos: list[Documento],
    senha_processo: str,
    timeout: float,
) -> tuple[dict[str, Any] | None, int]:
    tentativas = 0
    for doc in _documentos_para_tentativa(restritos):
        tentativas += 1
        falha, novo_csrf = _postar_senha_recurso(
            session,
            action,
            campos_ocultos,
            nome_botao,
            valor_botao,
            restritos,
            doc,
            senha_processo,
            timeout,
        )
        if falha:
            falha["tentativas"] = tentativas
            return falha, tentativas
        if novo_csrf is not None:
            campos_ocultos["_csrf"] = novo_csrf
    return None, tentativas


def _recarregar_autorizacao_senha(
    session: requests.Session,
    url_processo: str,
    restritos: list[Documento],
    timeout: float,
    pausa_paginas: float,
) -> dict[str, Any]:
    _aguardar_ritmo()
    pagina_atual = carregar_pagina(session, url_processo, timeout=timeout)
    codigo = processo_codigo(pagina_atual.url)
    atualizados, completo, aviso = carregar_movimentacoes_ajax(
        session,
        codigo,
        limite=None,
        pausa=pausa_paginas,
        timeout=timeout,
    )
    novos_por_codigo = {
        str(doc.get("cd_documento")): doc
        for movimento in atualizados
        for doc in movimento.get("documentos", [])
        if doc.get("cd_documento")
    }
    codigos_liberados: set[str] = set()
    for doc in restritos:
        codigo_documento = str(doc.get("cd_documento") or "")
        novo = novos_por_codigo.get(codigo_documento)
        if novo and novo.get("status_acesso") == "publico_candidato":
            doc.update(
                {
                    "href": novo.get("href", ""),
                    "id_recurso": novo.get("id_recurso", doc.get("id_recurso", "")),
                    "status_acesso": "publico_candidato",
                    "status_autorizacao": "liberado_pelo_portal",
                }
            )
            if codigo_documento:
                codigos_liberados.add(codigo_documento)
        else:
            doc["status_autorizacao"] = "nao_liberado_pelo_portal"
    return {
        "status": "liberado" if codigos_liberados else "nao_liberado_pelo_portal",
        "documentos_liberados": len(codigos_liberados),
        "movimentacoes_recarregadas_completas": completo,
        "aviso": aviso,
    }


def liberar_autos_com_senha(
    session: requests.Session,
    url_processo: str,
    movimentos: Sequence[MovimentoDeEntrada],
    senha_processo: str,
    *,
    timeout: float = 30.0,
    pausa_paginas: float = PAUSA_PAGINAS,
) -> dict[str, Any]:
    """Submete uma senha fornecida pelo usuário no formulário oficial do e-SAJ.

    Não tenta adivinhar senha nem contorna autenticação. A senha não é registrada;
    o resultado só é considerado liberado se o próprio portal devolver links de
    documento utilizáveis na mesma sessão.
    """
    if not senha_processo:
        return {"status": "senha_vazia", "documentos_liberados": 0}
    timeout = validar_timeout(timeout)

    restritos = _documentos_restritos(movimentos)
    if not restritos:
        return {"status": "sem_documentos_restritos", "documentos_liberados": 0}

    formulario = _formulario_senha(session, url_processo, timeout)
    if formulario is None:
        for doc in restritos:
            doc["status_autorizacao"] = "formulario_senha_indisponivel"
        return {"status": "formulario_senha_indisponivel", "documentos_liberados": 0}
    action, campos_ocultos, nome_botao, valor_botao = formulario
    for doc in restritos:
        if not str(doc.get("id_recurso") or ""):
            doc["status_autorizacao"] = "identificador_de_recurso_ausente"
    falha, tentativas = _submeter_senhas_restritas(
        session,
        action,
        campos_ocultos,
        nome_botao,
        valor_botao,
        restritos,
        senha_processo,
        timeout=timeout,
    )
    if falha:
        return falha
    resultado = _recarregar_autorizacao_senha(
        session, url_processo, restritos, timeout, pausa_paginas
    )
    resultado["tentativas"] = tentativas
    return resultado


def inspecionar_pecas_publicas(
    session: requests.Session,
    movimentos: Sequence[MovimentoDeEntrada],
    limite: int,
    *,
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    limite = validar_inteiro(limite, nome="limite", minimo=0)
    inspecionados: list[dict[str, Any]] = []
    for doc in iterar_docs_publicos(movimentos):
        if limite and len(inspecionados) >= limite:
            return inspecionados
        try:
            doc["pasta_digital"] = obter_metadados_pasta_documento(session, doc, timeout=timeout)
        except Exception as exc:  # pragma: no cover - depende de fonte externa
            doc["pasta_digital"] = {"status": "erro", "mensagem": str(exc)}
        inspecionados.append(
            {
                "cd_documento": doc.get("cd_documento", ""),
                "titulo": doc.get("titulo", ""),
                "pasta_digital": doc.get("pasta_digital", {}),
            }
        )
    return inspecionados


def baixar_pecas_publicas(
    session: requests.Session,
    movimentos: Sequence[MovimentoDeEntrada],
    pasta: Path,
    limite: int,
    sobrescrever: bool = False,
    max_bytes: int = MAX_DOCUMENT_DOWNLOAD_BYTES,
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    limite = validar_inteiro(limite, nome="limite", minimo=0)
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= MAX_DOCUMENT_DOWNLOAD_BYTES
    ):
        raise ValueError(f"max_bytes deve estar entre 1 e {MAX_DOCUMENT_DOWNLOAD_BYTES}.")
    timeout = validar_timeout(getattr(session, "timeout", 30.0) if timeout is None else timeout)
    pasta.mkdir(parents=True, exist_ok=True)
    baixados: list[dict[str, Any]] = []
    for indice, doc in enumerate(iterar_docs_publicos(movimentos)):
        if limite and indice >= limite:
            break
        titulo = nome_arquivo_seguro(doc.get("titulo", "documento"))
        codigo = nome_arquivo_seguro(str(doc["cd_documento"]), fallback="sem-id")
        destino = pasta / f"peca_{codigo}_{titulo[:40]}.pdf"
        if not sobrescrever and tamanho_pdf_existente_valido(destino, max_bytes) is not None:
            doc["download_status"] = "existente"
            baixados.append(
                {
                    "cd_documento": doc.get("cd_documento", ""),
                    "arquivo": str(destino),
                    "status": "existente",
                }
            )
            continue
        try:
            pasta_digital = doc.get("pasta_digital") or obter_metadados_pasta_documento(
                session, doc, timeout=timeout
            )
        except Exception as exc:  # uma peça com falha não cancela as demais
            doc["download_status"] = "erro_pasta_digital"
            doc["download_message"] = str(exc)
            continue
        doc["pasta_digital"] = pasta_digital
        if pasta_digital.get("status") != "ok":
            doc["download_status"] = pasta_digital.get("status", "erro_pasta_digital")
            continue
        paginas = pasta_digital.get("paginas") or []
        if not paginas:
            doc["download_status"] = "sem_paginas"
            continue
        params = paginas[0].get("parametros_pdf", "")
        try:
            status, bytes_gravados, preview = _baixar_pdf_atomico(
                session,
                urljoin(PASTA_BASE, f"getPDF.do?{params}"),
                destino,
                timeout=timeout,
                max_bytes=max_bytes,
            )
        except Exception as exc:  # falha por documento, não por processo/lote
            doc["download_status"] = "erro_download"
            doc["download_message"] = str(exc)
            continue
        if status != "baixado":
            expirada = MARCA_SESSAO_EXPIRADA in preview.lower()
            doc["download_status"] = "sessao_expirada" if expirada else status
            continue
        doc["download_status"] = "baixado"
        doc["arquivo"] = str(destino)
        baixados.append(
            {
                "cd_documento": doc.get("cd_documento", ""),
                "arquivo": str(destino),
                "bytes": bytes_gravados,
                "status": "baixado",
            }
        )
    return baixados


def _baixar_pdf_atomico(
    session: requests.Session,
    url: str,
    destino: Path,
    *,
    timeout: float,
    max_bytes: int = MAX_DOCUMENT_DOWNLOAD_BYTES,
) -> tuple[str, int, str]:
    """Stream para arquivo temporário e publica o destino só após validar o cabeçalho PDF."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    response = _get(session, url, timeout=timeout, stream=True)
    part: Path | None = None
    total = 0
    inicio = bytearray()
    preview = bytearray()
    reconhecido_pdf = False
    try:
        content_length = str((getattr(response, "headers", {}) or {}).get("Content-Length", ""))
        if content_length.isdigit() and int(content_length) > max_bytes:
            return "documento_muito_grande", 0, ""
        chunks = (
            response.iter_content(chunk_size=64 * 1024)
            if callable(getattr(response, "iter_content", None))
            else [getattr(response, "content", b"") or b""]
        )
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destino.name}.",
            suffix=".part",
            dir=destino.parent,
            delete=False,
        ) as arquivo:
            part = Path(arquivo.name)
            for chunk in chunks:
                if not chunk:
                    continue
                if not reconhecido_pdf:
                    inicio.extend(chunk)
                    if len(inicio) < 5:
                        continue
                    reconhecido_pdf = bytes(inicio[:5]).startswith(b"%PDF")
                    if not reconhecido_pdf:
                        preview.extend(inicio[:4096])
                        break
                    total += len(inicio)
                    if total > max_bytes:
                        return "documento_muito_grande", 0, ""
                    arquivo.write(inicio)
                    inicio.clear()
                    continue
                total += len(chunk)
                if total > max_bytes:
                    return "documento_muito_grande", 0, ""
                arquivo.write(chunk)
        if not reconhecido_pdf or total == 0:
            return "nao_pdf", 0, bytes(preview).decode("utf-8", errors="replace")
        part.replace(destino)
        return "baixado", total, ""
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
        if part is not None and part.exists():
            part.unlink()


def ler_pecas_publicas(
    session: requests.Session,
    movimentos: Sequence[MovimentoDeEntrada],
    limite: int = 3,
    max_chars: int = 4000,
    *,
    timeout: float | None = None,
    max_bytes: int = MAX_IN_MEMORY_DOCUMENT_BYTES,
) -> list[dict[str, Any]]:
    """Le documentos publicos candidatos em memoria, sem salvar PDFs em disco.

    PDFs remotos ainda precisam ser transferidos para memoria para que o texto seja
    extraido. Documentos restritos por senha, captcha ou sigilo nao sao acessados.
    """
    limite = validar_inteiro(limite, nome="limite", minimo=0)
    max_chars = validar_inteiro(max_chars, nome="max_chars", minimo=0)
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= MAX_IN_MEMORY_DOCUMENT_BYTES
    ):
        raise ValueError(f"max_bytes deve estar entre 1 e {MAX_IN_MEMORY_DOCUMENT_BYTES}.")
    timeout = validar_timeout(getattr(session, "timeout", 30.0) if timeout is None else timeout)
    documentos_lidos: list[dict[str, Any]] = []
    for doc in iterar_docs_publicos(movimentos):
        if limite and len(documentos_lidos) >= limite:
            return documentos_lidos

        registro: dict[str, Any] = {
            "cd_documento": doc.get("cd_documento", ""),
            "titulo": doc.get("titulo", ""),
            "status": "pendente",
        }
        try:
            pasta_digital = doc.get("pasta_digital") or obter_metadados_pasta_documento(
                session, doc, timeout=timeout
            )
            doc["pasta_digital"] = pasta_digital
            registro["pasta_digital"] = {
                "status": pasta_digital.get("status", ""),
                "paginas": len(pasta_digital.get("paginas") or []),
            }
            if pasta_digital.get("status") != "ok":
                registro["status"] = pasta_digital.get("status", "erro_pasta_digital")
                documentos_lidos.append(registro)
                continue

            paginas = pasta_digital.get("paginas") or []
            if not paginas:
                registro["status"] = "sem_paginas"
                documentos_lidos.append(registro)
                continue

            params = paginas[0].get("parametros_pdf", "")
            response = _get(
                session,
                urljoin(PASTA_BASE, f"getPDF.do?{params}"),
                timeout=timeout,
                stream=True,
            )
            conteudo = _ler_resposta_limitada(response, max_bytes)
            if conteudo is None:
                registro["status"] = "documento_muito_grande"
                registro["mensagem"] = (
                    f"O documento excede o limite de {max_bytes} bytes para leitura em memória."
                )
                documentos_lidos.append(registro)
                continue
            registro["bytes"] = len(conteudo)
            registro["mime_type"] = _content_type(response)

            if conteudo.startswith(b"%PDF"):
                texto, status = extrair_texto_pdf_bytes(conteudo, max_chars=max_chars)
                registro["status"] = status
                registro["texto"] = texto
                mensagem = mensagem_status_extracao_pdf(status)
                if mensagem:
                    registro["mensagem"] = mensagem
                registro["texto_chars"] = len(texto)
                registro["truncado"] = bool(max_chars and len(texto) >= max_chars)
            else:
                texto = _texto_bytes_nao_pdf(
                    conteudo,
                    max_chars=max_chars,
                    encoding=getattr(response, "encoding", None),
                )
                if MARCA_SESSAO_EXPIRADA in texto.lower():
                    registro["status"] = "sessao_expirada"
                    registro["mensagem"] = (
                        "O eSAJ recusou a leitura: a pasta digital só abre na sessão da consulta."
                    )
                    documentos_lidos.append(registro)
                    continue
                registro["status"] = "texto_html_extraido" if texto else "nao_pdf"
                registro["texto"] = texto
                registro["texto_chars"] = len(texto)
                registro["truncado"] = bool(max_chars and len(texto) >= max_chars)
            documentos_lidos.append(registro)
        except Exception as exc:  # pragma: no cover - depende de fonte externa
            registro["status"] = "erro"
            registro["mensagem"] = str(exc)
            documentos_lidos.append(registro)
    return documentos_lidos


def extrair_texto_pdf_bytes(conteudo: bytes, max_chars: int = 4000) -> tuple[str, str]:
    """Extrai texto de PDF em memoria quando o parser opcional esta instalado."""
    max_chars = validar_inteiro(max_chars, nome="max_chars", minimo=0)
    try:
        pdf_reader = importlib.import_module("pypdf").PdfReader
    except ImportError:
        return "", "pdf_parser_indisponivel"

    try:
        reader = pdf_reader(BytesIO(conteudo))
        partes = []
        for page in reader.pages:
            texto = page.extract_text() or ""
            if texto:
                partes.append(texto)
            parcial = limpar("\n".join(partes))
            if max_chars and len(parcial) >= max_chars:
                return parcial[:max_chars], "texto_extraido"
        texto_final = limpar("\n".join(partes))
        if max_chars:
            texto_final = texto_final[:max_chars]
        return texto_final, "texto_extraido" if texto_final else "pdf_sem_texto_extraido"
    except Exception as exc:  # pragma: no cover - depende da estrutura interna do PDF
        return "", f"erro_pdf:{type(exc).__name__}"


def mensagem_status_extracao_pdf(status: str) -> str:
    """Retorna orientação para PDFs obtidos sem texto disponível ao leitor."""
    if status == "pdf_parser_indisponivel":
        return (
            "O documento é PDF e falta o leitor de PDF. Instale com: "
            'python -m pip install "nanojud[pdf]"'
        )
    if status == "pdf_sem_texto_extraido":
        return (
            "O PDF foi obtido, mas não contém texto extraível; pode ser digitalizado como imagem."
        )
    return ""


MARCA_SESSAO_EXPIRADA = "sua sessão expirou"


def preparar_documentos(
    session: requests.Session,
    numero: str,
    movimentos: Sequence[MovimentoDeEntrada],
    limite: int = 0,
    *,
    timeout: float | None = None,
) -> None:
    """Deixa a sessão apta a abrir as pastas digitais dos documentos que serão lidos.

    O eSAJ só libera um documento na sessão que abriu o processo e carregou a página de
    movimentações onde ele aparece; o ticket guardado em um extrato salvo (JSON) já
    venceu. Sem isso a pasta devolve "sessão expirou" ou fica sem conteúdo.
    """
    limite = validar_inteiro(limite, nome="limite", minimo=0)
    timeout = validar_timeout(getattr(session, "timeout", 30.0) if timeout is None else timeout)
    docs = list(iterar_docs_publicos(movimentos))
    alvo = {d.get("cd_documento", "") for d in (docs[:limite] if limite else docs)}
    for doc in docs:
        doc.pop("pasta_digital", None)
    response = carregar_pagina(session, numero, timeout=timeout)
    if alvo and BeautifulSoup(response.text, "html.parser").find(id="btnExibirMovimentacoes"):
        carregar_movimentacoes_ajax(
            session,
            codigo_para_movimentacoes(response.text, response.url),
            limite=None,
            ate_documentos=alvo,
            timeout=timeout,
        )


def _texto_bytes_nao_pdf(conteudo: bytes, max_chars: int, encoding: str | None = None) -> str:
    texto = conteudo.decode(encoding or "utf-8", errors="replace")
    if BeautifulSoup is not None and "<" in texto and ">" in texto:
        texto = BeautifulSoup(texto, "html.parser").get_text(" ", strip=True)
    texto = limpar(texto)
    return texto[:max_chars] if max_chars else texto


def _content_type(response: Any) -> str:
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("Content-Type") or headers.get("content-type") or "")


def _ler_resposta_limitada(response: Any, max_bytes: int) -> bytes | None:
    """Lê uma resposta em blocos e interrompe assim que excede o limite em memória."""
    headers = getattr(response, "headers", {}) or {}
    content_length = str(headers.get("Content-Length") or headers.get("content-length") or "")
    if content_length.isdigit() and int(content_length) > max_bytes:
        fechar = getattr(response, "close", None)
        if callable(fechar):
            fechar()
        return None
    chunks = (
        response.iter_content(chunk_size=64 * 1024)
        if callable(getattr(response, "iter_content", None))
        else [getattr(response, "content", b"") or b""]
    )
    conteudo = bytearray()
    try:
        for bloco in chunks:
            if not bloco:
                continue
            if len(conteudo) + len(bloco) > max_bytes:
                return None
            conteudo.extend(bloco)
        return bytes(conteudo)
    finally:
        fechar = getattr(response, "close", None)
        if callable(fechar):
            fechar()


def montar_extrato(
    entrada: str,
    baixar_pecas: bool = False,
    limite_pecas: int = 3,
    inspecionar_pecas: bool = False,
    limite_inspecao_pecas: int = 10,
    salvar_html: bool = False,
    session: requests.Session | None = None,
    pasta_pecas: Path | None = None,
    timeout: float | None = None,
    limite_movimentacoes: int | None = LIMITE_MOVIMENTACOES,
    pausa_paginas: float = PAUSA_PAGINAS,
    desde: str = "",
    senha_processo: str | None = None,
    senha_processo_provider: Callable[[str, list[Any]], str | None] | None = None,
) -> Extrato:
    limite_pecas = validar_inteiro(limite_pecas, nome="limite_pecas", minimo=0)
    limite_inspecao_pecas = validar_inteiro(
        limite_inspecao_pecas, nome="limite_inspecao_pecas", minimo=0
    )
    if limite_movimentacoes is not None:
        limite_movimentacoes = validar_inteiro(
            limite_movimentacoes, nome="limite_movimentacoes", minimo=0
        )
    if timeout is None:
        timeout = getattr(session, "timeout", 30.0)
    timeout = validar_timeout(timeout)
    session = session or criar_session(timeout=timeout)
    response = carregar_pagina(session, entrada, timeout=timeout)
    soup = BeautifulSoup(response.text, "html.parser")
    detectar_estado_pagina(soup, response)

    dados_basicos = extrair_dados_basicos(soup, response.url)
    html_bruto = ""
    if salvar_html:
        numero_html = dados_basicos.get("numero") or entrada
        html_bruto = str(salvar_html_bruto(response.text, numero_html))

    movimentos = extrair_movimentacoes(soup)
    movimentos_completos, aviso_movimentacoes = True, ""
    if not movimentos and soup.find(id="btnExibirMovimentacoes"):
        movimentos, movimentos_completos, aviso_movimentacoes = carregar_movimentacoes_ajax(
            session,
            codigo_para_movimentacoes(response.text, response.url),
            limite=limite_movimentacoes,
            pausa=pausa_paginas,
            timeout=timeout,
            desde=desde,
        )
    elif desde:
        movimentos = _a_partir_de(movimentos, desde)
    restritos_antes = [
        doc
        for movimento in movimentos
        for doc in movimento.get("documentos", [])
        if doc.get("status_acesso") == "restrito_por_senha"
    ]
    if senha_processo is None and senha_processo_provider and restritos_antes:
        senha_processo = senha_processo_provider(entrada, restritos_antes)
    tentativa_senha = None
    if senha_processo is not None:
        tentativa_senha = liberar_autos_com_senha(
            session,
            response.url,
            movimentos,
            senha_processo,
            timeout=timeout or 30.0,
            pausa_paginas=pausa_paginas,
        )
    documentos_unicos: dict[str, Documento] = {}
    restritos_unicos: dict[str, Documento] = {}
    for movimento in movimentos:
        for doc in movimento.get("documentos", []):
            doc.setdefault("data_documento", movimento.get("data", ""))
            key = doc.get("cd_documento") or doc.get("href", "")
            if doc.get("status_acesso") == "restrito_por_senha":
                restritos_unicos.setdefault(key, doc)
            elif doc.get("cd_documento"):
                documentos_unicos.setdefault(doc["cd_documento"], doc)

    documentos: Documentos = {
        "publicos_candidatos_unicos": list(documentos_unicos.values()),
        "restritos_por_senha_unicos": list(restritos_unicos.values()),
    }
    if tentativa_senha is not None:
        documentos["tentativas_autorizacao"] = [tentativa_senha]
    if inspecionar_pecas:
        documentos["pecas_publicas_inspecionadas"] = inspecionar_pecas_publicas(
            session, movimentos, limite_inspecao_pecas, timeout=timeout
        )
    if baixar_pecas:
        destino = pasta_pecas or Path.cwd() / "esaj_pecas"
        try:
            documentos["baixados"] = baixar_pecas_publicas(
                session, movimentos, destino, limite_pecas, timeout=timeout
            )
        except DownloadIndisponivel:
            raise
        except Exception as exc:  # pragma: no cover - depende de fonte externa
            raise DownloadIndisponivel(str(exc)) from exc

    extrato_parcial = not movimentos_completos
    mensagem = "Extrato gerado parcialmente" if extrato_parcial else "Extrato gerado com sucesso"
    if aviso_movimentacoes:
        mensagem = f"{mensagem}: {aviso_movimentacoes}"

    return {
        "status": "partial" if extrato_parcial else "ok",
        "mensagem": mensagem,
        "origem": {
            "sistema": "eSAJ",
            "tribunal": "TJSP",
            "grau": "1g",
            "consulta": "cpopg",
            "entrada": entrada,
            "url_final": response.url,
            "html_bruto": html_bruto,
            "movimentacoes_completas": movimentos_completos,
            "aviso_movimentacoes": aviso_movimentacoes,
            "data_coleta": datetime.now(UTC).isoformat(),
        },
        "dados_basicos": dados_basicos,
        "partes": extrair_partes(soup),
        "movimentacoes": movimentos,
        "peticoes_diversas": extrair_peticoes_diversas(soup),
        "audiencias": extrair_audiencias(soup),
        "documentos": documentos,
        "relacionados": extrair_relacionados(soup),
    }
