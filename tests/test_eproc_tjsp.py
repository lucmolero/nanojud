import sys
from types import ModuleType

import pytest

from nanojud import eproc_tjsp
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado

CNJ = "1001194-30.2024.8.26.0114"
URL = "https://eproc-consulta.tjsp.jus.br/consulta_1g/externo_controlador.php?acao=detalhes"
URL_EVENTOS = f"{URL}&eventos=true"
HTML_EVENTOS_2G = (
    f"<span>{CNJ}</span><table><tr><th>Evento</th><th>Data/Hora</th><th>Descrição</th>"
    "<th>Usuário</th><th>Documentos</th></tr>"
    "<tr><td>1</td><td>11/11/2026 10:00</td><td>Distribuído</td>"
    "<td>SISTEMA</td><td></td></tr></table>"
)


def test_parse_resultado_le_capa_e_eventos_sem_baixar_documentos():
    html = f"""<html><body><span>{CNJ}</span>
      <span id="lblAutuacao">Data de autuação:</span><div>15/01/2024</div>
      <span id="lblSituacao">Situação:</span><div>MOVIMENTO</div>
      <span id="lblOrgaoJulgador">Órgão Julgador:</span><div>Vara Cível</div>
      <span id="lblClasse">Classe da ação:</span><div>Execução</div>
      <table><tr><th>Evento</th><th>Data/Hora</th><th>Descrição</th><th>Usuário</th><th>Documentos</th></tr>
      <tr><td>2</td><td>11/11/2026 11:27:19</td><td>Juntada de petição<span>Texto</span></td>
      <td>ABC</td><td><a href="/documento?id=123">Visualizar documento</a></td></tr></table>
    </body></html>"""
    resultado = eproc_tjsp.parse_resultado(CNJ, html, URL_EVENTOS)
    assert resultado["dados_basicos"]["numero"] == CNJ
    assert resultado["dados_basicos"]["classe"] == "Execução"
    assert resultado["status"] == "ok"
    assert resultado["origem"]["movimentacoes_completas"] is True
    assert "?" not in resultado["origem"]["url_final"]
    assert resultado["movimentacoes"][0]["titulo"] == "Juntada de petição"
    assert resultado["movimentacoes"][0]["data"] == "2026-11-11"
    assert resultado["movimentacoes"][0]["teor"] == "Texto"
    assert resultado["movimentacoes"][0]["documentos"][0]["href"].startswith("https://")


def test_parse_resultado_nao_presume_historico_completo_sem_marcador_do_portal():
    html = f"""<span>{CNJ}</span><table><tr><th>Data/Hora</th></tr><tr><td>1</td>
      <td>11/11/2026</td><td>Movimento</td><td>ABC</td><td></td></tr></table>"""
    resultado = eproc_tjsp.parse_resultado(CNJ, html, URL)
    assert resultado["status"] == "partial"
    assert resultado["origem"]["movimentacoes_completas"] is False


def test_parse_resultado_exige_confirmacao_do_cnj_na_resposta():
    html = """<table><tr><th>Data/Hora</th></tr><tr><td>1</td>
      <td>11/11/2026</td><td>Movimento</td><td>ABC</td><td></td></tr></table>"""
    with pytest.raises(ConsultaIndisponivel, match="não confirmou o CNJ"):
        eproc_tjsp.parse_resultado(CNJ, html, URL)


def test_parse_resultado_classifica_nao_encontrado():
    with pytest.raises(ProcessoNaoEncontrado):
        eproc_tjsp.parse_resultado(CNJ, "<p>Nenhum processo encontrado</p>", URL)


def test_parse_resultado_classifica_desafio_interativo():
    with pytest.raises(AcessoRestrito):
        eproc_tjsp.parse_resultado(CNJ, "<p>Captcha verification</p>", URL)


def test_parse_resultado_classifica_bloqueio_cloudflare_como_acesso_restrito():
    html = """<html><head><title>Sorry, you have been blocked</title></head>
      <body><h1>Sorry, you have been blocked</h1>
      <p>This website is using a security service to protect itself from bots.</p>
      <p>Cloudflare Ray ID: 1234567890</p></body></html>"""
    with pytest.raises(AcessoRestrito, match="Cloudflare bloqueou"):
        eproc_tjsp.parse_resultado(CNJ, html, URL)


def test_detector_reconhece_bloqueio_cloudflare_sem_challenge_widget():
    html = """<html><head><title>Attention Required! | Cloudflare</title></head>
      <body><h1>Sorry, you have been blocked</h1>
      <p>Cloudflare Ray ID: 1234567890</p></body></html>"""
    assert eproc_tjsp._pagina_tem_desafio_interativo(html) is True


def test_detector_reconhece_widget_turnstile_interativo():
    html = """<html><body>
      <div class="cf-turnstile" data-sitekey="public-site-key"></div>
      <iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/"></iframe>
    </body></html>"""
    assert eproc_tjsp._pagina_tem_desafio_interativo(html) is True


def test_alerta_javascript_de_captcha_vira_acesso_restrito():
    with pytest.raises(AcessoRestrito, match="verificação interativa"):
        eproc_tjsp._verificar_alerta_consulta("Resolva o captcha para continuar.", "2G")


def test_alerta_cloudflare_sem_palavra_captcha_vira_acesso_restrito():
    with pytest.raises(AcessoRestrito, match="verificação interativa"):
        eproc_tjsp._verificar_alerta_consulta("Checking your browser", "1G")


def test_alerta_de_sigilo_vira_acesso_restrito():
    with pytest.raises(AcessoRestrito, match="não exibe o andamento"):
        eproc_tjsp._verificar_alerta_consulta("Processo em segredo de justiça", "2G")


def test_alerta_aguarde_captcha_permite_resolucao_natural_limitada():
    assert eproc_tjsp._verificar_alerta_consulta("Aguarde a verificação do captcha.", "1G") is True


def test_alerta_javascript_de_processo_ausente_preserva_semantica():
    with pytest.raises(ProcessoNaoEncontrado):
        eproc_tjsp._verificar_alerta_consulta("Processo não encontrado", "1G")


def test_dialogo_captcha_e_capturado_e_dispensa_o_alerta():
    class Page:
        def on(self, event, callback):
            assert event == "dialog"
            self.callback = callback

    class Dialog:
        message = "Resolva o captcha para continuar."
        dismissed = False

        def dismiss(self):
            self.dismissed = True

    page = Page()
    alerta = eproc_tjsp._capturar_alertas(page)
    dialog = Dialog()
    page.callback(dialog)

    with pytest.raises(AcessoRestrito, match="verificação interativa"):
        eproc_tjsp._verificar_alerta_capturado(alerta, "2G")
    assert dialog.dismissed is True


def test_detector_nao_confunde_script_turnstile_com_desafio():
    html = """<html><head>
      <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
    </head><body>
      <input type="hidden" name="cf-turnstile-response" value="">
      <form id="frmProcessoLista"></form>
    </body></html>"""
    assert eproc_tjsp._pagina_tem_desafio_interativo(html) is False


def test_aguardar_resultado_observa_tabela_mensagem_ou_desafio():
    chamadas = []

    class Locator:
        def __init__(self, selector):
            self.selector = selector

        @property
        def first(self):
            return self

        def count(self):
            return 0

        def wait_for(self, **kwargs):
            chamadas.append((self.selector, kwargs))

    class Page:
        def content(self):
            return "<html><body>Consulta</body></html>"

        def locator(self, selector):
            chamadas.append(selector)
            return Locator(selector)

    eproc_tjsp._aguardar_resultado(
        Page(), timeout_ms=2500, seletor_adicional="button:has-text('EPROC')"
    )

    seletor_resultado, opcoes = chamadas[-1]
    assert "Data/Hora" in seletor_resultado
    assert "nenhum processo" in seletor_resultado
    assert "challenges.cloudflare.com" not in seletor_resultado
    assert "button:has-text('EPROC')" in seletor_resultado
    assert opcoes == {"state": "visible", "timeout": 2500}


def test_aguardar_resultado_da_janela_curta_ao_turnstile_autoverificar():
    chamadas = []

    class Locator:
        def __init__(self, selector):
            self.selector = selector

        @property
        def first(self):
            return self

        def count(self):
            return int(self.selector == eproc_tjsp.SELETOR_DESAFIO)

        def wait_for(self, **kwargs):
            chamadas.append((self.selector, kwargs))

    class Page:
        def content(self):
            return "<div class='cf-turnstile'></div>"

        def locator(self, selector):
            return Locator(selector)

    eproc_tjsp._aguardar_resultado(Page(), timeout_ms=60_000)

    seletor_resultado, opcoes = chamadas[0]
    assert "Data/Hora" in seletor_resultado
    assert opcoes == {"state": "visible", "timeout": 30_000}


def test_aguardar_resultado_permita_espera_completa_quando_operador_resolve():
    chamadas = []

    class Locator:
        @property
        def first(self):
            return self

        def count(self):
            return 1

        def wait_for(self, **kwargs):
            chamadas.append(kwargs)

    class Page:
        def content(self):
            return "<div class='cf-turnstile'></div>"

        def locator(self, _selector):
            return Locator()

    eproc_tjsp._aguardar_resultado(
        Page(),
        timeout_ms=30_000,
        desafio_pendente=True,
        aguardar_desafio_interativo=True,
    )

    assert chamadas == [{"state": "visible", "timeout": 30_000}]


@pytest.mark.parametrize(
    "consulta", [eproc_tjsp.consultar_processo, eproc_tjsp.consultar_processo_2g]
)
def test_espera_interativa_exige_navegador_visivel(consulta):
    with pytest.raises(ValueError, match="headless=False"):
        consulta(CNJ, headless=True, aguardar_desafio_interativo=True)


@pytest.mark.parametrize(
    "consulta", [eproc_tjsp.consultar_processo, eproc_tjsp.consultar_processo_2g]
)
def test_espera_interativa_exige_booleano(consulta):
    with pytest.raises(ValueError, match="deve ser booleano"):
        consulta(CNJ, aguardar_desafio_interativo="true")


def test_aguardar_resultado_classifica_desafio_persistente_apos_espera(monkeypatch):
    class TimeoutError(Exception):
        pass

    class Locator:
        def __init__(self, selector):
            self.selector = selector

        @property
        def first(self):
            return self

        def count(self):
            return int(self.selector == eproc_tjsp.SELETOR_DESAFIO)

        def wait_for(self, **kwargs):
            assert kwargs["timeout"] == 25_000
            raise TimeoutError()

    class Page:
        def content(self):
            return "<div class='cf-turnstile'></div>"

        def locator(self, selector):
            return Locator(selector)

    playwright_module = ModuleType("playwright")
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.TimeoutError = TimeoutError
    playwright_module.sync_api = sync_api_module
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    with pytest.raises(AcessoRestrito, match="dentro do prazo de 25 segundos"):
        eproc_tjsp._aguardar_resultado(Page(), timeout_ms=25000, grau="2G")


def test_aguardar_resultado_classifica_bloqueio_cloudflare(monkeypatch):
    class TimeoutError(Exception):
        pass

    class Locator:
        @property
        def first(self):
            return self

        def count(self):
            return 0

        def wait_for(self, **kwargs):
            raise TimeoutError()

    class Page:
        url = URL

        def content(self):
            return """<html><body><h1>Sorry, you have been blocked</h1>
              <p>Cloudflare Ray ID: 1234567890</p></body></html>"""

        def locator(self, _selector):
            return Locator()

    playwright_module = ModuleType("playwright")
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.TimeoutError = TimeoutError
    playwright_module.sync_api = sync_api_module
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    with pytest.raises(AcessoRestrito, match="Cloudflare bloqueou.*automatizada"):
        eproc_tjsp._aguardar_resultado(Page(), timeout_ms=1000, grau="1G")


def test_aguardar_resultado_informa_prazo_interativo_configurado(monkeypatch):
    class TimeoutError(Exception):
        pass

    class Locator:
        @property
        def first(self):
            return self

        def count(self):
            return 1

        def wait_for(self, **kwargs):
            assert kwargs["timeout"] == 120_000
            raise TimeoutError()

    class Page:
        def content(self):
            return "<div class='cf-turnstile'></div>"

        def locator(self, _selector):
            return Locator()

    playwright_module = ModuleType("playwright")
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.TimeoutError = TimeoutError
    playwright_module.sync_api = sync_api_module
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    with pytest.raises(AcessoRestrito, match="120 segundos"):
        eproc_tjsp._aguardar_resultado(
            Page(),
            timeout_ms=120_000,
            desafio_pendente=True,
            aguardar_desafio_interativo=True,
        )


def test_aguardar_resultado_identifica_redirecionamento_para_sso(monkeypatch):
    class TimeoutError(Exception):
        pass

    class Locator:
        @property
        def first(self):
            return self

        def count(self):
            return 1

        def wait_for(self, **kwargs):
            raise TimeoutError()

    class Page:
        url = "https://sso.tjsp.jus.br/realms/eproc/protocol/openid-connect/auth?response_type=code"

        def content(self):
            return "<div class='cf-turnstile'></div>"

        def locator(self, _selector):
            return Locator()

    playwright_module = ModuleType("playwright")
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.TimeoutError = TimeoutError
    playwright_module.sync_api = sync_api_module
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    with pytest.raises(
        AcessoRestrito,
        match="autenticação do TJSP com verificação interativa",
    ):
        eproc_tjsp._aguardar_resultado(Page(), timeout_ms=60_000, grau="2G")


def test_validar_url_classifica_sso_oficial_como_acesso_restrito():
    url = "https://sso.tjsp.jus.br/realms/eproc/protocol/openid-connect/auth"
    with pytest.raises(AcessoRestrito, match="autenticação do TJSP"):
        eproc_tjsp._validar_url(url, grau="2G")


def test_parse_resultado_nao_confunde_script_turnstile_com_desafio():
    html = """<html><head>
      <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
    </head><body>
      <input type="hidden" name="cf-turnstile-response" value="">
      <form id="frmProcessoLista"></form>
    </body></html>"""
    with pytest.raises(ConsultaIndisponivel, match="tabela de eventos"):
        eproc_tjsp.parse_resultado(CNJ, html, URL)


def test_consultar_classifica_timeout_com_desafio_como_acesso_restrito(monkeypatch):
    class TimeoutError(Exception):
        pass

    class Locator:
        def __init__(self, should_timeout=False):
            self.should_timeout = should_timeout

        def count(self):
            return 1

        def fill(self, value):
            assert value == CNJ

        def input_value(self):
            return "SP"

        def click(self):
            if self.should_timeout:
                raise TimeoutError()

    challenge_html = """<div class="cf-turnstile" data-sitekey="site"></div>
      <iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/"></iframe>"""

    class Page:
        url = URL

        def on(self, event, callback):
            assert event == "dialog"

        def set_default_timeout(self, value):
            assert value > 0

        def goto(self, *args, **kwargs):
            return None

        def locator(self, selector):
            return Locator(should_timeout=selector == "#sbmNovo")

        def get_by_role(self, role, **kwargs):
            return Locator()

        def wait_for_load_state(self, *args, **kwargs):
            return None

        def content(self):
            return challenge_html

    page = Page()

    class Browser:
        def new_page(self):
            return page

        def close(self):
            return None

    class Chromium:
        def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

    class PlaywrightManager:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *args):
            return None

    playwright_module = ModuleType("playwright")
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.TimeoutError = TimeoutError
    sync_api_module.sync_playwright = PlaywrightManager
    playwright_module.sync_api = sync_api_module
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    with pytest.raises(AcessoRestrito, match="verificação interativa"):
        eproc_tjsp.consultar_processo(CNJ, timeout=1)


def test_consultar_processo_1g_inicia_no_portal_e_segue_consulta_unificada(monkeypatch):
    consultas = []
    url_consulta = "https://eproc-consulta.tjsp.jus.br/consulta_1g/externo_controlador.php"

    class Locator:
        first = None

        def __init__(self, selector):
            self.selector = selector
            self.first = self

        def count(self):
            return 0 if self.selector == "a" else 1

        def fill(self, value):
            consultas.append(("fill", self.selector, value))

        def input_value(self):
            return "SP"

        def select_option(self, value):
            consultas.append(("select", self.selector, value))

        def click(self):
            consultas.append(("click", self.selector))

        def filter(self, **kwargs):
            return self

        def wait_for(self, **kwargs):
            consultas.append(("wait_for", self.selector))

    class Page:
        url = url_consulta

        def on(self, event, callback):
            assert event == "dialog"

        def set_default_timeout(self, value):
            assert value > 0

        def goto(self, url, **kwargs):
            consultas.append(("goto", url))

        def locator(self, selector, **kwargs):
            return Locator(selector)

        def get_by_role(self, role, **kwargs):
            consultas.append(("get_by_role", role, kwargs.get("name")))
            return Locator(f"role:{role}:{kwargs.get('name')}")

        def wait_for_load_state(self, *args, **kwargs):
            consultas.append(("wait_for_load_state",))

        def content(self):
            return HTML_EVENTOS_2G

    page = Page()

    class Browser:
        def new_page(self):
            return page

        def close(self):
            return None

    class Chromium:
        def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

    class PlaywrightManager:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *args):
            return None

    playwright_module = ModuleType("playwright")
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.TimeoutError = type("TimeoutError", (Exception,), {})
    sync_api_module.sync_playwright = PlaywrightManager
    playwright_module.sync_api = sync_api_module
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    resultado = eproc_tjsp.consultar_processo(CNJ)

    assert resultado["dados_basicos"]["numero"] == CNJ
    assert consultas[0] == ("goto", "https://eproc1g.tjsp.jus.br/eproc")
    assert ("get_by_role", "link", "Consulta Unificada") in consultas
    assert consultas.index(("get_by_role", "link", "Consulta Unificada")) < consultas.index(
        ("fill", "#txtNumProcesso", CNJ)
    )


def test_parse_resultado_rejeita_tabela_de_eventos_vazia():
    html = "<table><tr><th>Data/Hora</th></tr></table>"
    with pytest.raises(ConsultaIndisponivel, match="nenhum evento"):
        eproc_tjsp.parse_resultado(CNJ, html, URL)


def test_parse_resultado_rejeita_numero_de_processo_divergente():
    outro = "1000000-00.2024.8.26.0114"
    html = f"""<table><tr><th>Data/Hora</th></tr><tr><td>{outro}</td></tr>
      <tr><td>1</td><td>11/11/2026</td><td>Movimento</td><td>ABC</td><td></td></tr></table>"""
    with pytest.raises(ConsultaIndisponivel, match="diferente"):
        eproc_tjsp.parse_resultado(CNJ, html, URL)


def test_parse_resultado_falha_se_a_pagina_nao_for_do_host_oficial():
    with pytest.raises(ConsultaIndisponivel):
        eproc_tjsp.parse_resultado(CNJ, "<p>nada</p>", "https://example.com/")


def test_parse_resultado_2g_usa_host_e_grau_proprios():
    url = "https://eproc2g-consulta.tjsp.jus.br/eproc/externo_controlador.php?eventos=true"
    resultado = eproc_tjsp.parse_resultado(CNJ, HTML_EVENTOS_2G, url, grau="2G")
    assert resultado["origem"]["grau"] == "2G"
    assert resultado["origem"]["movimentacoes_completas"] is True


def test_consultar_processo_2g_percorre_consulta_unificada_e_formulario_eproc(monkeypatch):
    consultas = []

    class Locator:
        first = None

        def __init__(self, selector):
            self.selector = selector
            self.first = self

        def count(self):
            return 0 if self.selector == "a" else 1

        def fill(self, value):
            consultas.append(("fill", self.selector, value))

        def select_option(self, value):
            consultas.append(("select", self.selector, value))

        def click(self):
            consultas.append(("click", self.selector))

        def filter(self, **kwargs):
            return self

        def wait_for(self, **kwargs):
            consultas.append(("wait_for", self.selector))

    class Page:
        url = "https://eproc2g-consulta.tjsp.jus.br/eproc/externo_controlador.php?eventos=true"

        def on(self, event, callback):
            assert event == "dialog"

        def set_default_timeout(self, value):
            assert value > 0

        def goto(self, url, **kwargs):
            consultas.append(("goto", url))

        def locator(self, selector, **kwargs):
            return Locator(selector)

        def get_by_role(self, role, **kwargs):
            return Locator(f"role:{role}:{kwargs['name']}")

        def wait_for_load_state(self, *args, **kwargs):
            return None

        def content(self):
            return HTML_EVENTOS_2G

    page = Page()

    class Browser:
        def new_page(self):
            return page

        def close(self):
            return None

    class Chromium:
        def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

    class PlaywrightManager:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *args):
            return None

    playwright_module = ModuleType("playwright")
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.TimeoutError = type("TimeoutError", (Exception,), {})
    sync_api_module.sync_playwright = PlaywrightManager
    playwright_module.sync_api = sync_api_module
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    resultado = eproc_tjsp.consultar_processo_2g(CNJ)
    assert resultado["origem"]["grau"] == "2G"
    assert consultas[0] == ("goto", "https://eproc2g-consulta.tjsp.jus.br/eproc/")
    assert ("click", "role:button:EPROC") in consultas
    assert ("fill", "#numNrProcesso", CNJ) in consultas
    assert ("click", "#divInfraBarraComandosSuperior #sbmConsultar") in consultas
    assert not any(item[0] == "select" and item[1] == "#selInstancia" for item in consultas)
    assert not any(item[0] == "fill" and item[1] == "#txtNumProcesso" for item in consultas)
