from pathlib import Path

import pytest

from nanojud import esaj
from nanojud.exceptions import ConsultaIndisponivel

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(nome):
    return (FIXTURES / nome).read_text(encoding="utf-8")


PAGINAS = {
    "": "esaj_movimentacoes_pagina1.html",
    "CURSOR2": "esaj_movimentacoes_pagina2.html",
    "CURSOR3": "esaj_movimentacoes_pagina3.html",
}


class FakeResponse:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.content = text.encode("utf-8")


class FakeSession:
    """Simula o eSAJ com movimentações carregadas sob demanda, por cursor."""

    def __init__(self, falhar_no_cursor=None):
        self.cursores = []
        self.falhar_no_cursor = falhar_no_cursor

    def get(self, url, **kwargs):
        if "carregarMovimentacoesAjax.do" in url:
            params = kwargs["params"]
            assert params["processo.codigo"] == "ABC123"
            cursor = params.get("cursor", "")
            self.cursores.append(cursor)
            if cursor == self.falhar_no_cursor:
                return FakeResponse("", url, status_code=503)
            return FakeResponse(_fixture(PAGINAS[cursor]), url)
        if "search.do" in url:
            return FakeResponse(_fixture("esaj_processo_lazy.html"), url)
        return FakeResponse("", url)


def test_carrega_todas_as_paginas_seguindo_o_cursor():
    session = FakeSession()
    pausas = []

    movimentos, completo, aviso = esaj.carregar_movimentacoes_ajax(
        session, "ABC123", limite=None, sleep=pausas.append
    )

    assert session.cursores == ["", "CURSOR2", "CURSOR3"]
    assert [m["titulo"] for m in movimentos][-1] == "Distribuído por Sorteio"
    assert [m["ordem"] for m in movimentos] == [1, 2, 3, 4, 5]
    assert completo is True and aviso == ""
    assert pausas == [esaj.PAUSA_PAGINAS, esaj.PAUSA_PAGINAS]


def test_limite_interrompe_a_paginacao_e_avisa():
    session = FakeSession()

    movimentos, completo, aviso = esaj.carregar_movimentacoes_ajax(
        session, "ABC123", limite=3, sleep=lambda _: None
    )

    assert len(movimentos) == 3
    assert session.cursores == ["", "CURSOR2"]
    assert completo is False
    assert "limitadas a 3" in aviso


def test_falha_no_meio_preserva_o_que_foi_coletado():
    session = FakeSession(falhar_no_cursor="CURSOR2")

    movimentos, completo, aviso = esaj.carregar_movimentacoes_ajax(
        session, "ABC123", limite=None, sleep=lambda _: None
    )

    assert len(movimentos) == 2
    assert completo is False
    assert "incompletas" in aviso


def test_extrato_usa_ajax_quando_a_pagina_nao_traz_a_tabela():
    extrato = esaj.montar_extrato(
        "1076539-20.2019.8.26.0100", session=FakeSession(), pausa_paginas=0
    )

    assert len(extrato["movimentacoes"]) == 5
    assert extrato["movimentacoes"][0]["data"] == "29/07/2026"
    assert extrato["origem"]["movimentacoes_completas"] is True


def test_extrato_com_limite_sinaliza_movimentacoes_incompletas():
    extrato = esaj.montar_extrato(
        "1076539-20.2019.8.26.0100",
        session=FakeSession(),
        limite_movimentacoes=2,
        pausa_paginas=0,
    )

    assert len(extrato["movimentacoes"]) == 2
    assert extrato["origem"]["movimentacoes_completas"] is False
    assert extrato["origem"]["aviso_movimentacoes"]


def test_pagina_estatica_nao_dispara_requisicao_ajax():
    html = (FIXTURES / "esaj_processo_basico.html").read_text(encoding="utf-8")

    class SessaoEstatica(FakeSession):
        def get(self, url, **kwargs):
            if "search.do" in url:
                return FakeResponse(html, url)
            assert "carregarMovimentacoesAjax" not in url
            return FakeResponse("", url)

    extrato = esaj.montar_extrato("1076539-20.2019.8.26.0100", session=SessaoEstatica())

    assert extrato["origem"]["movimentacoes_completas"] is True


def test_primeira_pagina_indisponivel_nao_derruba_o_extrato():
    session = FakeSession(falhar_no_cursor="")
    with pytest.raises(ConsultaIndisponivel):
        esaj._get(session, esaj.MOVIMENTACOES_AJAX_URL, params={"processo.codigo": "ABC123"})

    extrato = esaj.montar_extrato("1076539-20.2019.8.26.0100", session=session, pausa_paginas=0)

    assert extrato["movimentacoes"] == []
    assert extrato["origem"]["movimentacoes_completas"] is False
