from uuid import uuid4

import requests

from nanojud import esaj
from nanojud.exceptions import (
    AcessoRestrito,
    ConsultaIndisponivel,
    ProcessoNaoEncontrado,
    URLInvalida,
)


class FakeResponse:
    def __init__(self, text: str, url: str, status_code: int = 200):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.content = text.encode("utf-8")


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "search.do" in url:
            html = (
                '<a class="linkProcesso" '
                'href="/cpopg/show.do?processo.foro=100&processo.codigo=ABC">Processo</a>'
            )
            return FakeResponse(
                html,
                url,
            )
        return FakeResponse('<span id="numeroProcesso">1076539-20.2019.8.26.0100</span>', url)


def test_carregar_pagina_segue_lista_de_processos():
    session = FakeSession()

    response = esaj.carregar_pagina(session, "1076539-20.2019.8.26.0100")

    assert "show.do" in response.url
    assert len(session.calls) == 3


def test_carregar_pagina_rejeita_url_fora_do_esaj():
    try:
        esaj.carregar_pagina(FakeSession(), "https://example.test/cpopg/show.do")
    except URLInvalida:
        pass
    else:
        raise AssertionError("URL externa deveria gerar URLInvalida")


def test_get_traduz_status_http_previstos():
    def resposta_com_status(status):
        return lambda url, **kwargs: FakeResponse("", url, status_code=status)

    for status, esperado in [
        (403, AcessoRestrito),
        (404, ProcessoNaoEncontrado),
        (503, ConsultaIndisponivel),
    ]:
        session = FakeSession()
        session.get = resposta_com_status(status)

        try:
            esaj._get(session, "https://esaj.tjsp.jus.br/cpopg/show.do")
        except esperado:
            pass
        else:
            raise AssertionError(f"HTTP {status} deveria gerar {esperado.__name__}")


def test_get_traduz_falha_de_comunicacao():
    class SessionComErro:
        def get(self, url, **kwargs):
            raise requests.RequestException("timeout")

    try:
        esaj._get(SessionComErro(), "https://esaj.tjsp.jus.br/cpopg/show.do")
    except ConsultaIndisponivel as exc:
        assert "timeout" in str(exc)
    else:
        raise AssertionError("Falha requests deveria gerar ConsultaIndisponivel")


def test_garantir_dependencias_rejeita_ambiente_sem_dependencias(monkeypatch):
    monkeypatch.setattr(esaj, "requests", None)

    try:
        esaj._garantir_dependencias()
    except ConsultaIndisponivel:
        pass
    else:
        raise AssertionError("Dependências ausentes deveriam gerar ConsultaIndisponivel")


def test_criar_session_configura_headers_e_timeout():
    session = esaj.criar_session(timeout=12)

    assert session.timeout == 12
    assert "nanojud" in session.headers["User-Agent"]
    assert session.headers["Referer"].endswith("/open.do")


def test_salvar_html_bruto():
    pasta = __import__("pathlib").Path(f".tmp/test-html-{uuid4()}")
    caminho = esaj.salvar_html_bruto("<html>ok</html>", "1076539-20.2019.8.26.0100", pasta)

    assert caminho.read_text(encoding="utf-8") == "<html>ok</html>"


def test_carregar_pagina_url_direta_valida():
    session = FakeSession()

    response = esaj.carregar_pagina(
        session,
        "https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=ABC",
        timeout=9,
    )

    assert response.url.endswith("processo.codigo=ABC")
    assert session.calls[0][1]["timeout"] == 9


def test_seguir_lista_sem_links_retorna_resposta_original():
    response = FakeResponse(
        "<html><body>lista vazia</body></html>", "https://esaj.tjsp.jus.br/cpopg/search.do"
    )
    session = FakeSession()

    resultado = esaj._seguir_lista_se_preciso(session, response)

    assert resultado is response


class SessaoQueNaoDeveSerChamada:
    def get(self, url, **kwargs):
        raise AssertionError(f"requisicao inesperada para {url}")


def test_pasta_digital_rejeita_href_fora_do_esaj():
    for href in (
        "https://example.test/cpopg/abrir.do",
        "http://esaj.tjsp.jus.br/cpopg/abrir.do",
        "https://esaj.tjsp.jus.br.example.test/cpopg/abrir.do",
        "https://esaj.tjsp.jus.br/outro/abrir.do",
    ):
        try:
            esaj.obter_metadados_pasta_documento(SessaoQueNaoDeveSerChamada(), {"href": href})
        except URLInvalida:
            continue
        raise AssertionError(f"href deveria ser rejeitado: {href}")


def test_pasta_digital_aceita_href_do_esaj():
    class Sessao:
        def get(self, url, **kwargs):
            return FakeResponse("<html></html>", url)

    href = "https://esaj.tjsp.jus.br/cpopg/abrirDocumentoVinculadoMovimentacao.do?cdDocumento=1"

    resultado = esaj.obter_metadados_pasta_documento(Sessao(), {"href": href})

    assert resultado["status"] == "sem_request_scope"
