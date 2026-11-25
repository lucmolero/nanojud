import json
from pathlib import Path

import pytest

from nanojud import esaj


class FakeResponse:
    status_code = 200

    def __init__(
        self,
        text="",
        content=b"",
        url="https://esaj.tjsp.jus.br/pastadigital/doc",
        headers=None,
    ):
        self.text = text
        self.content = content or text.encode("utf-8")
        self.url = url
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        return self.responses.pop(0)


def _request_scope():
    scope = [
        {
            "data": {
                "title": "Decisão",
                "cdDocumento": "123456",
                "cdFormatoDoc": "1",
                "sigiloAbsoluto": False,
                "flPeticaoInicial": False,
                "flProtocolado": True,
            },
            "children": [
                {
                    "data": {
                        "title": "Página 1",
                        "indicePagina": 1,
                        "nuPaginas": 2,
                        "documentoSigiloso": False,
                        "possuiDocumentoOriginal": True,
                        "parametros": (
                            "numInicial=1&numFinal=2&nuPagina=1&idDocumento=ABC&"
                            "sigiloExterno=false&cdFormatoDoc=1"
                        ),
                    }
                }
            ],
        }
    ]
    return f"<script>var requestScope = {json.dumps(scope)};</script>"


def _movimentos(doc):
    return [{"documentos": [doc]}]


@pytest.mark.parametrize(
    ("metadata", "response", "status"),
    [
        ({"status": "restrito_por_senha"}, None, "restrito_por_senha"),
        ({"status": "ok", "paginas": []}, None, "sem_paginas"),
        (
            {"status": "ok", "paginas": [{"parametros_pdf": "doc=123"}]},
            FakeResponse(text="<p>Sua sessão expirou</p>"),
            "sessao_expirada",
        ),
        (
            {"status": "ok", "paginas": [{"parametros_pdf": "doc=123"}]},
            FakeResponse(content=b"%PDF-1.7"),
            "pdf_parser_indisponivel",
        ),
    ],
)
def test_leitura_de_peca_informa_por_que_texto_nao_foi_extraido(
    monkeypatch, metadata, response, status
):
    doc = {
        "cd_documento": "123",
        "href": "https://esaj.tjsp.jus.br/cpopg/abrirDocumento.do?cdDocumento=123",
        "status_acesso": "publico_candidato",
        "pasta_digital": metadata,
    }
    sessao = FakeSession([] if response is None else [response])
    monkeypatch.setattr(esaj, "_aguardar_ritmo", lambda: None)
    monkeypatch.setattr(
        esaj, "extrair_texto_pdf_bytes", lambda *a, **k: ("", "pdf_parser_indisponivel")
    )

    [resultado] = esaj.ler_pecas_publicas(sessao, _movimentos(doc))

    assert resultado["cd_documento"] == "123"
    assert resultado["status"] == status
    assert not resultado.get("texto")
    assert len(sessao.calls) == int(response is not None)


def test_obter_metadados_pasta_documento_parseia_request_scope():
    session = FakeSession([FakeResponse(text=_request_scope())])

    metadados = esaj.obter_metadados_pasta_documento(
        session,
        {"href": "https://esaj.tjsp.jus.br/pastadigital/viewer"},
    )

    assert metadados["status"] == "ok"
    assert metadados["cd_documento"] == "123456"
    assert metadados["total_paginas_no_documento"] == 1
    assert metadados["paginas"][0]["id_documento"] == "ABC"


def test_download_de_peca_aplica_timeout_a_metadados_e_pdf(tmp_path):
    session = FakeSession(
        [
            FakeResponse(text=_request_scope()),
            FakeResponse(content=b"%PDF-1.7 documento"),
        ]
    )
    documento = {
        "cd_documento": "123456",
        "titulo": "Decisao",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
    }

    resultado = esaj.baixar_pecas_publicas(
        session, _movimentos(documento), tmp_path, limite=1, timeout=7
    )

    assert resultado[0]["status"] == "baixado"
    assert [chamada["kwargs"]["timeout"] for chamada in session.calls] == [7, 7]


def test_leitura_de_peca_aplica_timeout_a_metadados_e_pdf():
    session = FakeSession(
        [
            FakeResponse(text=_request_scope()),
            FakeResponse(content=b"%PDF-1.7 documento"),
        ]
    )
    documento = {
        "cd_documento": "123456",
        "titulo": "Decisao",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
    }

    esaj.ler_pecas_publicas(session, _movimentos(documento), limite=1, timeout=7)

    assert [chamada["kwargs"]["timeout"] for chamada in session.calls] == [7, 7]


def test_leitura_esaj_interrompe_pdf_acima_do_limite_em_memoria():
    class RespostaGrande:
        status_code = 200
        headers = {"Content-Length": "11"}

        def __init__(self):
            self.closed = False

        def iter_content(self, chunk_size):
            pytest.fail("Content-Length deve rejeitar antes de ler o corpo")

        def close(self):
            self.closed = True

    resposta = RespostaGrande()
    session = FakeSession([resposta])
    documento = {
        "cd_documento": "123456",
        "titulo": "Decisao",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
        "pasta_digital": {
            "status": "ok",
            "paginas": [{"parametros_pdf": "idDocumento=ABC"}],
        },
    }

    resultado = esaj.ler_pecas_publicas(
        session, _movimentos(documento), limite=1, max_chars=100, max_bytes=10
    )

    assert resultado[0]["status"] == "documento_muito_grande"
    assert resposta.closed is True
    assert session.calls[0]["kwargs"]["stream"] is True


def test_leitura_esaj_para_o_stream_ao_exceder_limite():
    class RespostaEmBlocos:
        status_code = 200
        headers = {}

        def __init__(self):
            self.closed = False
            self.chunks_lidos = 0

        def iter_content(self, chunk_size):
            self.chunks_lidos += 1
            yield b"%PDF-1.7"
            self.chunks_lidos += 1
            yield b"12345"
            self.chunks_lidos += 1
            pytest.fail("o stream deve parar no primeiro bloco acima do limite")

        def close(self):
            self.closed = True

    resposta = RespostaEmBlocos()
    documento = {
        "cd_documento": "123456",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
        "pasta_digital": {
            "status": "ok",
            "paginas": [{"parametros_pdf": "idDocumento=ABC"}],
        },
    }

    resultado = esaj.ler_pecas_publicas(
        FakeSession([resposta]), _movimentos(documento), limite=1, max_bytes=10
    )

    assert resultado[0]["status"] == "documento_muito_grande"
    assert resposta.chunks_lidos == 2
    assert resposta.closed is True


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1.5, "10", 8 * 1024 * 1024 + 1])
def test_leitura_esaj_valida_limite_de_memoria_antes_de_io(max_bytes):
    with pytest.raises(ValueError, match="max_bytes"):
        esaj.ler_pecas_publicas(FakeSession([]), [], max_bytes=max_bytes)


def test_obter_metadados_pasta_documento_sem_request_scope():
    session = FakeSession([FakeResponse(text="<html>sem escopo</html>", url="https://final")])

    metadados = esaj.obter_metadados_pasta_documento(
        session,
        {"href": "https://esaj.tjsp.jus.br/pastadigital/viewer"},
    )

    assert metadados == {"status": "sem_request_scope", "url_final": "https://final"}


def test_iterar_docs_publicos_filtra_e_deduplica():
    docs = list(
        esaj.iterar_docs_publicos(
            [
                {
                    "documentos": [
                        {"cd_documento": "1", "status_acesso": "publico_candidato"},
                        {"cd_documento": "1", "status_acesso": "publico_candidato"},
                        {"cd_documento": "2", "status_acesso": "restrito_por_senha"},
                        {"cd_documento": "", "status_acesso": "publico_candidato"},
                    ]
                }
            ]
        )
    )

    assert docs == [{"cd_documento": "1", "status_acesso": "publico_candidato"}]


def test_inspecionar_pecas_publicas_respeita_limite(monkeypatch):
    monkeypatch.setattr(
        esaj,
        "obter_metadados_pasta_documento",
        lambda session, doc, **kwargs: {"status": "ok", "cd_documento": doc["cd_documento"]},
    )
    movimentos = _movimentos(
        {"cd_documento": "1", "titulo": "Decisão", "status_acesso": "publico_candidato"}
    )

    resultado = esaj.inspecionar_pecas_publicas(object(), movimentos, limite=1)

    assert resultado[0]["pasta_digital"]["cd_documento"] == "1"


def test_inspecionar_pecas_publicas_registra_erro(monkeypatch):
    def falha(session, doc, **kwargs):
        raise RuntimeError("fonte indisponível")

    monkeypatch.setattr(esaj, "obter_metadados_pasta_documento", falha)
    movimentos = _movimentos(
        {"cd_documento": "1", "titulo": "Decisão", "status_acesso": "publico_candidato"}
    )

    resultado = esaj.inspecionar_pecas_publicas(object(), movimentos, limite=0)

    assert resultado[0]["pasta_digital"]["status"] == "erro"
    assert "fonte indisponível" in resultado[0]["pasta_digital"]["mensagem"]


def test_baixar_pecas_publicas_baixa_pdf(tmp_path):
    session = FakeSession([FakeResponse(content=b"%PDF-1.4 fake")])
    doc = {
        "cd_documento": "123",
        "titulo": "Decisão",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "idDocumento=ABC"}]},
    }

    resultado = esaj.baixar_pecas_publicas(session, _movimentos(doc), tmp_path / "pecas", limite=1)

    assert resultado[0]["status"] == "baixado"
    assert Path(resultado[0]["arquivo"]).read_bytes().startswith(b"%PDF")


def test_baixar_pecas_publicas_aplica_limite_por_documento(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        esaj,
        "_baixar_pdf_atomico",
        lambda *args, **kwargs: chamadas.append(kwargs["max_bytes"]) or ("baixado", 8, ""),
    )
    doc = {
        "cd_documento": "123",
        "titulo": "Decisão",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "idDocumento=ABC"}]},
    }

    resultado = esaj.baixar_pecas_publicas(
        FakeSession([]), _movimentos(doc), tmp_path, limite=1, max_bytes=4096
    )

    assert resultado[0]["status"] == "baixado"
    assert chamadas == [4096]


@pytest.mark.parametrize("max_bytes", [0, 1.5, "32", None, True])
def test_baixar_pecas_publicas_rejeita_limite_invalido(tmp_path, max_bytes):
    import pytest

    with pytest.raises(ValueError, match="max_bytes"):
        esaj.baixar_pecas_publicas(
            FakeSession([]),
            _movimentos({"cd_documento": "1"}),
            tmp_path,
            limite=1,
            max_bytes=max_bytes,
        )


def test_baixar_pecas_publicas_nao_requisita_arquivo_existente(tmp_path):
    pasta = tmp_path / "pecas"
    pasta.mkdir()
    destino = pasta / "peca_123_Decis_o.pdf"
    destino.write_bytes(b"%PDF-1.4 ja baixado")
    doc = {
        "cd_documento": "123",
        "titulo": "Decisão",
        "status_acesso": "publico_candidato",
    }

    resultado = esaj.baixar_pecas_publicas(FakeSession([]), _movimentos(doc), pasta, limite=1)

    assert resultado[0]["status"] == "existente"
    assert doc["download_status"] == "existente"


def test_baixar_pecas_publicas_substitui_arquivo_existente_que_nao_e_pdf(tmp_path):
    pasta = tmp_path / "pecas"
    pasta.mkdir()
    destino = pasta / "peca_123_Decis_o.pdf"
    destino.write_bytes(b"resposta HTML armazenada por engano")
    doc = {
        "cd_documento": "123",
        "titulo": "Decisão",
        "status_acesso": "publico_candidato",
        "pasta_digital": {
            "status": "ok",
            "paginas": [{"parametros_pdf": "idDocumento=123"}],
        },
    }
    session = FakeSession([FakeResponse(content=b"%PDF-1.7 documento valido")])

    resultado = esaj.baixar_pecas_publicas(session, _movimentos(doc), pasta, limite=1)

    assert resultado[0]["status"] == "baixado"
    assert destino.read_bytes() == b"%PDF-1.7 documento valido"
    assert len(session.calls) == 1


def test_download_pdf_recusa_tamanho_excedido_sem_publicar_arquivo(tmp_path):
    resposta = FakeResponse(content=b"%PDF-1.4 conteudo")
    status, gravados, preview = esaj._baixar_pdf_atomico(
        FakeSession([resposta]),
        "https://esaj.tjsp.jus.br/pastadigital/pdf",
        tmp_path / "doc.pdf",
        timeout=1,
        max_bytes=5,
    )

    assert status == "documento_muito_grande"
    assert gravados == 0
    assert preview == ""
    assert not (tmp_path / "doc.pdf").exists()


def test_baixar_pecas_publicas_marca_nao_pdf():
    session = FakeSession([FakeResponse(content=b"<html>erro</html>")])
    doc = {
        "cd_documento": "123",
        "titulo": "Decisão",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "idDocumento=ABC"}]},
    }

    resultado = esaj.baixar_pecas_publicas(session, _movimentos(doc), Path("pecas"), limite=1)

    assert resultado == []
    assert doc["download_status"] == "nao_pdf"


def test_baixar_pecas_publicas_marca_sem_paginas():
    doc = {
        "cd_documento": "123",
        "titulo": "Decisão",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "ok", "paginas": []},
    }

    resultado = esaj.baixar_pecas_publicas(
        FakeSession([]), _movimentos(doc), Path("pecas"), limite=1
    )

    assert resultado == []
    assert doc["download_status"] == "sem_paginas"


def test_baixar_pecas_publicas_marca_status_pasta_digital():
    doc = {
        "cd_documento": "123",
        "titulo": "Decisão",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "sem_request_scope"},
    }

    resultado = esaj.baixar_pecas_publicas(
        FakeSession([]), _movimentos(doc), Path("pecas"), limite=1
    )

    assert resultado == []
    assert doc["download_status"] == "sem_request_scope"


def test_baixar_pecas_publicas_respeita_limite_zero_com_multiplos_docs(tmp_path):
    session = FakeSession([FakeResponse(content=b"%PDF one"), FakeResponse(content=b"%PDF two")])
    docs = [
        {
            "cd_documento": "1",
            "titulo": "Um",
            "status_acesso": "publico_candidato",
            "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "id=1"}]},
        },
        {
            "cd_documento": "2",
            "titulo": "Dois",
            "status_acesso": "publico_candidato",
            "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "id=2"}]},
        },
    ]

    resultado = esaj.baixar_pecas_publicas(
        session, [{"documentos": docs}], tmp_path / "pecas", limite=0
    )

    assert [item["cd_documento"] for item in resultado] == ["1", "2"]


def test_ler_pecas_publicas_pdf_em_memoria(monkeypatch):
    monkeypatch.setattr(
        esaj,
        "extrair_texto_pdf_bytes",
        lambda conteudo, max_chars: ("texto da decisao", "texto_extraido"),
    )
    session = FakeSession([FakeResponse(content=b"%PDF-1.4 fake")])
    doc = {
        "cd_documento": "123",
        "titulo": "Decisao",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "idDocumento=ABC"}]},
    }

    resultado = esaj.ler_pecas_publicas(session, _movimentos(doc), limite=1, max_chars=200)

    assert resultado[0]["status"] == "texto_extraido"
    assert resultado[0]["texto"] == "texto da decisao"
    assert "arquivo" not in resultado[0]


def test_ler_pecas_publicas_html_em_memoria():
    session = FakeSession(
        [
            FakeResponse(
                text="<html><body><p>Texto publico</p></body></html>",
                headers={"Content-Type": "text/html"},
            )
        ]
    )
    doc = {
        "cd_documento": "123",
        "titulo": "Despacho",
        "href": "https://esaj.tjsp.jus.br/pastadigital/viewer",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "idDocumento=ABC"}]},
    }

    resultado = esaj.ler_pecas_publicas(session, _movimentos(doc), limite=1, max_chars=200)

    assert resultado[0]["status"] == "texto_html_extraido"
    assert resultado[0]["texto"] == "Texto publico"


def test_extrair_texto_pdf_bytes_sem_parser(monkeypatch):
    def fail_import(name):
        raise ImportError(name)

    monkeypatch.setattr(esaj.importlib, "import_module", fail_import)

    texto, status = esaj.extrair_texto_pdf_bytes(b"%PDF fake")

    assert texto == ""
    assert status == "pdf_parser_indisponivel"


@pytest.mark.parametrize(
    ("status", "fragmento"),
    [
        ("pdf_parser_indisponivel", "nanojud[pdf]"),
        ("pdf_sem_texto_extraido", "digitalizado como imagem"),
    ],
)
def test_mensagem_status_pdf_explica_por_que_texto_nao_foi_obtido(status, fragmento):
    assert fragmento in esaj.mensagem_status_extracao_pdf(status)


def test_limite_de_download_conta_candidatas_com_falha(monkeypatch, tmp_path):
    docs = [{"cd_documento": str(i), "status_acesso": "publico_candidato"} for i in range(1, 4)]
    chamadas = []

    def obter_metadados(session, doc, **kwargs):
        chamadas.append(doc["cd_documento"])
        return {"status": "sessao_expirada"}

    monkeypatch.setattr(esaj, "obter_metadados_pasta_documento", obter_metadados)
    assert esaj.baixar_pecas_publicas(object(), [{"documentos": docs}], tmp_path, limite=1) == []
    assert chamadas == ["1"]
    assert docs[0]["download_status"] == "sessao_expirada"
    assert "download_status" not in docs[1]


@pytest.mark.parametrize("limite", [-1, 1.5, "1", None, True])
def test_leitura_e_download_esaj_rejeitam_limite_invalido_antes_de_io(tmp_path, limite):
    with pytest.raises(ValueError, match="limite"):
        esaj.ler_pecas_publicas(FakeSession([]), [], limite=limite)
    with pytest.raises(ValueError, match="limite"):
        esaj.baixar_pecas_publicas(FakeSession([]), [], tmp_path / "nao-criada", limite=limite)

    assert not (tmp_path / "nao-criada").exists()


@pytest.mark.parametrize("max_chars", [-1, 1.5, "10", None, True])
def test_leitura_esaj_rejeita_max_chars_invalido_antes_de_io(max_chars):
    with pytest.raises(ValueError, match="max_chars"):
        esaj.ler_pecas_publicas(FakeSession([]), [], max_chars=max_chars)
    with pytest.raises(ValueError, match="max_chars"):
        esaj.extrair_texto_pdf_bytes(b"%PDF fixture", max_chars=max_chars)
