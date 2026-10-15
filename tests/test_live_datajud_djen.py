import os

import pytest

from nanojud import datajud, djen

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("NANOJUD_RUN_LIVE") != "1", reason="defina NANOJUD_RUN_LIVE=1"),
]

PROCESSO_DEMO = "0015020-23.2010.8.26.0053"


def test_live_datajud_retorna_registro_com_movimentos_e_graus():
    resultado = datajud.consultar_processo(PROCESSO_DEMO)

    assert resultado["status"] == "ok"
    assert resultado["movimentos"]
    assert resultado["graus"]
    assert all(mov["grau"] for mov in resultado["movimentos"])


def test_live_djen_retorna_comunicacoes_com_numero_do_processo():
    comunicacoes = djen.consultar_processo(PROCESSO_DEMO)

    assert comunicacoes
    assert {c["numero_processo"] for c in comunicacoes} == {PROCESSO_DEMO}
