"""Fluxos assistidos de autenticação oficial para fontes judiciais."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urlsplit

import requests

from . import esaj
from .exceptions import AcessoRestrito, ConsultaIndisponivel
from .utils import validar_inteiro


def _retorno_esaj(url: str) -> bool:
    destino = urlsplit(url)
    origem = urlsplit(esaj.ESAJ_BASE)
    endpoint_retorno = f"{origem.path.rstrip('/')}/open.do"
    return (
        destino.scheme == "https"
        and destino.netloc == origem.netloc
        and destino.path == endpoint_retorno
        and not destino.fragment
    )


def autenticar_esaj_no_navegador(
    *,
    timeout_login: int = 600,
    executable_path: str | None = None,
) -> requests.Session:
    """Abre o login oficial do e-SAJ e devolve uma sessão HTTP em memória.

    O advogado opera a tela do tribunal para escolher o mecanismo disponível
    (credencial do portal, código adicional ou certificado). A NanoJud não lê nem
    envia os campos de login. Cookies não são gravados em disco e a janela fecha
    depois do retorno ao e-SAJ. Requer ``nanojud[autenticacao]``.
    """
    timeout_login = validar_inteiro(timeout_login, nome="timeout_login", minimo=1, maximo=1800)

    redirect_uri = f"{esaj.ESAJ_BASE}/open.do"
    login_url = "https://esaj.tjsp.jus.br/esaj/api/auth/sign-in?" + urlencode(
        {"redirect_uri": redirect_uri}
    )
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ConsultaIndisponivel(
            'Autenticação assistida requer o extra: python -m pip install "nanojud[autenticacao]"'
        ) from exc

    cookies: list[Any] = []
    user_agent = ""
    try:
        with sync_playwright() as playwright:
            launch_options: dict[str, Any] = {"headless": False}
            if executable_path:
                launch_options["executable_path"] = executable_path
            browser = playwright.chromium.launch(**launch_options)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_login * 1000)
                page.wait_for_url(
                    _retorno_esaj,
                    timeout=timeout_login * 1000,
                )
                autenticado = page.evaluate(
                    "() => Boolean(window.sajcas && window.sajcas.usuarioLogadoNoCasServer)"
                )
                if not autenticado:
                    raise AcessoRestrito(
                        "O e-SAJ não confirmou uma identidade autenticada neste navegador."
                    )
                user_agent = str(page.evaluate("() => navigator.userAgent") or "")
                cookies = context.cookies([f"{esaj.ESAJ_BASE}/", esaj.PASTA_BASE])
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise AcessoRestrito(
            "O login oficial não retornou ao e-SAJ antes do timeout; nenhuma sessão foi criada."
        ) from exc
    except AcessoRestrito:
        raise
    except Exception as exc:
        # Não propaga URLs, corpo da página, campos de autenticação ou cookies.
        detalhe = str(exc).casefold()
        if "executable doesn't exist" in detalhe or "executable does not exist" in detalhe:
            if executable_path:
                mensagem = (
                    "O navegador configurado não foi encontrado. Confira `executable_path` "
                    "ou instale o Chromium do Playwright com "
                    "`python -m playwright install chromium`."
                )
            else:
                mensagem = (
                    "O Chromium do Playwright não está instalado. Execute "
                    "`python -m playwright install chromium` e tente novamente."
                )
            raise ConsultaIndisponivel(mensagem) from exc
        raise ConsultaIndisponivel(
            f"Falha no navegador de autenticação ({type(exc).__name__}). "
            "Confira se há um navegador Chromium funcional e uma sessão gráfica disponível."
        ) from exc

    if not cookies:
        raise AcessoRestrito("O e-SAJ não devolveu cookies de sessão após o login.")
    session = esaj.criar_session()
    for cookie in cookies:
        session.cookies.set(
            str(cookie["name"]),
            str(cookie["value"]),
            domain=str(cookie.get("domain") or "esaj.tjsp.jus.br"),
            path=str(cookie.get("path") or "/"),
            secure=bool(cookie.get("secure", True)),
            expires=int(cookie["expires"]) if cookie.get("expires", -1) >= 0 else None,
        )
    if user_agent:
        session.headers["User-Agent"] = user_agent
    return session
