from nanojud.divergencias import detectar_divergencias
from nanojud.normalization import normalizar_data


def _esaj(
    classe="Mandado de Segurança Cível", distribuicao="14/05/2010 às 11:53 - Livre", datas=()
):
    return {
        "dados_basicos": {"classe": classe, "distribuicao": distribuicao},
        "movimentacoes": [{"data": d} for d in datas],
    }


def _datajud(
    classe="Mandado de Segurança Cível", ajuizamento="20100514115300", datas=(), graus=None
):
    return {
        "status": "ok",
        "classe": classe,
        "graus": graus or [{"grau": "G1", "data_ajuizamento": ajuizamento, "total_movimentos": 1}],
        "movimentos": [{"data": d} for d in datas],
    }


def _campos(divergencias):
    return {d["campo"]: d for d in divergencias}


def test_fontes_coerentes_nao_geram_divergencia():
    data = {
        "esaj": _esaj(datas=["23/08/2026", "01/01/2020"]),
        "datajud": _datajud(datas=["2026-08-23", "2020-01-01"]),
    }

    assert detectar_divergencias(data) == []


def test_detecta_classe_distribuicao_e_ultima_movimentacao():
    data = {
        "esaj": _esaj(datas=["23/08/2026"]),
        "datajud": _datajud(
            classe="Requisição de Pequeno Valor",
            ajuizamento="2019-09-11T10:41:43.000Z",
            datas=["2026-08-18"],
        ),
    }

    campos = _campos(detectar_divergencias(data))

    assert campos["classe"]["valores"] == {
        "esaj": "Mandado de Segurança Cível",
        "datajud": "Requisição de Pequeno Valor",
    }
    assert campos["data_distribuicao"]["valores"] == {"esaj": "2010-05-14", "datajud": "2019-09-11"}
    assert campos["ultima_movimentacao"]["valores"] == {
        "esaj": "2026-08-23",
        "datajud": "2026-08-18",
    }


def test_classe_com_nome_contido_nao_e_divergencia():
    data = {
        "esaj": _esaj(classe="Procedimento Comum"),
        "datajud": _datajud(classe="Procedimento Comum Cível"),
    }

    assert "classe" not in _campos(detectar_divergencias(data))


def test_informa_varios_graus_e_comunicacoes_de_incidente():
    graus = [
        {"grau": "G1", "data_ajuizamento": "", "total_movimentos": 292},
        {"grau": "G2", "data_ajuizamento": "", "total_movimentos": 27},
    ]
    data = {
        "datajud": _datajud(graus=graus),
        "djen": [{"incidente": "47"}, {"incidente": ""}, {"incidente": "47"}],
    }

    campos = _campos(detectar_divergencias(data))

    assert campos["graus"]["severidade"] == "informacao"
    assert campos["djen_incidentes"]["valores"] == {"djen": "2 de 3"}


def test_sem_esaj_nao_compara_nada():
    assert detectar_divergencias({"datajud": _datajud()}) == []


def test_normalizar_data_aceita_formato_compacto_do_datajud():
    assert normalizar_data("20120910171334")["iso"] == "2012-09-10"
