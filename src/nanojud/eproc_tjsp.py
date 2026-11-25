"""Consultas públicas eproc/TJSP de primeiro e segundo graus."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado
from .normalization import normalizar_data
from .utils import limpar, validar_numero_cnj, validar_timeout

PORTAL_1G_URL = "https://eproc1g.tjsp.jus.br/eproc"
PORTAL_2G_URL = "https://eproc2g-consulta.tjsp.jus.br/eproc/"
HOST = "eproc-consulta.tjsp.jus.br"
HOST_2G = "eproc2g-consulta.tjsp.jus.br"
MAX_EVENTOS = 2000
TEMPO_MAXIMO_VERIFICACAO_CITIZEN_MS = 30_000
SELETOR_DESAFIO = ".cf-turnstile, [id^='cf-chl-widget'], iframe[src*='challenges.cloudflare.com']"
GrauEproc = Literal["1G", "2G"]


def _url_de_autenticacao_tjsp(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "sso.tjsp.jus.br"
        and parsed.path.startswith("/realms/eproc/protocol/openid-connect/auth")
    )


def _validar_url(url: str, *, grau: GrauEproc = "1G") -> None:
    if _url_de_autenticacao_tjsp(url):
        raise AcessoRestrito(
            f"O eproc/TJSP {grau} redirecionou para a autenticação do TJSP "
            "sem apresentar o resultado processual."
        )
    parsed = urlparse(url)
    host_esperado = HOST if grau == "1G" else HOST_2G
    if parsed.scheme != "https" or parsed.hostname != host_esperado:
        raise ConsultaIndisponivel("A navegação saiu do host oficial de consulta eproc/TJSP.")


def _texto_rotulado(soup: BeautifulSoup, rotulo: str) -> str:
    for item in soup.select("[id^='lbl']"):
        if limpar(item.get_text(" ", strip=True)).casefold() == rotulo.casefold():
            sibling = item.find_next_sibling()
            if sibling:
                return limpar(sibling.get_text(" ", strip=True))
            parent = item.parent
            if parent:
                return limpar(parent.get_text(" ", strip=True)).removeprefix(rotulo).strip(" :")
    return ""


def _pagina_tem_desafio_interativo(html: str) -> bool:
    """Identifica um desafio visível sem confundir sua biblioteca com o desafio."""
    soup = BeautifulSoup(html, "html.parser")
    texto = limpar(soup.get_text(" ", strip=True)).casefold()
    if _pagina_bloqueada_cloudflare(html):
        return True
    if any(
        marcador in texto
        for marcador in (
            "captcha verification",
            "verify you are human",
            "verifique que você é humano",
            "verificação de segurança",
            "checking your browser",
        )
    ):
        return True
    resposta_turnstile = soup.select_one("input[name='cf-turnstile-response']")
    if resposta_turnstile and resposta_turnstile.get("value"):
        return False
    if soup.select_one(SELETOR_DESAFIO):
        return True
    return False


def _pagina_bloqueada_cloudflare(html: str) -> bool:
    """Detecta páginas finais de bloqueio, sem inferir bloqueio por scripts ou Ray ID isolado."""
    texto = limpar(BeautifulSoup(html, "html.parser").get_text(" ", strip=True)).casefold()
    return any(
        marcador in texto
        for marcador in (
            "sorry, you have been blocked",
            "you have been blocked",
            "you are unable to access",
            "attention required! | cloudflare",
            "error 1020: access denied",
            "automated requests have been blocked",
            "bot detected",
        )
    )


def _verificar_alerta_consulta(mensagem: str, grau: GrauEproc) -> bool:
    """Classifica alertas e sinaliza quando o portal pede espera passiva."""
    texto = limpar(mensagem).casefold()
    if not texto:
        return False
    if any(
        marcador in texto
        for marcador in (
            "sorry, you have been blocked",
            "you have been blocked",
            "attention required! | cloudflare",
            "error 1020: access denied",
            "bot detected",
        )
    ):
        raise AcessoRestrito(f"O Cloudflare bloqueou a sessão eproc/TJSP {grau} como automatizada.")
    if "captcha" in texto or any(
        marcador in texto
        for marcador in (
            "verify you are human",
            "verifique que você é humano",
            "verificação de segurança",
            "checking your browser",
        )
    ):
        if "captcha" in texto and any(
            marcador in texto for marcador in ("aguarde", "aguardando", "waiting")
        ):
            return True
        raise AcessoRestrito(f"O eproc/TJSP {grau} solicitou uma verificação interativa.")
    if any(
        marcador in texto for marcador in ("nenhum processo", "não encontrado", "nao encontrado")
    ):
        raise ProcessoNaoEncontrado("O eproc/TJSP não encontrou o processo consultado.")
    if any(
        marcador in texto for marcador in ("segredo de justiça", "segredo de justica", "sigilo")
    ):
        raise AcessoRestrito(
            "O eproc/TJSP não exibe o andamento deste processo na consulta pública."
        )
    raise ConsultaIndisponivel("O eproc/TJSP exibiu um aviso durante a consulta pública.")


def _capturar_alertas(page: Any) -> dict[str, str]:
    """Captura e dispensa alertas do navegador sem perder sua semântica."""
    alerta = {"mensagem": ""}

    def tratar_dialogo(dialog: Any) -> None:
        alerta["mensagem"] = limpar(dialog.message)
        dialog.dismiss()

    page.on("dialog", tratar_dialogo)
    return alerta


def _verificar_alerta_capturado(alerta: dict[str, str], grau: GrauEproc) -> bool:
    mensagem = alerta["mensagem"]
    alerta["mensagem"] = ""
    return _verificar_alerta_consulta(mensagem, grau)


def _aguardar_resultado(
    page: Any,
    *,
    timeout_ms: float,
    seletor_adicional: str = "",
    desafio_pendente: bool = False,
    grau: GrauEproc = "1G",
    aguardar_desafio_interativo: bool = False,
) -> None:
    """Aguarda resultado e dá prazo curto à verificação automática do navegador."""
    resultado = ", ".join(
        seletor
        for seletor in (
            "table:has(th:text-matches('Data/Hora', 'i')), "
            "body:has-text('nenhum processo'), body:has-text('não encontrado'), "
            "body:has-text('not found')",
            seletor_adicional,
        )
        if seletor
    )
    html_atual = page.content()
    desafio_presente = bool(page.locator(SELETOR_DESAFIO).count()) or (
        _pagina_tem_desafio_interativo(html_atual)
    )
    limite_ms = (
        timeout_ms
        if aguardar_desafio_interativo
        else min(timeout_ms, TEMPO_MAXIMO_VERIFICACAO_CITIZEN_MS)
        if desafio_pendente or desafio_presente
        else timeout_ms
    )
    try:
        page.locator(resultado).first.wait_for(state="visible", timeout=limite_ms)
    except Exception as exc:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        if not isinstance(exc, PlaywrightTimeoutError):
            raise
        try:
            html_atual = page.content()
        except Exception:
            html_atual = ""
        url_atual = str(getattr(page, "url", ""))
        if _pagina_bloqueada_cloudflare(html_atual):
            raise AcessoRestrito(
                f"O Cloudflare bloqueou a sessão eproc/TJSP {grau} como automatizada."
            ) from exc
        if _url_de_autenticacao_tjsp(url_atual):
            tem_desafio = _pagina_tem_desafio_interativo(html_atual)
            if tem_desafio:
                raise AcessoRestrito(
                    f"O eproc/TJSP {grau} terminou na autenticação do TJSP com "
                    "verificação interativa, sem apresentar o resultado processual."
                ) from exc
            raise AcessoRestrito(
                f"O eproc/TJSP {grau} redirecionou para a autenticação do TJSP "
                "sem apresentar o resultado processual."
            ) from exc
        if _pagina_tem_desafio_interativo(html_atual):
            raise AcessoRestrito(
                f"O eproc/TJSP {grau} não concluiu a verificação dentro do prazo de "
                f"{limite_ms / 1000:g} segundos."
            ) from exc
        raise


def parse_resultado(numero: str, html: str, url: str, *, grau: GrauEproc = "1G") -> dict[str, Any]:
    """Normaliza a capa e os eventos renderizados na consulta pública."""
    _validar_url(url, grau=grau)
    soup = BeautifulSoup(html, "html.parser")
    tabela = next(
        (
            table
            for table in soup.find_all("table")
            if "Data/Hora" in table.get_text(" ", strip=True)
        ),
        None,
    )
    confirmado = limpar(soup.get_text(" ", strip=True))
    if tabela is None:
        if any(texto in confirmado.casefold() for texto in ("nenhum processo", "não encontrado")):
            raise ProcessoNaoEncontrado(f"eproc/TJSP não encontrou o processo {numero}.")
        if _pagina_bloqueada_cloudflare(html):
            raise AcessoRestrito(
                f"O Cloudflare bloqueou a sessão eproc/TJSP {grau} como automatizada."
            )
        if _pagina_tem_desafio_interativo(html):
            raise AcessoRestrito(f"O eproc/TJSP {grau} solicitou uma verificação interativa.")
        raise ConsultaIndisponivel("O eproc/TJSP não apresentou a tabela de eventos esperada.")

    eventos: list[dict[str, Any]] = []
    for linha in tabela.select("tr")[1 : MAX_EVENTOS + 1]:
        celulas = linha.find_all("td", recursive=False)
        if len(celulas) < 5:
            continue
        ordem_texto = limpar(celulas[0].get_text(" ", strip=True))
        if not ordem_texto.isdigit():
            continue
        descricoes = [limpar(x) for x in celulas[2].stripped_strings]
        data_hora = limpar(celulas[1].get_text(" ", strip=True))
        data_normalizada = normalizar_data(data_hora)
        documentos = []
        for link in celulas[4].select("a[href]"):
            documentos.append(
                {
                    "titulo": limpar(link.get_text(" ", strip=True))
                    or limpar(str(link.get("title", ""))),
                    "href": urljoin(url, str(link.get("href", ""))),
                }
            )
        eventos.append(
            {
                "ordem": int(ordem_texto),
                "data": data_normalizada["iso"],
                "data_original": data_normalizada["original"],
                "data_hora": data_hora,
                "titulo": descricoes[0] if descricoes else "",
                "teor": " ".join(descricoes[1:]),
                "usuario": limpar(celulas[3].get_text(" ", strip=True)),
                "documentos": documentos,
            }
        )

    if not eventos:
        raise ConsultaIndisponivel(
            "A tabela eproc foi encontrada, mas nenhum evento pôde ser lido."
        )
    numeros_pagina = re.findall(r"\d{7}-\d{2}\.\d{4}\.8\.26\.\d{4}", confirmado)
    if numeros_pagina and numero not in numeros_pagina:
        raise ConsultaIndisponivel("O eproc retornou um processo diferente do número consultado.")
    if numero not in numeros_pagina:
        raise ConsultaIndisponivel("O eproc não confirmou o CNJ do processo na resposta.")

    basicos = {
        campo: valor
        for campo, rotulo in (
            ("distribuicao", "Data de autuação:"),
            ("situacao", "Situação:"),
            ("vara", "Órgão Julgador:"),
            ("juiz", "Juiz(a):"),
            ("classe", "Classe da ação:"),
        )
        if (valor := _texto_rotulado(soup, rotulo))
    }
    basicos["numero"] = numero
    eventos_completos = (
        parse_qs(urlparse(url).query).get("eventos", [""])[0].casefold() == "true"
        and len(eventos) < MAX_EVENTOS
    )
    return {
        "status": "ok" if eventos_completos else "partial",
        "mensagem": (
            f"Consulta pública eproc/TJSP de {grau} concluída."
            if eventos_completos
            else (
                f"Consulta eproc/TJSP {grau} concluída, "
                "mas a completude do histórico não foi confirmada."
            )
        ),
        "origem": {
            "sistema": "eproc",
            "tribunal": "TJSP",
            "grau": grau,
            "consulta": "pública",
            "entrada": numero,
            "url_final": urlunparse((*urlparse(url)[:4], "", "")),
            "data_coleta": datetime.now(UTC).isoformat(),
            "movimentacoes_completas": eventos_completos,
        },
        "dados_basicos": basicos,
        "movimentacoes": eventos,
    }


def consultar_processo_2g(
    numero: str,
    *,
    timeout: float = 30.0,
    headless: bool = False,
    aguardar_desafio_interativo: bool = False,
) -> dict[str, Any]:
    """Consulta a instalação pública eproc/TJSP de segundo grau.

    A entrada pública leva à Consulta Unificada, que oferece uma rota direta para
    o formulário eproc 2G. O número é enviado uma vez nesse formulário, e a função
    só retorna depois de encontrar os eventos processuais esperados.
    """
    numero_cnj = validar_numero_cnj(numero, segmento="8", tribunal="26")
    validar_timeout(timeout)
    if not isinstance(aguardar_desafio_interativo, bool):
        raise ValueError("aguardar_desafio_interativo deve ser booleano.")
    if aguardar_desafio_interativo and headless:
        raise ValueError("A espera por ação humana exige headless=False.")
    page: Any | None = None
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ConsultaIndisponivel(
            "Instale a dependência opcional com `pip install nanojud[autenticacao]`."
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                alerta = _capturar_alertas(page)
                page.set_default_timeout(timeout * 1000)
                page.goto(PORTAL_2G_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
                _validar_url(page.url, grau="2G")
                escolha_eproc = page.get_by_role("button", name="EPROC", exact=True)
                if not escolha_eproc.count():
                    raise ConsultaIndisponivel(
                        "O portal eproc/TJSP 2G não apresentou a consulta direta EPROC."
                    )
                escolha_eproc.click()
                page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
                _validar_url(page.url, grau="2G")

                campo_processo = page.locator("#numNrProcesso")
                consultar = page.locator("#divInfraBarraComandosSuperior #sbmConsultar")
                if not campo_processo.count() or not consultar.count():
                    raise ConsultaIndisponivel("O formulário de consulta pública eproc 2G mudou.")
                campo_processo.fill(numero_cnj)
                consultar.click()
                desafio_pendente = _verificar_alerta_capturado(alerta, "2G")
                page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
                _validar_url(page.url, grau="2G")
                _aguardar_resultado(
                    page,
                    timeout_ms=timeout * 1000,
                    desafio_pendente=desafio_pendente,
                    grau="2G",
                    aguardar_desafio_interativo=aguardar_desafio_interativo,
                )
                todos_eventos = page.locator("a").filter(
                    has_text=re.compile(r"listar todos os eventos", re.IGNORECASE)
                )
                if todos_eventos.count():
                    todos_eventos.first.click()
                    desafio_pendente = _verificar_alerta_capturado(alerta, "2G")
                    page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
                    _validar_url(page.url, grau="2G")
                    _aguardar_resultado(
                        page,
                        timeout_ms=timeout * 1000,
                        desafio_pendente=desafio_pendente,
                        grau="2G",
                        aguardar_desafio_interativo=aguardar_desafio_interativo,
                    )
                return parse_resultado(numero_cnj, page.content(), page.url, grau="2G")
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        html_atual = ""
        if page is not None:
            try:
                html_atual = page.content()
            except Exception:
                pass
        if _pagina_tem_desafio_interativo(html_atual):
            raise AcessoRestrito(
                "O eproc/TJSP 2G exige verificação interativa para concluir esta consulta."
            ) from exc
        raise ConsultaIndisponivel("Tempo esgotado na consulta pública eproc/TJSP 2G.") from exc


def consultar_processo(
    numero: str,
    *,
    timeout: float = 30.0,
    headless: bool = False,
    aguardar_desafio_interativo: bool = False,
) -> dict[str, Any]:
    """Consulta a interface pública com navegador Chromium instalado pelo Playwright.

    ``headless=False`` usa o fluxo normal do navegador. Com
    ``aguardar_desafio_interativo=True``, mantém a janela aberta até o timeout para
    que o operador conclua a verificação apresentada pelo portal; a biblioteca
    não interage com o desafio nem fabrica tokens.
    """
    numero_cnj = validar_numero_cnj(numero, segmento="8", tribunal="26")
    validar_timeout(timeout)
    if not isinstance(aguardar_desafio_interativo, bool):
        raise ValueError("aguardar_desafio_interativo deve ser booleano.")
    if aguardar_desafio_interativo and headless:
        raise ValueError("A espera por ação humana exige headless=False.")
    page: Any | None = None
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ConsultaIndisponivel(
            "Instale a dependência opcional com `pip install nanojud[autenticacao]`."
        ) from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                alerta = _capturar_alertas(page)
                page.set_default_timeout(timeout * 1000)
                page.goto(PORTAL_1G_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
                consulta_unificada = page.get_by_role("link", name="Consulta Unificada", exact=True)
                if not consulta_unificada.count():
                    raise ConsultaIndisponivel(
                        "O portal oficial eproc/TJSP não apresentou a Consulta Unificada."
                    )
                consulta_unificada.click()
                page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
                _validar_url(page.url)
                campo = page.locator("#txtNumProcesso")
                if not campo.count():
                    raise ConsultaIndisponivel("O formulário público eproc/TJSP mudou.")
                instancia = page.locator("#selInstancia")
                if not instancia.count():
                    raise ConsultaIndisponivel("O seletor de instância do eproc/TJSP mudou.")
                if instancia.input_value() != "SP":
                    instancia.select_option("SP")
                campo.fill(numero_cnj)
                page.locator("#sbmNovo").click()
                desafio_pendente = _verificar_alerta_capturado(alerta, "1G")
                page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
                _validar_url(page.url)
                _aguardar_resultado(
                    page,
                    timeout_ms=timeout * 1000,
                    desafio_pendente=desafio_pendente,
                    grau="1G",
                    aguardar_desafio_interativo=aguardar_desafio_interativo,
                )
                todos_eventos = page.locator("a").filter(
                    has_text=re.compile(r"listar todos os eventos", re.IGNORECASE)
                )
                if todos_eventos.count():
                    todos_eventos.first.click()
                    desafio_pendente = _verificar_alerta_capturado(alerta, "1G")
                    page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
                    _validar_url(page.url)
                    _aguardar_resultado(
                        page,
                        timeout_ms=timeout * 1000,
                        desafio_pendente=desafio_pendente,
                        grau="1G",
                        aguardar_desafio_interativo=aguardar_desafio_interativo,
                    )
                return parse_resultado(numero_cnj, page.content(), page.url)
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        html_atual = ""
        if page is not None:
            try:
                html_atual = page.content()
            except Exception:
                pass
        if _pagina_tem_desafio_interativo(html_atual):
            raise AcessoRestrito(
                "O eproc/TJSP exige verificação interativa para concluir esta consulta."
            ) from exc
        raise ConsultaIndisponivel("Tempo esgotado na consulta pública eproc/TJSP.") from exc
