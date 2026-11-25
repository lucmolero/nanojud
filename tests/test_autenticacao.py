from __future__ import annotations

import sys
from types import ModuleType

import pytest
import requests

from nanojud import autenticacao, esaj
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel


@pytest.mark.parametrize(
    "url",
    [
        "https://esaj.tjsp.jus.br/cpopg/",
        "https://esaj.tjsp.jus.br/cpopg/other.do",
        "https://esaj.tjsp.jus.br/cpopg/../sajcas/login",
        "https://esaj.tjsp.jus.br:443/cpopg/open.do",
        "https://user@esaj.tjsp.jus.br/cpopg/open.do",
        "http://esaj.tjsp.jus.br/cpopg/open.do",
        "https://esaj.tjsp.jus.br/cpopg/open.do#fragment",
    ],
)
def test_retorno_esaj_aceita_somente_endpoint_oficial_exato(url):
    assert autenticacao._retorno_esaj(url) is False


def test_retorno_esaj_aceita_query_no_endpoint_oficial():
    assert autenticacao._retorno_esaj("https://esaj.tjsp.jus.br/cpopg/open.do?origem=login")


class _Page:
    def goto(self, url: str, **kwargs: object) -> None:
        assert kwargs["timeout"] == 30_000
        self.login_url = url

    def wait_for_url(self, predicate, **kwargs: object) -> None:
        assert predicate("https://esaj.tjsp.jus.br/cpopg/open.do")
        assert not predicate("https://example.org/cpopg/open.do")
        assert not predicate("https://esaj.tjsp.jus.br/sajcas/login?service=/cpopg/open.do")

    def evaluate(self, script: str) -> object:
        if "usuarioLogadoNoCasServer" in script:
            return True
        return "Mozilla/5.0 NanoJud-Test"


class _Context:
    def new_page(self) -> _Page:
        return _Page()

    def cookies(self, urls: list[str]) -> list[dict[str, object]]:
        assert urls == [f"{esaj.ESAJ_BASE}/", esaj.PASTA_BASE]
        return [
            {
                "name": "JSESSIONID",
                "value": "cookie-secret",
                "domain": "esaj.tjsp.jus.br",
                "path": "/",
                "secure": True,
            }
        ]


class _Browser:
    def new_context(self) -> _Context:
        return _Context()

    def close(self) -> None:
        self.closed = True


class _Chromium:
    def __init__(self) -> None:
        self.browser = _Browser()

    def launch(self, **kwargs: object) -> _Browser:
        assert kwargs["headless"] is False
        return self.browser


class _Playwright:
    def __init__(self) -> None:
        self.chromium = _Chromium()


class _Manager:
    def __enter__(self) -> _Playwright:
        self.playwright = _Playwright()
        return self.playwright

    def __exit__(self, *args: object) -> None:
        return None


def test_login_assistido_copia_cookies_para_sessao_em_memoria(monkeypatch) -> None:
    module = ModuleType("playwright.sync_api")
    module.sync_playwright = _Manager
    timeout_error = type("TimeoutError", (Exception,), {})
    module.TimeoutError = timeout_error
    package = ModuleType("playwright")
    package.sync_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(esaj, "criar_session", requests.Session)

    session = autenticacao.autenticar_esaj_no_navegador(timeout_login=30)

    assert session.cookies.get("JSESSIONID") == "cookie-secret"
    assert session.headers["User-Agent"] == "Mozilla/5.0 NanoJud-Test"


@pytest.mark.parametrize("timeout_login", [0, -1, 1.5, "30", None, True, 1801, 10**1000])
def test_login_assistido_rejeita_timeout_invalido_antes_de_criar_sessao(
    monkeypatch, timeout_login
) -> None:
    monkeypatch.setattr(
        esaj,
        "criar_session",
        lambda: pytest.fail("Timeout inválido não deve criar sessão nem abrir navegador"),
    )

    with pytest.raises(ValueError, match="timeout_login"):
        autenticacao.autenticar_esaj_no_navegador(timeout_login=timeout_login)


def test_login_assistido_orienta_instalacao_do_chromium_sem_expor_caminho(monkeypatch) -> None:
    caminho_local = "C:/Users/teste/AppData/Local/ms-playwright/chromium-123/chrome.exe"

    class _ChromiumSemInstalacao:
        def launch(self, **kwargs: object) -> object:
            raise RuntimeError(f"Executable doesn't exist at {caminho_local}")

    class _PlaywrightSemInstalacao:
        chromium = _ChromiumSemInstalacao()

    class _ManagerSemInstalacao:
        def __enter__(self) -> _PlaywrightSemInstalacao:
            return _PlaywrightSemInstalacao()

        def __exit__(self, *args: object) -> None:
            return None

    module = ModuleType("playwright.sync_api")
    module.sync_playwright = _ManagerSemInstalacao
    module.TimeoutError = type("TimeoutError", (Exception,), {})
    package = ModuleType("playwright")
    package.sync_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(esaj, "criar_session", requests.Session)

    with pytest.raises(ConsultaIndisponivel) as erro:
        autenticacao.autenticar_esaj_no_navegador(timeout_login=30)

    assert "python -m playwright install chromium" in str(erro.value)
    assert caminho_local not in str(erro.value)


def test_login_assistido_sem_playwright_nao_cria_sessao_http(monkeypatch) -> None:
    criacoes = []
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    monkeypatch.setattr(esaj, "criar_session", lambda: criacoes.append(True))

    with pytest.raises(ConsultaIndisponivel, match="nanojud\\[autenticacao\\]"):
        autenticacao.autenticar_esaj_no_navegador(timeout_login=30)

    assert criacoes == []


def test_login_assistido_navegador_configurado_ausente_nao_expoe_caminho(monkeypatch) -> None:
    caminho = "C:/segredo/perfil/chromium.exe"

    class _ChromiumAusente:
        def launch(self, **kwargs: object) -> object:
            raise RuntimeError(f"Executable does not exist at {caminho}")

    class _PlaywrightAusente:
        chromium = _ChromiumAusente()

    class _ManagerAusente:
        def __enter__(self) -> _PlaywrightAusente:
            return _PlaywrightAusente()

        def __exit__(self, *args: object) -> None:
            return None

    module = ModuleType("playwright.sync_api")
    module.sync_playwright = _ManagerAusente
    module.TimeoutError = type("TimeoutError", (Exception,), {})
    package = ModuleType("playwright")
    package.sync_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(esaj, "criar_session", lambda: pytest.fail("Não deve criar sessão"))

    with pytest.raises(ConsultaIndisponivel, match="navegador configurado") as erro:
        autenticacao.autenticar_esaj_no_navegador(timeout_login=30, executable_path=caminho)

    assert caminho not in str(erro.value)


def test_login_assistido_sanitiza_falha_generica_do_navegador(monkeypatch) -> None:
    segredo = "cookie=nao-registre"

    class _ChromiumComFalha:
        def launch(self, **kwargs: object) -> object:
            raise RuntimeError(segredo)

    class _PlaywrightComFalha:
        chromium = _ChromiumComFalha()

    class _ManagerComFalha:
        def __enter__(self) -> _PlaywrightComFalha:
            return _PlaywrightComFalha()

        def __exit__(self, *args: object) -> None:
            return None

    module = ModuleType("playwright.sync_api")
    module.sync_playwright = _ManagerComFalha
    module.TimeoutError = type("TimeoutError", (Exception,), {})
    package = ModuleType("playwright")
    package.sync_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(esaj, "criar_session", lambda: pytest.fail("Não deve criar sessão"))

    with pytest.raises(ConsultaIndisponivel, match="RuntimeError") as erro:
        autenticacao.autenticar_esaj_no_navegador(timeout_login=30)

    assert segredo not in str(erro.value)


def test_login_assistido_nao_substitui_user_agent_quando_navegador_nao_informa(monkeypatch) -> None:
    module = ModuleType("playwright.sync_api")
    module.sync_playwright = _Manager
    module.TimeoutError = type("TimeoutError", (Exception,), {})
    package = ModuleType("playwright")
    package.sync_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(
        _Page,
        "evaluate",
        lambda _self, script: True if "usuarioLogadoNoCasServer" in script else "",
    )
    monkeypatch.setattr(esaj, "criar_session", requests.Session)

    session = autenticacao.autenticar_esaj_no_navegador(timeout_login=30)

    assert session.headers["User-Agent"] == requests.utils.default_user_agent()


@pytest.mark.parametrize(
    ("cenario", "mensagem"),
    [
        ("timeout", "antes do timeout"),
        ("sem_identidade", "não confirmou uma identidade"),
        ("sem_cookies", "não devolveu cookies"),
    ],
)
def test_login_assistido_fecha_navegador_sem_entregar_sessao(monkeypatch, cenario, mensagem):
    timeout_error = type("TimeoutError", (Exception,), {})
    manager = _Manager()
    module = ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: manager
    module.TimeoutError = timeout_error
    package = ModuleType("playwright")
    package.sync_api = module
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    if cenario == "timeout":

        def aguardar(*args, **kwargs):
            raise timeout_error

        monkeypatch.setattr(_Page, "wait_for_url", aguardar)
    elif cenario == "sem_identidade":
        monkeypatch.setattr(_Page, "evaluate", lambda *args: False)
    else:
        monkeypatch.setattr(_Context, "cookies", lambda *args: [])

    with pytest.raises(AcessoRestrito, match=mensagem):
        autenticacao.autenticar_esaj_no_navegador(
            timeout_login=30, executable_path="chromium-de-teste"
        )

    assert manager.playwright.chromium.browser.closed
