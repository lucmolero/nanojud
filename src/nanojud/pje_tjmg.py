"""Consulta pública de processos no PJe de primeiro grau do TJMG.

O portal usa JSF/RichFaces. Este adaptador reproduz o postback declarado pela própria
página, falha fechado se o fluxo público passar a exigir reCAPTCHA e marca como parcial
qualquer resultado cuja paginação não foi percorrida.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import esaj
from .exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado, URLInvalida
from .normalization import normalizar_data, normalizar_texto_extraido
from .utils import (
    limpar,
    tamanho_pdf_existente_valido,
    validar_inteiro,
    validar_numero_cnj,
    validar_prazo_total,
    validar_timeout,
)
from .version import __version__

PJE_ORIGIN = "https://pje-consulta-publica.tjmg.jus.br"
PJE_LOGIN_URL = f"{PJE_ORIGIN}/pje/login.seam"
PJE_DETAIL_PREFIX = "/pje/ConsultaPublica/DetalheProcessoConsultaPublica/"
PJE_DOCUMENT_PATH = f"{PJE_DETAIL_PREFIX}documentoSemLoginHTML.seam"
INTERVALO_REQUISICOES = 1.0
PRAZO_TOTAL = 60.0
MAX_DOCUMENT_BYTES = 128 * 1024 * 1024
MAX_EMBEDDED_DOCUMENT_BYTES = esaj.MAX_IN_MEMORY_DOCUMENT_BYTES
MAX_PAGINAS_POR_TABELA = 100
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


def _pausar(deadline: float | None = None) -> None:
    """Aplica uma pausa global conservadora entre requests ao host do TJMG."""
    global _LAST_REQUEST_AT
    with _RATE_LOCK:
        decorrido = time.monotonic() - _LAST_REQUEST_AT
        if _LAST_REQUEST_AT and decorrido < INTERVALO_REQUISICOES:
            espera = INTERVALO_REQUISICOES - decorrido
            if deadline is not None:
                restante = deadline - time.monotonic()
                if restante <= 0:
                    raise ConsultaIndisponivel("Prazo total da consulta PJe/TJMG excedido.")
                espera = min(espera, restante)
            time.sleep(espera)
        if deadline is not None and time.monotonic() >= deadline:
            raise ConsultaIndisponivel("Prazo total da consulta PJe/TJMG excedido.")
        _LAST_REQUEST_AT = time.monotonic()


def _sessao(session: requests.Session | None) -> requests.Session:
    if session is not None:
        return session
    criada = requests.Session()
    criada.headers.update(
        {
            "User-Agent": f"Mozilla/5.0 (compatible; nanojud/{__version__}; +https://github.com/lucmolero/nanojud)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return criada


def criar_sessao() -> requests.Session:
    """Cria uma sessão HTTP com cabeçalhos padrão para o PJe/TJMG público."""
    return _sessao(None)


def _request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    deadline: float | None = None,
    **kwargs: Any,
) -> requests.Response:
    _validar_url_tjmg(url)
    timeout = validar_timeout(timeout)
    _pausar(deadline)
    if deadline is not None:
        restante = deadline - time.monotonic()
        if restante <= 0:
            raise ConsultaIndisponivel("Prazo total da consulta PJe/TJMG excedido.")
        timeout = min(timeout, restante)
    try:
        response = getattr(session, method.lower())(url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(
            f"Falha de comunicação com o PJe/TJMG: {type(exc).__name__}."
        ) from exc
    if deadline is not None and time.monotonic() >= deadline:
        raise ConsultaIndisponivel("Prazo total da consulta PJe/TJMG excedido.")
    status = response.status_code
    if status in {401, 403}:
        raise AcessoRestrito(f"PJe/TJMG retornou HTTP {status}.")
    if status == 404:
        raise ProcessoNaoEncontrado("Página pública do PJe/TJMG não encontrada.")
    if status == 429 or status >= 500:
        raise ConsultaIndisponivel(f"PJe/TJMG retornou HTTP {status}.")
    if status >= 400:
        raise ConsultaIndisponivel(f"PJe/TJMG retornou HTTP {status}.")
    return response


def _validar_url_tjmg(url: str, *, prefixo: str = "/pje/") -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != urlparse(PJE_ORIGIN).hostname:
        raise URLInvalida("A URL deve pertencer ao host HTTPS oficial do PJe/TJMG.")
    if not parsed.path.startswith(prefixo):
        raise URLInvalida("A rota não pertence à consulta pública do PJe/TJMG.")


def _captcha_desativado(html: str) -> bool:
    """Aceita somente a forma exata do fluxo sem desafio observada no portal."""
    if len(re.findall(r"function\s+executarReCaptcha\s*\(", html)) != 1:
        return False
    return bool(
        re.search(
            r"function\s+executarReCaptcha\s*\(\s*\)\s*\{\s*"
            r"if\s*\(\s*false\s*\)\s*\{\s*"
            r"grecaptcha\.execute\s*\(\s*\)\s*;\s*return\s+false\s*;\s*\}\s*"
            r"executarPesquisa\s*\(\s*\)\s*;\s*\}",
            html,
            re.S,
        )
    )


def _extrair_evento_busca(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Lê o evento A4J/JSF gerado pelo formulário em vez de fixar IDs do portal."""
    scripts = soup.find_all("script")
    scripts.sort(key=lambda script: "executarPesquisa" not in script.get_text())
    for script in scripts:
        conteudo = script.get_text()
        marcador = re.search(
            r"['\"]parameters['\"]\s*:\s*\{\s*['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]",
            conteudo,
        )
        action = re.search(r"['\"]actionUrl['\"]\s*:\s*['\"]([^'\"]+)['\"]", conteudo)
        origem = re.search(r"A4J\.AJAX\.Submit\(['\"]([^'\"]+)['\"]", conteudo)
        if marcador and action and origem:
            identificador_form = origem.group(1)
            if identificador_form != "fPP" or "ajaxSingle" in conteudo:
                continue
            caminho = re.sub(
                r"\\x([0-9a-fA-F]{2})",
                lambda match: chr(int(match.group(1), 16)),
                action.group(1),
            )
            parametro, valor = marcador.groups()
            if parametro != valor or not parametro.startswith("fPP:"):
                continue
            return identificador_form, parametro, caminho
    raise ConsultaIndisponivel("O formulário público do PJe/TJMG mudou o postback JSF esperado.")


def _campos_formulario(form: Any) -> dict[str, str]:
    campos: dict[str, str] = {}
    radios_vistos: set[str] = set()
    radios_marcados: set[str] = {
        str(item.get("name")) for item in form.select('input[type="radio"][checked][name]')
    }
    for campo in form.select("input[name]"):
        nome = str(campo.get("name"))
        tipo = str(campo.get("type") or "text").lower()
        if tipo in {"submit", "button", "image", "file"}:
            continue
        if tipo in {"checkbox", "radio"}:
            if campo.has_attr("checked"):
                campos[nome] = str(campo.get("value") or "on")
                radios_vistos.add(nome)
            elif tipo == "radio" and nome not in radios_marcados and nome not in radios_vistos:
                campos[nome] = str(campo.get("value") or "on")
                radios_vistos.add(nome)
            continue
        campos[nome] = str(campo.get("value") or "")
    for campo in form.select("select[name]"):
        selecionada = campo.select_one("option[selected]") or campo.select_one("option")
        campos[str(campo.get("name"))] = str(selecionada.get("value") or "") if selecionada else ""
    for campo in form.select("textarea[name]"):
        campos[str(campo.get("name"))] = campo.get_text()
    return campos


def consultar_processo(
    numero: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    prazo_total: float | None = PRAZO_TOTAL,
) -> dict[str, Any]:
    """Consulta busca e páginas públicas do detalhe PJe/TJMG.

    Percorre até 100 páginas por tabela e marca o resultado parcial quando a
    paginação falha, não pode ser verificada ou excede o limite. A função não tenta
    resolver nem contornar desafios do portal.
    """
    timeout = validar_timeout(timeout)
    validar_prazo_total(prazo_total)
    numero_cnj = validar_numero_cnj(numero, segmento="8", tribunal="13")
    deadline = time.monotonic() + prazo_total if prazo_total is not None else None
    sessao = _sessao(session)
    pagina = _request(sessao, "GET", PJE_LOGIN_URL, timeout=timeout, deadline=deadline)
    soup = BeautifulSoup(pagina.content, "html.parser")
    if not _captcha_desativado(pagina.text):
        raise AcessoRestrito(
            "O PJe/TJMG não confirmou que o reCAPTCHA está desativado neste fluxo; "
            "use a consulta oficial sem contornar o desafio."
        )
    form = soup.find("form", id="fPP")
    if form is None:
        raise ConsultaIndisponivel(
            "O formulário público de pesquisa do PJe/TJMG não foi encontrado."
        )
    campos = _campos_formulario(form)
    campo_numero = next(
        (nome for nome in campos if nome.endswith("numProcesso-inputNumeroProcesso")), None
    )
    if campo_numero is None:
        raise ConsultaIndisponivel("O formulário do PJe/TJMG não contém o campo de número CNJ.")
    campos[campo_numero] = numero_cnj
    try:
        form_id, evento, action_path = _extrair_evento_busca(soup)
    except ConsultaIndisponivel:
        raise
    action_url = urljoin(pagina.url, action_path)
    _validar_url_tjmg(action_url, prefixo="/pje/ConsultaPublica/")
    campos[form_id] = form_id
    campos[evento] = evento
    campos["AJAXREQUEST"] = "_viewRoot"
    campos["AJAX:EVENTS_COUNT"] = "1"
    resultado = _request(
        sessao,
        "POST",
        action_url,
        timeout=timeout,
        deadline=deadline,
        data=campos,
        headers={
            "Referer": pagina.url,
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    resultados_soup = BeautifulSoup(resultado.content, "html.parser")
    tabela = resultados_soup.find("table", id=re.compile(r"processosTable$"))
    if tabela is None:
        texto = limpar(resultados_soup.get_text(" ", strip=True)).lower()
        if any(termo in texto for termo in ("nenhum processo", "não encontrado", "nao encontrado")):
            raise ProcessoNaoEncontrado(f"PJe/TJMG não encontrou o processo {numero_cnj}.")
        raise ConsultaIndisponivel(
            "A busca pública do PJe/TJMG não retornou a tabela de resultados."
        )
    link_detalhe = None
    for linha in tabela.select("tr"):
        if numero_cnj in linha.get_text(" ", strip=True):
            link_detalhe = linha.select_one('a[title="Ver Detalhes"]')
            if link_detalhe:
                break
    if link_detalhe is None:
        raise ProcessoNaoEncontrado(f"PJe/TJMG não retornou detalhe para {numero_cnj}.")
    href = _url_do_onclick(str(link_detalhe.get("onclick") or ""), pagina.url)
    detalhe_response = _request(
        sessao,
        "GET",
        href,
        timeout=timeout,
        deadline=deadline,
        headers={"Referer": resultado.url},
    )
    extrato = parse_detail_page(numero_cnj, detalhe_response.text, detalhe_response.url)
    return _percorrer_paginas(
        sessao, detalhe_response.text, detalhe_response.url, extrato, timeout, deadline
    )


def _url_do_onclick(onclick: str, base_url: str) -> str:
    destino = re.search(r"openPopUp\([^,]+,\s*['\"]([^'\"]+)['\"]", onclick)
    if not destino:
        raise ConsultaIndisponivel("O link público de detalhe do PJe/TJMG mudou de formato.")
    url = urljoin(base_url, destino.group(1))
    _validar_url_tjmg(url, prefixo=PJE_DETAIL_PREFIX)
    return url


def _valor_rotulado(soup: BeautifulSoup, rotulo: str) -> str:
    prefixo = normalizar_texto_extraido(rotulo).casefold()
    for celula in soup.select("td, th"):
        texto = limpar(celula.get_text(" ", strip=True))
        if texto.casefold().startswith(prefixo):
            return texto[len(rotulo) :].strip(" :\u00a0")
    return ""


def _paginas(slider: Any | None) -> int | None:
    if slider is None:
        return None
    direita = slider.select_one(".rich-inslider-right-num")
    if direita is None:
        return None
    try:
        paginas = int(limpar(direita.get_text()))
    except ValueError:
        return None
    return paginas if paginas > 0 else None


def _paginas_documentos(soup: BeautifulSoup) -> int | None:
    """Lê o paginador dos documentos ou confirma uma tabela completa pelo total visível."""
    sliders = soup.select(".rich-slider")
    if len(sliders) > 1:
        return _paginas(sliders[1])

    tabela = soup.find("table", id="j_id145:processoDocumentoGridTab")
    if tabela is None:
        return None
    painel = tabela.find_parent(class_="rich-panel-body")
    resumo = painel.select_one("span.pull-right.text-muted") if painel else None
    if resumo is None:
        return None
    encontrado = re.search(
        r"\b(\d+)\s+resultados?\s+encontrados?\b",
        limpar(resumo.get_text(" ", strip=True)),
        re.IGNORECASE,
    )
    if encontrado is None:
        return None
    total = int(encontrado.group(1))
    linhas = len(tabela.select("tr.rich-table-row"))
    return 1 if total == linhas else None


def _propriedade_js(texto: str, nome: str) -> str | None:
    padrao = rf"\\?'{re.escape(nome)}\\?'\s*:\s*\\?'([^']*)\\?'"
    encontrado = re.search(padrao, texto)
    if not encontrado:
        return None
    valor = encontrado.group(1).rstrip("\\")
    return re.sub(r"\\+x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), valor)


def _configurar_slider(soup: BeautifulSoup, indice: int) -> dict[str, Any] | None:
    sliders = soup.select(".rich-slider")
    if indice >= len(sliders):
        return None
    slider = sliders[indice]
    total = _paginas(slider)
    form = slider.find_parent("form")
    campo = slider.select_one("input.rich-inslider-field")
    slider_id = str(slider.get("id") or "")
    if total is None or form is None or campo is None or not slider_id:
        return None
    form_id = str(form.get("id") or "")
    if not form_id or not campo.get("name"):
        return None

    script = next(
        (
            item.get_text()
            for item in soup.find_all("script")
            if re.search(
                rf"Richfaces\.Slider\(\s*['\"]{re.escape(slider_id)}['\"]", item.get_text()
            )
        ),
        "",
    )
    action_url = _propriedade_js(script, "actionUrl")
    container_id = _propriedade_js(script, "containerId")
    evento = _propriedade_js(script, "similarityGroupingId")
    parametros = re.search(
        r"\\?'parameters\\?'\s*:\s*\{\\?'([^']+)\\?'\s*:\s*\\?'([^']*)\\?'",
        script,
    )
    if not action_url or not container_id or not evento or not parametros:
        return None
    action_url = re.sub(r"\\+x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), action_url)
    url = urljoin(PJE_ORIGIN, action_url)
    _validar_url_tjmg(url, prefixo=PJE_DETAIL_PREFIX)
    return {
        "form": form,
        "form_id": form_id,
        "field_name": str(campo.get("name")),
        "event_name": parametros.group(1).rstrip("\\"),
        "event_value": parametros.group(2).rstrip("\\"),
        "action_url": url,
        "container_id": container_id,
        "total_pages": total,
    }


def _conteudo_atualizacao(xml: str, container_id: str) -> tuple[str, str | None]:
    try:
        parcial = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ConsultaIndisponivel("O PJe/TJMG retornou um postback JSF inválido.") from exc
    update = next(
        (
            item
            for item in parcial.iter()
            if item.tag.rsplit("}", 1)[-1] == "update" and item.get("id") == container_id
        ),
        None,
    )
    if update is None:
        raise ConsultaIndisponivel(
            "O PJe/TJMG não retornou a atualização esperada da página do slider."
        )
    fragmento = update.text or ""
    estado = next(
        (
            item
            for item in parcial.iter()
            if item.tag.rsplit("}", 1)[-1] == "update" and item.get("id") == "javax.faces.ViewState"
        ),
        None,
    )
    novo_estado = (estado.text or "").strip() if estado is not None else None
    return fragmento, novo_estado


def _extrair_pagina_resposta(
    conteudo: str,
    configuracao: dict[str, Any],
    tabela_id: str,
    pagina_esperada: int,
) -> tuple[Any | None, str | None]:
    """Lê uma atualização JSF parcial ou a página HTML completa devolvida pelo portal."""
    if re.match(r"(?:<\?xml[^>]*>\s*)?<partial-response\b", conteudo.lstrip()):
        fragmento, view_state = _conteudo_atualizacao(conteudo, configuracao["container_id"])
        soup = BeautifulSoup(fragmento, "html.parser")
        campo = soup.find("input", attrs={"name": configuracao["field_name"]})
        if campo is None or str(campo.get("value") or "") != str(pagina_esperada):
            raise ConsultaIndisponivel("O slider não confirmou a página solicitada.")
        tabela = soup.find("table", id=tabela_id)
        return tabela, view_state

    soup = BeautifulSoup(conteudo, "html.parser")
    campo = soup.find("input", attrs={"name": configuracao["field_name"]})
    if campo is None or str(campo.get("value") or "") != str(pagina_esperada):
        raise ConsultaIndisponivel("O slider não confirmou a página solicitada.")
    formulario = campo.find_parent("form")
    view_state = None
    if formulario is not None:
        estado = formulario.find("input", attrs={"name": "javax.faces.ViewState"})
        if estado is not None:
            view_state = str(estado.get("value") or "") or None
    return soup.find("table", id=tabela_id), view_state


def _percorrer_slider(
    session: requests.Session,
    html: str,
    url: str,
    indice: int,
    timeout: float,
    view_state: str | None,
    deadline: float | None,
) -> tuple[list[dict[str, Any]], int, int, str | None, str | None]:
    """Percorre páginas com o evento A4J declarado no slider público."""
    soup = BeautifulSoup(html, "html.parser")
    sliders = soup.select(".rich-slider")
    total = _paginas(sliders[indice]) if indice < len(sliders) else None
    if indice == 1 and total is None and _paginas_documentos(soup) == 1:
        return [], 1, 1, None, view_state
    if total is None:
        return [], 0, 0, "A quantidade de páginas do slider não foi identificada.", view_state
    if total == 1:
        return [], total, 1, None, view_state
    configuracao = _configurar_slider(soup, indice)
    if configuracao is None:
        return [], total, 1, "O slider público não expôs um postback JSF utilizável.", view_state
    limite = min(total, MAX_PAGINAS_POR_TABELA)
    lidas = 1
    itens: list[dict[str, Any]] = []
    formulario = configuracao["form"]
    campos_base = {"AJAXREQUEST": configuracao["container_id"]}
    campos_base.update(
        {
            nome: valor
            for nome, valor in _campos_formulario(formulario).items()
            if not nome.endswith((":_link_hidden_", ":j_idcl"))
        }
    )
    if view_state is not None:
        campos_base["javax.faces.ViewState"] = view_state
    tipo_tabela = "j_id145:processoEvento" if indice == 0 else "j_id145:processoDocumentoGridTab"

    for pagina_numero in range(2, limite + 1):
        campos = dict(campos_base)
        campos[configuracao["field_name"]] = str(pagina_numero)
        campos[configuracao["event_name"]] = configuracao["event_value"]
        campos["AJAX:EVENTS_COUNT"] = "1"
        try:
            resposta = _request(
                session,
                "POST",
                configuracao["action_url"],
                timeout=timeout,
                deadline=deadline,
                data=campos,
                headers={
                    "Referer": url,
                    "Accept": "*/*",
                },
            )
            tabela, novo_estado = _extrair_pagina_resposta(
                resposta.text, configuracao, tipo_tabela, pagina_numero
            )
        except (AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado) as exc:
            return itens, total, lidas, str(exc), view_state
        if tabela is None:
            return (
                itens,
                total,
                lidas,
                "A resposta do PJe/TJMG não continha a tabela da página solicitada.",
                view_state,
            )
        if indice == 0:
            itens_pagina = _extrair_movimentos(tabela, url)
        else:
            itens_pagina = _extrair_documentos(tabela, url)
        itens.extend(itens_pagina)
        if novo_estado is not None:
            view_state = novo_estado
            campos_base["javax.faces.ViewState"] = novo_estado
        lidas = pagina_numero

    aviso = None
    if total > MAX_PAGINAS_POR_TABELA:
        aviso = (
            f"O portal indica {total} páginas; o limite desta consulta é {MAX_PAGINAS_POR_TABELA}."
        )
    return itens, total, lidas, aviso, view_state


def _percorrer_paginas(
    session: requests.Session,
    html: str,
    url: str,
    extrato: dict[str, Any],
    timeout: float,
    deadline: float | None,
) -> dict[str, Any]:
    """Completa os sliders disponíveis e preserva a resposta parcial em falhas."""
    origem = extrato["origem"]
    view_state = None
    for indice, chave, nome_paginacao, completa, aviso_chave in (
        (0, "movimentacoes", "movimentacoes", "movimentacoes_completas", "aviso_movimentacoes"),
        (
            1,
            "publicos_candidatos_unicos",
            "documentos",
            "documentos_completos",
            "aviso_documentos",
        ),
    ):
        try:
            paginas, total, lidas, erro, view_state = _percorrer_slider(
                session, html, url, indice, timeout, view_state, deadline
            )
        except (AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado) as exc:
            paginas, total, lidas, erro = [], 1, 1, str(exc)
        origem[f"paginas_{nome_paginacao}_total"] = total
        origem[f"paginas_{nome_paginacao}_lidas"] = lidas
        if indice == 0:
            extrato["movimentacoes"].extend(paginas)
        else:
            existentes = extrato["documentos"][chave]
            _adicionar_documentos_unicos(existentes, paginas)
        origem[completa] = erro is None and lidas == total
        if origem[completa]:
            origem.pop(aviso_chave, None)
        else:
            detalhe = erro or f"Leu {lidas} de {total} páginas."
            origem[aviso_chave] = f"PJe/TJMG: paginação incompleta. {detalhe}"
    extrato["status"] = (
        "ok"
        if origem.get("movimentacoes_completas") is True
        and origem.get("documentos_completos") is True
        else "partial"
    )
    return extrato


def _adicionar_documentos_unicos(
    existentes: list[dict[str, Any]], novos: list[dict[str, Any]]
) -> None:
    """Acrescenta documentos mantendo unicidade entre e dentro das páginas."""
    ids = {str(item.get("cd_documento") or item.get("href")) for item in existentes}
    for item in novos:
        identificador = str(item.get("cd_documento") or item.get("href"))
        if identificador not in ids:
            existentes.append(item)
            ids.add(identificador)


def _url_documento(onclick: str, base_url: str) -> str:
    destino = re.search(r"openPopUp\([^,]+,\s*['\"]([^'\"]+)['\"]", onclick)
    if not destino:
        return ""
    url = urljoin(base_url, destino.group(1))
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != urlparse(PJE_ORIGIN).hostname
        or parsed.path != PJE_DOCUMENT_PATH
    ):
        return ""
    return url


def parse_detail_page(numero: str, html: str, url_final: str) -> dict[str, Any]:
    """Normaliza a primeira página observada do detalhe público do PJe/TJMG."""
    _validar_url_tjmg(url_final, prefixo=PJE_DETAIL_PREFIX)
    soup = BeautifulSoup(html, "html.parser")
    tabela_mov = soup.find("table", id="j_id145:processoEvento")
    if tabela_mov is None:
        raise ProcessoNaoEncontrado("O detalhe público não contém a tabela de movimentações.")
    tabela_docs = soup.find("table", id="j_id145:processoDocumentoGridTab")
    sliders = soup.select(".rich-slider")
    total_paginas_mov = _paginas(sliders[0] if sliders else None)
    total_paginas_docs = _paginas_documentos(soup)
    movimentos = _extrair_movimentos(tabela_mov, url_final)
    documentos = _extrair_documentos(tabela_docs, url_final)
    avisos = []
    if total_paginas_mov is None:
        avisos.append("PJe/TJMG não foi possível verificar a paginação das movimentações.")
    elif total_paginas_mov > 1:
        avisos.append(
            f"PJe/TJMG indica {total_paginas_mov} páginas de movimentações; "
            "esta consulta leu somente a primeira."
        )
    aviso_docs = ""
    if total_paginas_docs is None:
        aviso_docs = "PJe/TJMG não foi possível verificar a paginação dos documentos."
    elif total_paginas_docs > 1:
        aviso_docs = (
            f"PJe/TJMG indica {total_paginas_docs} páginas de documentos; "
            "esta consulta listou somente a primeira."
        )
    completo = total_paginas_mov == 1 and total_paginas_docs == 1
    orgao_julgador = _valor_rotulado(soup, "Órgão Julgador")
    dados_basicos = {
        "numero": numero,
        "classe": _valor_rotulado(soup, "Classe Judicial"),
        "assunto": _valor_rotulado(soup, "Assunto"),
        "orgao_julgador": orgao_julgador,
        "foro": orgao_julgador,
        "vara": _valor_rotulado(soup, "Unidade Judiciária"),
    }
    origem: dict[str, Any] = {
        "sistema": "PJe",
        "tribunal": "TJMG",
        "grau": "1º grau",
        "consulta": "publica",
        "entrada": numero,
        "url_final": url_final,
        "data_coleta": datetime.now(UTC).isoformat(),
        "movimentacoes_completas": total_paginas_mov == 1,
        "documentos_completos": total_paginas_docs == 1,
    }
    if total_paginas_docs == 1:
        origem["paginas_documentos_total"] = 1
        origem["paginas_documentos_lidas"] = 1
    if avisos:
        origem["aviso_movimentacoes"] = " ".join(avisos)
    if aviso_docs:
        origem["aviso_documentos"] = aviso_docs
    return {
        "status": "ok" if completo and not aviso_docs else "partial",
        "origem": origem,
        "dados_basicos": dados_basicos,
        "movimentacoes": movimentos,
        "documentos": {"publicos_candidatos_unicos": documentos},
    }


def _extrair_movimentos(tabela: Any, url_final: str) -> list[dict[str, Any]]:
    saida = []
    for linha in tabela.select("tr"):
        celulas = linha.find_all("td", recursive=False)
        if not celulas:
            continue
        texto = limpar(celulas[0].get_text(" ", strip=True))
        data_bruta = re.match(
            r"(\d{2}/\d{2}/\d{4})(?:\s+\d{2}:\d{2}(?::\d{2})?)?\s*[-–:]?\s*(.*)", texto
        )
        if not data_bruta:
            continue
        data = normalizar_data(data_bruta.group(1))
        titulo = limpar(data_bruta.group(2))
        movimento: dict[str, Any] = {
            "data": data["iso"],
            "data_original": data["original"],
            "titulo": titulo,
            "teor": titulo,
            "documentos": [],
        }
        if len(celulas) > 1:
            documentos = _extrair_documentos(celulas[1], url_final)
            movimento["documentos"] = documentos
        saida.append(movimento)
    return saida


def _extrair_documentos(tabela: Any | None, url_final: str) -> list[dict[str, Any]]:
    if tabela is None:
        return []
    saida = []
    vistos: set[str] = set()
    for link in tabela.select('a[title="Visualizar"]'):
        href = _url_documento(link.get("onclick", ""), url_final)
        if not href or href in vistos:
            continue
        vistos.add(href)
        titulo = limpar(link.get_text(" ", strip=True) or link.get("title") or "Documento")
        dados = parse_qs(urlparse(href).query)
        saida.append(
            {
                "titulo": titulo,
                "href": href,
                "cd_documento": (dados.get("idProcessoDoc") or [""])[0],
                "status_acesso": "publico_candidato",
            }
        )
    return saida


def ler_documento_publico(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Gera e lê o PDF pelo botão oficial da página pública de documentos."""
    max_chars = validar_inteiro(max_chars, nome="max_chars", minimo=0)
    pdf = _gerar_pdf_publico(
        url,
        session=session,
        timeout=timeout,
        max_bytes=MAX_EMBEDDED_DOCUMENT_BYTES,
    )
    texto, status = esaj.extrair_texto_pdf_bytes(pdf, max_chars=max_chars)
    resultado = {
        "status": status,
        "mime_type": "application/pdf",
        "bytes": len(pdf),
        "texto": texto,
        "texto_chars": len(texto),
        "truncado": bool(max_chars and len(texto) >= max_chars),
    }
    mensagem = esaj.mensagem_status_extracao_pdf(status)
    if mensagem:
        resultado["mensagem"] = mensagem
    return resultado


def obter_pdf_publico(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    max_bytes: int = MAX_EMBEDDED_DOCUMENT_BYTES,
) -> bytes:
    """Obtém bytes de um PDF público com limite adequado a uma resposta MCP."""
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= MAX_DOCUMENT_BYTES
    ):
        raise ValueError(f"max_bytes deve estar entre 1 e {MAX_DOCUMENT_BYTES}.")
    return _gerar_pdf_publico(
        url,
        session=session,
        timeout=timeout,
        max_bytes=max_bytes,
    )


def _gerar_pdf_publico(
    url: str,
    *,
    session: requests.Session | None,
    timeout: float,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> bytes:
    _validar_url_documento(url)
    sessao = _sessao(session)
    pagina = _request(sessao, "GET", url, timeout=timeout)
    soup = BeautifulSoup(pagina.content, "html.parser")
    botao = soup.find(id="j_id41:downloadPDF")
    if botao is None:
        raise AcessoRestrito("O PJe/TJMG não ofereceu o botão público de geração do PDF.")
    script = str(botao.get("onclick") or "")
    chamada = re.search(
        r"jsfcljs\(document\.getElementById\(['\"]([^'\"]+)['\"]\),\s*(\{.*?\}),\s*['\"]{2}\s*\)",
        script,
        re.S,
    )
    if not chamada:
        raise ConsultaIndisponivel("O botão público de PDF do PJe/TJMG mudou de formato.")
    form = soup.find("form", id=chamada.group(1))
    if form is None:
        raise ConsultaIndisponivel("O formulário de geração do PDF do PJe/TJMG não foi encontrado.")
    campos = _campos_formulario(form)
    pares = re.findall(r"['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]*)['\"]", chamada.group(2))
    campos.update(dict(pares))
    destino = urljoin(pagina.url, str(form.get("action") or pagina.url))
    _validar_url_tjmg(destino, prefixo=PJE_DETAIL_PREFIX)
    resposta = _request(
        sessao,
        "POST",
        destino,
        timeout=timeout,
        data=campos,
        headers={"Referer": pagina.url},
        stream=True,
    )
    content_length = str(resposta.headers.get("Content-Length", ""))
    if content_length.isdigit() and int(content_length) > max_bytes:
        resposta.close()
        raise ConsultaIndisponivel("O PDF público excede o limite de tamanho solicitado.")
    corpo = bytearray()
    try:
        for bloco in resposta.iter_content(chunk_size=64 * 1024):
            if len(corpo) + len(bloco) > max_bytes:
                raise ConsultaIndisponivel("O PDF público excede o limite de tamanho solicitado.")
            corpo.extend(bloco)
    finally:
        resposta.close()
    pdf = bytes(corpo)
    if not pdf.startswith(b"%PDF-"):
        raise AcessoRestrito("O PJe/TJMG não retornou um PDF público para este documento.")
    return pdf


def _validar_url_documento(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != urlparse(PJE_ORIGIN).hostname
        or parsed.path != PJE_DOCUMENT_PATH
    ):
        raise URLInvalida("Informe o link HTTPS de documento público do PJe/TJMG.")


def baixar_documento_publico(
    url: str,
    destino: Path,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    sobrescrever: bool = False,
) -> dict[str, Any]:
    """Baixa atomicamente um PDF que o portal apresenta como documento público."""
    _validar_url_documento(url)
    if not sobrescrever:
        tamanho_existente = tamanho_pdf_existente_valido(destino, MAX_DOCUMENT_BYTES)
        if tamanho_existente is not None:
            return {"status": "existente", "arquivo": str(destino), "bytes": tamanho_existente}
    pagina = _baixar_pdf(url, session=session, timeout=timeout)
    destino.parent.mkdir(parents=True, exist_ok=True)
    descritor, caminho_temporario = tempfile.mkstemp(
        prefix=f".{destino.name}.", suffix=".part", dir=destino.parent
    )
    temporario = Path(caminho_temporario)
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(pagina)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        if sobrescrever:
            temporario.replace(destino)
        else:
            try:
                os.link(temporario, destino)
            except FileExistsError:
                tamanho_existente = tamanho_pdf_existente_valido(destino, MAX_DOCUMENT_BYTES)
                if tamanho_existente is not None:
                    return {
                        "status": "existente",
                        "arquivo": str(destino),
                        "bytes": tamanho_existente,
                    }
                temporario.replace(destino)
        return {"status": "baixado", "arquivo": str(destino), "bytes": len(pagina)}
    finally:
        temporario.unlink(missing_ok=True)


def _baixar_pdf(url: str, *, session: requests.Session | None, timeout: float) -> bytes:
    """Executa a mesma ação oficial usada por leitura e download."""
    return _gerar_pdf_publico(url, session=session, timeout=timeout)
