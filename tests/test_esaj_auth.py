from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from nanojud import esaj

PROCESS_URL = (
    "https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=ABC"
    "&processo.foro=100&processo.numero=0000000-00.0000.8.26.0100"
)
FORM = """
<form id="popupSenha" method="POST" action="/cpopg/show.do">
  <input type="hidden" name="_csrf" value="csrf-test">
  <input type="hidden" name="idRecursoQueProvocouLiberacaoPorSenha" value="">
  <input type="password" name="senhaProcesso">
  <input type="submit" id="btEnviarSenha" name="btEnviarSenha" value="Acessar">
</form>
"""


class _FakeSession:
    def __init__(self, body: str = "") -> None:
        self.body = body
        self.posted: dict[str, str] = {}
        self.posted_calls: list[dict[str, str]] = []

    def post(self, url: str, *, data: dict[str, str], **kwargs: object) -> SimpleNamespace:
        self.posted = data
        self.posted_calls.append(data.copy())
        return SimpleNamespace(status_code=200, text=self.body, url=url)


def _doc() -> dict[str, str]:
    return {
        "cd_documento": "123",
        "id_recurso": "linkMovVincProc-123",
        "href": "https://esaj.tjsp.jus.br/cpopg/#liberarAutoPorSenha",
        "status_acesso": "restrito_por_senha",
    }


def test_senha_oficial_atualiza_links_e_nao_retorna_segredo(monkeypatch) -> None:
    alvo = _doc()
    session = _FakeSession()
    monkeypatch.setattr(
        esaj,
        "carregar_pagina",
        lambda *args, **kwargs: SimpleNamespace(text=FORM, url=PROCESS_URL),
    )
    monkeypatch.setattr(
        esaj,
        "carregar_movimentacoes_ajax",
        lambda *args, **kwargs: (
            [
                {
                    "documentos": [
                        {
                            "cd_documento": "123",
                            "href": "https://esaj.tjsp.jus.br/cpopg/abrirDocumento.do?cdDocumento=123",
                            "id_recurso": "linkMovVincProc-123",
                            "status_acesso": "publico_candidato",
                        }
                    ]
                }
            ],
            True,
            "",
        ),
    )

    resultado = esaj.liberar_autos_com_senha(
        session, PROCESS_URL, [{"documentos": [alvo]}], "senha-de-teste"
    )

    assert session.posted["senhaProcesso"] == "senha-de-teste"
    assert session.posted["idRecursoQueProvocouLiberacaoPorSenha"] == "linkMovVincProc-123"
    assert resultado["status"] == "liberado"
    assert resultado["documentos_liberados"] == 1
    assert alvo["status_acesso"] == "publico_candidato"
    assert "senha-de-teste" not in repr(resultado)


def test_senha_incorreta_permanece_restrita(monkeypatch) -> None:
    alvo = _doc()
    session = _FakeSession("<div class='msgErroSenha'>Senha incorreta</div>")
    monkeypatch.setattr(
        esaj,
        "carregar_pagina",
        lambda *args, **kwargs: SimpleNamespace(text=FORM, url=PROCESS_URL),
    )

    resultado = esaj.liberar_autos_com_senha(
        session, PROCESS_URL, [{"documentos": [alvo]}], "senha-errada"
    )

    assert resultado["status"] == "senha_invalida"
    assert alvo["status_autorizacao"] == "senha_invalida"
    assert alvo["status_acesso"] == "restrito_por_senha"
    assert "senha-errada" not in repr(resultado)


@pytest.mark.parametrize(
    ("status", "location", "esperado"),
    [
        (302, "/sajcas/login", "identificacao_do_advogado_necessaria"),
        (302, "https://example.test/externo", "redirecionamento_externo_nao_seguido"),
        (403, "", "identificacao_do_advogado_necessaria"),
        (429, "", "erro_http_do_portal"),
        (None, "", "erro_de_comunicacao"),
    ],
)
def test_senha_diferencia_falhas_do_portal_de_senha_invalida(
    monkeypatch, status, location, esperado
):
    alvo = _doc()
    duplicado = _doc()
    monkeypatch.setattr(
        esaj, "carregar_pagina", lambda *a, **k: SimpleNamespace(text=FORM, url=PROCESS_URL)
    )
    monkeypatch.setattr(esaj, "_aguardar_ritmo", lambda: None)

    def post(url, **kwargs):
        assert kwargs["allow_redirects"] is False
        if status is None:
            raise requests.Timeout("detalhe que não deve ser propagado")
        return SimpleNamespace(status_code=status, headers={"Location": location})

    resultado = esaj.liberar_autos_com_senha(
        SimpleNamespace(post=post),
        PROCESS_URL,
        [{"documentos": [alvo]}, {"documentos": [duplicado]}],
        "senha-teste",
    )

    assert resultado["status"] == alvo["status_autorizacao"] == esperado
    assert duplicado["status_autorizacao"] == esperado
    assert resultado["documentos_liberados"] == 0
    assert alvo["status_acesso"] == "restrito_por_senha"
    assert "senha-teste" not in repr(resultado)
    if status == 429:
        assert resultado["http_status"] == status


def test_senha_preserva_restricao_quando_formulario_desaparece(monkeypatch):
    alvo = _doc()
    monkeypatch.setattr(
        esaj, "carregar_pagina", lambda *a, **k: SimpleNamespace(text="", url=PROCESS_URL)
    )

    resultado = esaj.liberar_autos_com_senha(
        SimpleNamespace(), PROCESS_URL, [{"documentos": [alvo]}], "senha-teste"
    )

    assert resultado["status"] == "formulario_senha_indisponivel"
    assert resultado["documentos_liberados"] == 0
    assert alvo["status_acesso"] == "restrito_por_senha"


def test_senha_submete_uma_vez_quando_o_mesmo_documento_aparece_em_varios_movimentos(
    monkeypatch,
):
    primeiro = _doc()
    duplicado = _doc()
    session = _FakeSession()
    monkeypatch.setattr(
        esaj,
        "carregar_pagina",
        lambda *args, **kwargs: SimpleNamespace(text=FORM, url=PROCESS_URL),
    )
    monkeypatch.setattr(
        esaj,
        "carregar_movimentacoes_ajax",
        lambda *args, **kwargs: (
            [
                {
                    "documentos": [
                        {
                            "cd_documento": "123",
                            "href": "https://esaj.tjsp.jus.br/cpopg/abrirDocumento.do?cdDocumento=123",
                            "id_recurso": "linkMovVincProc-123",
                            "status_acesso": "publico_candidato",
                        }
                    ]
                }
            ],
            True,
            "",
        ),
    )

    resultado = esaj.liberar_autos_com_senha(
        session,
        PROCESS_URL,
        [{"documentos": [primeiro]}, {"documentos": [duplicado]}],
        "senha-de-teste",
    )

    assert len(session.posted_calls) == 1
    assert resultado["tentativas"] == 1
    assert resultado["documentos_liberados"] == 1
    assert primeiro["status_acesso"] == duplicado["status_acesso"] == "publico_candidato"


def test_senha_mantem_documento_restrito_quando_portal_nao_confirma_liberacao(monkeypatch):
    alvo = _doc()
    monkeypatch.setattr(
        esaj,
        "carregar_pagina",
        lambda *args, **kwargs: SimpleNamespace(text=FORM, url=PROCESS_URL),
    )
    monkeypatch.setattr(
        esaj,
        "carregar_movimentacoes_ajax",
        lambda *args, **kwargs: (
            [{"documentos": [_doc()]}],
            True,
            "",
        ),
    )

    resultado = esaj.liberar_autos_com_senha(
        _FakeSession(), PROCESS_URL, [{"documentos": [alvo]}], "senha-de-teste"
    )

    assert resultado["status"] == "nao_liberado_pelo_portal"
    assert resultado["tentativas"] == 1
    assert resultado["documentos_liberados"] == 0
    assert alvo["status_acesso"] == "restrito_por_senha"
    assert alvo["status_autorizacao"] == "nao_liberado_pelo_portal"
