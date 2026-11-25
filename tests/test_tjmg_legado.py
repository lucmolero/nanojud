from types import SimpleNamespace

import pytest
import requests

from nanojud import tjmg_legado
from nanojud.exceptions import (
    AcessoRestrito,
    ConsultaIndisponivel,
    DocumentoNaoEncontrado,
    ProcessoNaoEncontrado,
)

CNJ = "2125575-44.2023.8.13.0000"
ID_INTERNO = "10000232125575004"
DOCUMENT_LINK = (
    "<a onclick=\"window.open('downloadPeca2?codigoDocumento=12345&amp;"
    "anoCriacaoDoc=2024')\">Peça</a>"
)


def _response(html: str, status_code: int = 200):
    return SimpleNamespace(status_code=status_code, text=html)


def test_consulta_confirma_identidade_e_marca_extrato_parcial():
    html = f"""
    <html><head><title>TJMG - Andamento Processual - Andamentos</title></head><body>
      <h1>2ª Instância - Dados do processo</h1>
      <div>Número: 1.0000.23.212557-5/004</div>
      <div>Numeração única: {CNJ}</div>
      <table class="corpo">
        <tr><td>Movimentação</td><td>Detalhe</td><td>Data</td><td>Complemento</td></tr>
        <tr><td>Decisão</td><td>Publicada</td><td>13/11/2026</td><td>Inteiro teor</td></tr>
      </table>
    </body></html>
    """

    class Session:
        def __init__(self):
            self.urls = []

        def get(self, url, *, timeout, allow_redirects):
            self.urls.append(url)
            assert timeout == 9
            assert allow_redirects is False
            if "proc_movimentacoes2.jsp" in url:
                return _response(html)
            if "proc_complemento2.jsp" in url:
                return _response(
                    f"""<h1>Dados completos</h1><p>NÚMERO TJMG: 1.0000.23.212557-5/004</p>
                    <p>NUMERAÇÃO ÚNICA: {CNJ}</p><table class="corpo">
                    <tr><td>Câmara: 1ª Seção Cível</td><td></td></tr>
                    <tr><td>Classe: IRDR - Cv</td><td>Assunto: Servidor público</td></tr>
                    <tr><td>Relator: Des(a). Exemplo</td><td></td></tr>
                    <tr><td>Comarca Origem: Belo Horizonte</td><td>Vara Origem: 4ª Vara</td></tr>
                    </table>"""
                )
            return _response(
                f"""<p>NÚMERO TJMG: 1.0000.23.212557-5/004</p><p>NUMERAÇÃO ÚNICA: {CNJ}</p>
                <table class="corpo"><tr><td>Agravante(s):</td><td>Parte autora
                <table class="corpo"><tr><td>Advogado(s):</td><td><table>
                <tr><td>OAB/XX 12345</td><td>Advogado Exemplo</td></tr></table></td></tr>
                </table></td></tr>
                <tr><td>Agravado(a)(s):</td><td>Parte ré</td></tr></table>"""
            )

    session = Session()

    resultado = tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=session, timeout=9)

    assert resultado["status"] == "partial"
    assert resultado["origem"]["tribunal"] == "TJMG"
    assert resultado["origem"]["grau"] == "2G"
    assert resultado["dados_basicos"]["numero"] == CNJ
    assert resultado["dados_basicos"]["numero_tjmg"] == "1.0000.23.212557-5/004"
    assert resultado["dados_basicos"]["classe"] == "IRDR - Cv"
    assert resultado["dados_basicos"]["assunto"] == "Servidor público"
    assert resultado["partes"]["polo_ativo"][0]["nomes"] == ["Parte autora"]
    assert resultado["partes"]["polo_ativo"][0]["advogados"] == ["OAB/XX 12345 — Advogado Exemplo"]
    assert resultado["partes"]["polo_passivo"][0]["nomes"] == ["Parte ré"]
    assert resultado["origem"]["partes_completas"] is False
    assert resultado["movimentacoes"][0]["titulo"] == "Decisão"
    assert resultado["movimentacoes_completas"] is False
    assert len(session.urls) == 3


def test_consulta_rejeita_identidade_divergente():
    html = (
        "<html><body><h1>2ª Instância - Dados do processo</h1>"
        "2125575-44.2023.8.13.0001</body></html>"
    )

    class Session:
        def get(self, *_args, **_kwargs):
            return _response(html)

    with pytest.raises(ConsultaIndisponivel, match="não confirmou o CNJ"):
        tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())


def test_consulta_cria_sessao_com_user_agent_da_biblioteca(monkeypatch):
    html = (
        f"<h1>2ª Instância - Dados do processo</h1>1.0000.23.212557-5/004 {CNJ}"
        "<table class='corpo'><tr><td>Decisão</td>"
        "<td>13/11/2026</td><td></td></tr></table>"
    )
    criada = SimpleNamespace(headers={}, get=lambda *_args, **_kwargs: _response(html))
    monkeypatch.setattr(tjmg_legado.requests, "Session", lambda: criada)

    resultado = tjmg_legado.consultar_processo(CNJ, ID_INTERNO)

    assert "nanojud/" in criada.headers["User-Agent"]
    assert resultado["status"] == "partial"


def test_consulta_classifica_desafio_sem_tentar_resolve_lo():
    class Session:
        def get(self, *_args, **_kwargs):
            return _response("<html><body>captcha confirmação de segurança</body></html>")

    with pytest.raises(AcessoRestrito, match="confirmação interativa"):
        tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())


@pytest.mark.parametrize(
    ("status", "erro"),
    [
        (403, AcessoRestrito),
        (412, AcessoRestrito),
        (404, ProcessoNaoEncontrado),
        (503, ConsultaIndisponivel),
    ],
)
def test_consulta_classifica_status_http(status, erro):
    class Session:
        def get(self, *_args, **_kwargs):
            return _response("", status)

    with pytest.raises(erro):
        tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())


def test_consulta_classifica_falha_de_rede():
    class Session:
        def get(self, *_args, **_kwargs):
            raise requests.Timeout("detalhe omitido")

    with pytest.raises(ConsultaIndisponivel, match="Timeout"):
        tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())


@pytest.mark.parametrize(
    ("html", "mensagem"),
    [
        ("Nenhum registro encontrado", "não retornou registro"),
        (f"<h1>Dados do processo</h1>{CNJ}", "não confirmou que é um detalhe de 2º grau"),
        (
            f"<h1>2ª Instância - Dados do processo</h1>1.0000.23.212557-5/004 {CNJ}"
            "<table class='corpo'><tr><td>Sem data</td></tr></table>",
            "não retornou movimentos legíveis",
        ),
    ],
)
def test_consulta_classifica_resposta_sem_extrato_util(html, mensagem):
    class Session:
        def get(self, *_args, **_kwargs):
            return _response(html)

    with pytest.raises((ProcessoNaoEncontrado, ConsultaIndisponivel), match=mensagem):
        tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())


@pytest.mark.parametrize("identificador", ["", "abc", "123", "1000023212557500/4"])
def test_consulta_valida_identificador_interno_antes_da_rede(identificador):
    class Session:
        def get(self, *_args, **_kwargs):
            pytest.fail("identificador inválido não pode iniciar requisição")

    with pytest.raises(ValueError, match="17 dígitos"):
        tjmg_legado.consultar_processo(CNJ, identificador, session=Session())


def test_consulta_rejeita_id_que_aponta_para_sequencial_divergente():
    html = f"""<h1>2ª Instância - Dados do processo</h1>
    <p>NÚMERO TJMG: 1.0000.23.212557-5/001</p><p>NUMERAÇÃO ÚNICA: {CNJ}</p>
    <table class="corpo"><tr><td>Decisão</td><td>13/11/2026</td><td></td></tr></table>"""

    class Session:
        def get(self, *_args, **_kwargs):
            return _response(html)

    with pytest.raises(ConsultaIndisponivel, match="diverge do identificador interno"):
        tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())


def test_consulta_lista_somente_documentos_com_vinculo_oficial():
    html = f"""<h1>2ª Instância - Dados do processo</h1>
    <p>NÚMERO TJMG: 1.0000.23.212557-5/004</p><p>NUMERAÇÃO ÚNICA: {CNJ}</p>
    <table class="corpo"><tr><td>Decisão</td><td>13/11/2026</td><td></td>
    <td>{DOCUMENT_LINK}</td>
    </tr></table>"""

    class Session:
        def get(self, url, **_kwargs):
            return _response(html)

    resultado = tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())
    documento = resultado["documentos"]["publicos_candidatos_unicos"][0]
    assert documento["cd_documento"] == "12345"
    assert documento["metadados"]["ano_criacao_doc"] == "2024"
    assert documento["status_acesso"] == "publico_candidato"
    assert resultado["origem"]["documentos_completos"] is False


def test_obter_documento_valida_vinculo_identidade_e_assinatura():
    html = f"""<h1>2ª Instância - Dados do processo</h1>
    <p>NÚMERO TJMG: 1.0000.23.212557-5/004</p><p>NUMERAÇÃO ÚNICA: {CNJ}</p>
    <table class="corpo"><tr><td>Decisão</td><td>13/11/2026</td>
    <td>{DOCUMENT_LINK}</td>
    </tr></table>"""
    conteudo = bytes.fromhex("d0cf11e0a1b11ae1") + b"document"

    class BinaryResponse:
        status_code = 200
        headers = {"Content-Type": "application/msword", "Content-Length": str(len(conteudo))}

        def iter_content(self, chunk_size):
            assert chunk_size > 0
            yield conteudo

        def close(self):
            self.closed = True

    class Session:
        def __init__(self):
            self.urls = []

        def get(self, url, **kwargs):
            self.urls.append(url)
            if "proc_movimentacoes2.jsp" in url:
                assert kwargs["allow_redirects"] is False
                return _response(html)
            assert kwargs["stream"] is True
            return BinaryResponse()

    session = Session()
    data, mimetype = tjmg_legado.obter_documento_publico(
        CNJ, ID_INTERNO, "12345", "2024", session=session
    )
    assert data == conteudo
    assert mimetype == "application/msword"
    assert "downloadPeca2?codigoDocumento=12345&anoCriacaoDoc=2024" in session.urls[-1]


def test_obter_documento_nao_busca_id_que_nao_esta_vinculado():
    html = f"""<h1>2ª Instância - Dados do processo</h1>
    <p>NÚMERO TJMG: 1.0000.23.212557-5/004</p><p>NUMERAÇÃO ÚNICA: {CNJ}</p>
    <table class="corpo"><tr><td>Decisão</td><td>13/11/2026</td>
    <td>{DOCUMENT_LINK}</td>
    </tr></table>"""

    class Session:
        def get(self, *_args, **_kwargs):
            return _response(html)

    with pytest.raises(DocumentoNaoEncontrado, match="não está vinculado"):
        tjmg_legado.obter_documento_publico(CNJ, ID_INTERNO, "54321", "2024", session=Session())


@pytest.mark.parametrize("max_bytes", [0, tjmg_legado.MAX_DOCUMENT_BYTES + 1, True])
def test_obter_documento_valida_limite_antes_da_rede(max_bytes):
    class Session:
        def get(self, *_args, **_kwargs):
            pytest.fail("limite inválido não pode iniciar requisição")

    with pytest.raises(ValueError, match="max_bytes"):
        tjmg_legado.obter_documento_publico(
            CNJ, ID_INTERNO, "12345", "2024", session=Session(), max_bytes=max_bytes
        )


def _html_with_document_link():
    return f"""<h1>2ª Instância - Dados do processo</h1>
    <p>NÚMERO TJMG: 1.0000.23.212557-5/004</p><p>NUMERAÇÃO ÚNICA: {CNJ}</p>
    <table class="corpo"><tr><td>Decisão</td><td>13/11/2026</td>
    <td>{DOCUMENT_LINK}</td></tr></table>"""


def _session_with_document_response(response):
    class Session:
        def __init__(self):
            self.binary_requests = 0

        def get(self, url, **kwargs):
            if "proc_movimentacoes2.jsp" in url:
                return _response(_html_with_document_link())
            self.binary_requests += 1
            assert kwargs["allow_redirects"] is False
            assert kwargs["stream"] is True
            return response

    return Session()


class _StreamingResponse:
    def __init__(self, *, status=200, content_type="application/msword", content_length=""):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        if content_length:
            self.headers["Content-Length"] = content_length
        self.closed = False

    def iter_content(self, chunk_size):
        raise NotImplementedError

    def close(self):
        self.closed = True


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_download_nao_segue_redirecionamento_e_fecha_resposta(status):
    class Response(_StreamingResponse):
        def iter_content(self, *, chunk_size):
            assert chunk_size > 0
            pytest.fail("corpo de resposta redirecionada não deve ser lido")

    response = Response(status=status)
    session = _session_with_document_response(response)
    with pytest.raises(ConsultaIndisponivel, match="redirecionou"):
        tjmg_legado.obter_documento_publico(CNJ, ID_INTERNO, "12345", "2024", session=session)
    assert response.closed is True
    assert session.binary_requests == 1


@pytest.mark.parametrize(
    ("status", "erro"),
    [
        (401, AcessoRestrito),
        (403, AcessoRestrito),
        (412, AcessoRestrito),
        (404, DocumentoNaoEncontrado),
        (500, ConsultaIndisponivel),
    ],
)
def test_download_classifica_status_http_e_fecha_resposta(status, erro):
    class Response(_StreamingResponse):
        def iter_content(self, *, chunk_size):
            pytest.fail("corpo de status HTTP de erro não deve ser consumido")

    response = Response(status=status)
    with pytest.raises(erro):
        tjmg_legado.obter_documento_publico(
            CNJ,
            ID_INTERNO,
            "12345",
            "2024",
            session=_session_with_document_response(response),
        )
    assert response.closed is True


def test_download_rejeita_html_de_erro_antes_de_consumir_corpo():
    class Response(_StreamingResponse):
        def __init__(self):
            super().__init__(content_type="text/html")

        def iter_content(self, *, chunk_size):
            pytest.fail("HTML de erro não deve ser tratado como documento")

    response = Response()
    with pytest.raises(ConsultaIndisponivel, match="tipo de documento suportado"):
        tjmg_legado.obter_documento_publico(
            CNJ,
            ID_INTERNO,
            "12345",
            "2024",
            session=_session_with_document_response(response),
        )
    assert response.closed is True


def test_download_rejeita_content_length_acima_do_limite_e_fecha_resposta():
    class Response(_StreamingResponse):
        def iter_content(self, *, chunk_size):
            assert chunk_size > 0
            pytest.fail("não deve abrir stream quando Content-Length excede o limite")

    response = Response(content_length="16")
    with pytest.raises(ConsultaIndisponivel, match="excede o limite"):
        tjmg_legado.obter_documento_publico(
            CNJ,
            ID_INTERNO,
            "12345",
            "2024",
            session=_session_with_document_response(response),
            max_bytes=15,
        )
    assert response.closed is True


def test_download_interrompe_stream_que_ultrapassa_limite_e_fecha_resposta():
    class Response(_StreamingResponse):
        def iter_content(self, *, chunk_size):
            assert chunk_size > 0
            yield bytes.fromhex("d0cf11e0a1b11ae1")
            yield b"overflow"

    response = Response()
    with pytest.raises(ConsultaIndisponivel, match="excede o limite"):
        tjmg_legado.obter_documento_publico(
            CNJ,
            ID_INTERNO,
            "12345",
            "2024",
            session=_session_with_document_response(response),
            max_bytes=12,
        )
    assert response.closed is True


def test_download_rejeita_assinatura_incompativel_com_mime_e_fecha_resposta():
    class Response(_StreamingResponse):
        def __init__(self):
            super().__init__(content_type="application/pdf")

        def iter_content(self, *, chunk_size):
            assert chunk_size > 0
            yield bytes.fromhex("d0cf11e0a1b11ae1")

    response = Response()
    with pytest.raises(ConsultaIndisponivel, match="não corresponde ao MIME"):
        tjmg_legado.obter_documento_publico(
            CNJ, ID_INTERNO, "12345", "2024", session=_session_with_document_response(response)
        )
    assert response.closed is True


def test_download_classifica_falha_durante_stream_e_fecha_resposta():
    class Response(_StreamingResponse):
        def iter_content(self, *, chunk_size):
            assert chunk_size > 0
            yield bytes.fromhex("d0cf11e0a1b11ae1")
            raise requests.ConnectionError("detalhe de transporte não deve vazar")

    response = Response()
    with pytest.raises(ConsultaIndisponivel, match="ConnectionError"):
        tjmg_legado.obter_documento_publico(
            CNJ, ID_INTERNO, "12345", "2024", session=_session_with_document_response(response)
        )
    assert response.closed is True


def test_consulta_preserva_movimentos_se_pagina_auxiliar_tiver_cnj_divergente():
    html = f"""<h1>2ª Instância - Dados do processo</h1>
    <p>NÚMERO TJMG: 1.0000.23.212557-5/004</p><p>NUMERAÇÃO ÚNICA: {CNJ}</p>
    <table class="corpo"><tr><td>Decisão</td><td>13/11/2026</td><td></td></tr></table>"""
    outro_cnj = "2125575-44.2023.8.13.0001"

    class Session:
        def get(self, url, **_kwargs):
            if "proc_movimentacoes2.jsp" in url:
                return _response(html)
            return _response(f"<p>NÚMERO TJMG: 1.0000.23.212557-5/004</p>{outro_cnj}")

    resultado = tjmg_legado.consultar_processo(CNJ, ID_INTERNO, session=Session())

    assert resultado["movimentacoes"][0]["titulo"] == "Decisão"
    assert "página auxiliar" in " ".join(resultado["avisos"]).casefold()
    assert "partes" not in resultado
