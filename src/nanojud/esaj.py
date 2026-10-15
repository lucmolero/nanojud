"""Cliente e parser eSAJ/TJSP."""

from __future__ import annotations

import importlib
import json
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlencode, urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - ambientes de documentação podem não ter deps
    requests = None
    BeautifulSoup = None

from .exceptions import (
    AcessoRestrito,
    ConsultaIndisponivel,
    DownloadIndisponivel,
    ProcessoNaoEncontrado,
    URLInvalida,
)
from .models import Documento, Extrato
from .normalization import normalizar_data
from .utils import (
    classificar_polo,
    limpar,
    nome_arquivo_seguro,
    normalizar_chave,
    validar_numero_cnj,
)
from .version import __version__

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
RAW_HTML_DIR = Path.cwd() / "esaj_raw" / "tjsp" / "cpopg"
USER_AGENT = (
    f"Mozilla/5.0 (compatible; nanojud/{__version__}; +https://github.com/lucmolero/nanojud)"
)


def _garantir_dependencias() -> None:
    if requests is None or BeautifulSoup is None:
        raise ConsultaIndisponivel("requests/beautifulsoup4 não estão disponíveis no ambiente.")


def criar_session(timeout: float = 30.0) -> requests.Session:
    """Cria sessão HTTP com cabeçalhos conservadores para consulta pública."""
    _garantir_dependencias()
    session = requests.Session()
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
    if "timeout" not in kwargs and hasattr(session, "timeout"):
        kwargs["timeout"] = session.timeout
    try:
        response = session.get(url, **kwargs)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(f"Falha de comunicação com o eSAJ: {exc}") from exc

    status_code = getattr(response, "status_code", 0)
    if status_code in {401, 403}:
        raise AcessoRestrito(f"eSAJ retornou HTTP {status_code}.")
    if status_code >= 500:
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
        candidato = link.get("href", "")
        match = re.search(r"processo\.foro=(\d+)", candidato)
        if foro_pedido and match and match.group(1).lstrip("0") == foro_pedido:
            href = candidato
            break
    href = href or links[0].get("href", "")
    kwargs = {"allow_redirects": True}
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
        kwargs = {"allow_redirects": True}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return _seguir_lista_se_preciso(session, _get(session, entrada, **kwargs), timeout=timeout)

    numero = validar_numero_cnj(entrada)
    open_kwargs = {}
    search_kwargs = {"allow_redirects": True}
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


def extrair_dados_basicos(soup: BeautifulSoup, url_final: str) -> dict[str, Any]:
    campos_rotulados: dict[str, str] = {}
    for container_id in ("containerDadosPrincipaisProcesso", "maisDetalhes"):
        campos_rotulados.update(extrair_campos_rotulados(soup.find(id=container_id)))

    dados = {
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


def extrair_partes_tabela(tabela: Any) -> list[dict[str, Any]]:
    partes = []
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


def extrair_partes(soup: BeautifulSoup) -> dict[str, list[dict[str, Any]]]:
    principais = extrair_partes_tabela(soup.find("table", id="tablePartesPrincipais"))
    todas = extrair_partes_tabela(soup.find("table", id="tableTodasPartes"))
    if not todas:
        tabela_todas = soup.find("table", {"class": lambda c: c and "todasPartes" in c})
        todas = extrair_partes_tabela(tabela_todas)

    todas = todas or principais  # processos pequenos só trazem a tabela de partes principais
    base_para_polos = todas
    polo_ativo = []
    polo_passivo = []
    polo_desconhecido = []
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


def classificar_documento(href: str) -> str:
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


def extrair_movimentacoes(soup: BeautifulSoup) -> list[dict[str, Any]]:
    tabela = soup.find(["table", "tbody"], id="tabelaTodasMovimentacoes") or soup.find(
        ["table", "tbody"], id="tabelaUltimasMovimentacoes"
    )
    if not tabela:
        return []
    return _movimentos_das_linhas(tabela)


def _movimentos_das_linhas(container: Any, ordem_inicial: int = 0) -> list[dict[str, Any]]:
    movimentos = []
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
) -> tuple[list[dict[str, Any]], bool, str]:
    """Pagina carregarMovimentacoesAjax.do (cursor opaco, 5 linhas por página).

    Retorna (movimentos, completo, aviso). ``limite`` vazio ou 0 busca tudo. ``desde``
    (YYYY-MM-DD) para a paginação ao chegar em movimentos mais antigos, que vêm por último.
    ``ate_documentos`` (códigos de documento) para assim que todos aparecerem nas linhas lidas.
    Falha de rede no meio devolve o que já foi coletado com ``completo=False``.
    """
    movimentos: list[dict[str, Any]] = []
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


def _codigos_de_documentos(movimentos: list[dict[str, Any]]) -> set[str]:
    return {doc.get("cd_documento", "") for m in movimentos for doc in m.get("documentos", [])}


def _a_partir_de(movimentos: list[dict[str, Any]], desde: str) -> list[dict[str, Any]]:
    """Mantém movimentos sem data legível e os de data >= ``desde`` (ISO)."""
    return [m for m in movimentos if (normalizar_data(m.get("data"))["iso"] or desde) >= desde]


def _passou_de(movimentos: list[dict[str, Any]], desde: str) -> bool:
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


def obter_metadados_pasta_documento(session: requests.Session, doc: Documento) -> dict[str, Any]:
    # o extrato pode vir de um JSON externo; nunca requisitar fora do eSAJ
    _validar_url_esaj(doc["href"], ("/cpopg/", "/pastadigital/"))
    viewer = _get(session, doc["href"], timeout=30, allow_redirects=True)
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


def iterar_docs_publicos(movimentos: list[dict[str, Any]]):
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


def inspecionar_pecas_publicas(
    session: requests.Session, movimentos: list[dict[str, Any]], limite: int
) -> list[dict[str, Any]]:
    inspecionados = []
    for doc in iterar_docs_publicos(movimentos):
        if limite and len(inspecionados) >= limite:
            return inspecionados
        try:
            doc["pasta_digital"] = obter_metadados_pasta_documento(session, doc)
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
    movimentos: list[dict[str, Any]],
    pasta: Path,
    limite: int,
    sobrescrever: bool = False,
) -> list[dict[str, Any]]:
    pasta.mkdir(parents=True, exist_ok=True)
    baixados = []
    for doc in iterar_docs_publicos(movimentos):
        if limite and len(baixados) >= limite:
            return baixados
        pasta_digital = doc.get("pasta_digital") or obter_metadados_pasta_documento(session, doc)
        doc["pasta_digital"] = pasta_digital
        if pasta_digital.get("status") != "ok":
            doc["download_status"] = pasta_digital.get("status", "erro_pasta_digital")
            continue
        paginas = pasta_digital.get("paginas") or []
        if not paginas:
            doc["download_status"] = "sem_paginas"
            continue
        params = paginas[0].get("parametros_pdf", "")
        response = _get(session, urljoin(PASTA_BASE, f"getPDF.do?{params}"), timeout=30)
        if not response.content.startswith(b"%PDF"):
            expirada = MARCA_SESSAO_EXPIRADA in _texto_resposta_nao_pdf(response, 400).lower()
            doc["download_status"] = "sessao_expirada" if expirada else "nao_pdf"
            continue

        titulo = nome_arquivo_seguro(doc.get("titulo", "documento"))
        destino = pasta / f"peca_{doc.get('cd_documento') or 'sem-id'}_{titulo[:40]}.pdf"
        if destino.exists() and not sobrescrever:
            doc["download_status"] = "existente"
            baixados.append(
                {
                    "cd_documento": doc.get("cd_documento", ""),
                    "arquivo": str(destino),
                    "status": "existente",
                }
            )
            continue
        destino.write_bytes(response.content)
        doc["download_status"] = "baixado"
        doc["arquivo"] = str(destino)
        baixados.append(
            {
                "cd_documento": doc.get("cd_documento", ""),
                "arquivo": str(destino),
                "bytes": len(response.content),
                "status": "baixado",
            }
        )
    return baixados


def ler_pecas_publicas(
    session: requests.Session,
    movimentos: list[dict[str, Any]],
    limite: int = 3,
    max_chars: int = 4000,
) -> list[dict[str, Any]]:
    """Le documentos publicos candidatos em memoria, sem salvar PDFs em disco.

    PDFs remotos ainda precisam ser transferidos para memoria para que o texto seja
    extraido. Documentos restritos por senha, captcha ou sigilo nao sao acessados.
    """
    documentos_lidos = []
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
                session, doc
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
            response = _get(session, urljoin(PASTA_BASE, f"getPDF.do?{params}"), timeout=30)
            conteudo = getattr(response, "content", b"") or b""
            registro["bytes"] = len(conteudo)
            registro["mime_type"] = _content_type(response)

            if conteudo.startswith(b"%PDF"):
                texto, status = extrair_texto_pdf_bytes(conteudo, max_chars=max_chars)
                registro["status"] = status
                registro["texto"] = texto
                if status == "pdf_parser_indisponivel":
                    registro["mensagem"] = (
                        "O documento é PDF e falta o leitor de PDF. Instale com: "
                        'python -m pip install "nanojud[pdf]"'
                    )
                registro["texto_chars"] = len(texto)
                registro["truncado"] = bool(max_chars and len(texto) >= max_chars)
            else:
                texto = _texto_resposta_nao_pdf(response, max_chars=max_chars)
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


MARCA_SESSAO_EXPIRADA = "sua sessão expirou"


def preparar_documentos(
    session: requests.Session,
    numero: str,
    movimentos: list[dict[str, Any]],
    limite: int = 0,
) -> None:
    """Deixa a sessão apta a abrir as pastas digitais dos documentos que serão lidos.

    O eSAJ só libera um documento na sessão que abriu o processo e carregou a página de
    movimentações onde ele aparece; o ticket guardado em um extrato salvo (JSON) já
    venceu. Sem isso a pasta devolve "sessão expirou" ou fica sem conteúdo.
    """
    docs = list(iterar_docs_publicos(movimentos))
    alvo = {d.get("cd_documento", "") for d in (docs[:limite] if limite else docs)}
    for doc in docs:
        doc.pop("pasta_digital", None)
    response = carregar_pagina(session, numero)
    if alvo and BeautifulSoup(response.text, "html.parser").find(id="btnExibirMovimentacoes"):
        carregar_movimentacoes_ajax(
            session,
            codigo_para_movimentacoes(response.text, response.url),
            limite=None,
            ate_documentos=alvo,
        )


def _texto_resposta_nao_pdf(response: Any, max_chars: int) -> str:
    texto = getattr(response, "text", "") or ""
    if not texto:
        conteudo = getattr(response, "content", b"") or b""
        texto = conteudo.decode("utf-8", errors="replace")
    if BeautifulSoup is not None and "<" in texto and ">" in texto:
        texto = BeautifulSoup(texto, "html.parser").get_text(" ", strip=True)
    texto = limpar(texto)
    return texto[:max_chars] if max_chars else texto


def _content_type(response: Any) -> str:
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("Content-Type") or headers.get("content-type") or "")


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
) -> Extrato:
    session = session or criar_session(timeout=timeout or 30.0)
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

    documentos = {
        "publicos_candidatos_unicos": list(documentos_unicos.values()),
        "restritos_por_senha_unicos": list(restritos_unicos.values()),
    }
    if inspecionar_pecas:
        documentos["pecas_publicas_inspecionadas"] = inspecionar_pecas_publicas(
            session, movimentos, limite_inspecao_pecas
        )
    if baixar_pecas:
        destino = pasta_pecas or Path.cwd() / "esaj_pecas"
        try:
            documentos["baixados"] = baixar_pecas_publicas(
                session, movimentos, destino, limite_pecas
            )
        except DownloadIndisponivel:
            raise
        except Exception as exc:  # pragma: no cover - depende de fonte externa
            raise DownloadIndisponivel(str(exc)) from exc

    return {
        "status": "ok",
        "mensagem": "Extrato gerado com sucesso",
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
            "data_coleta": datetime.now(timezone.utc).isoformat(),
        },
        "dados_basicos": dados_basicos,
        "partes": extrair_partes(soup),
        "movimentacoes": movimentos,
        "peticoes_diversas": extrair_peticoes_diversas(soup),
        "audiencias": extrair_audiencias(soup),
        "documentos": documentos,
        "relacionados": extrair_relacionados(soup),
    }
