import os

import pytest

from nanojud import esaj

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.getenv("NANOJUD_RUN_LIVE") == "1"


@pytest.mark.skipif(not _live_enabled(), reason="defina NANOJUD_RUN_LIVE=1")
def test_live_esaj_public_process_with_hidden_password_popup():
    extrato = esaj.montar_extrato(
        "1076539-20.2019.8.26.0100",
        session=esaj.criar_session(timeout=25),
        salvar_html=False,
    )

    partes = extrato["partes"]
    documentos = extrato["documentos"]

    completo = extrato["origem"]["movimentacoes_completas"]
    assert extrato["status"] == ("ok" if completo else "partial")
    if not completo:
        assert extrato["origem"]["aviso_movimentacoes"]
    assert extrato["dados_basicos"]["numero"] == "1076539-20.2019.8.26.0100"
    assert extrato["dados_basicos"]["classe"]
    assert len(partes["principais"]) >= 1
    assert len(extrato["movimentacoes"]) >= 1
    assert (
        len(documentos["publicos_candidatos_unicos"])
        + len(documentos["restritos_por_senha_unicos"])
        >= 1
    )
