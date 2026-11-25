"""Contrato do catálogo de amostras reais, sem chamadas de rede."""

import json
import re
from datetime import date
from pathlib import Path

from nanojud.sources import AVAILABLE_SOURCES
from nanojud.utils import validar_numero_cnj

CATALOGO = Path(__file__).with_name("live_cases.json")


def test_catalogo_real_tem_identidade_proveniencia_e_escopo():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    ids = set()
    pares = set()
    for caso in casos:
        assert set(caso) in (
            {
                "id",
                "numero",
                "fonte",
                "grau",
                "cenario",
                "estado",
                "evidencia",
                "observado_em",
            },
            {
                "id",
                "numero",
                "fonte",
                "grau",
                "cenario",
                "estado",
                "evidencia",
                "observado_em",
                "metadados_capa",
                "identidades_resultado_confirmadas",
            },
            {
                "id",
                "numero",
                "fonte",
                "grau",
                "cenario",
                "resultado_esperado",
                "estado",
                "evidencia",
                "observado_em",
                "metadados_capa",
            },
            {
                "id",
                "numero",
                "fonte",
                "grau",
                "cenario",
                "resultado_esperado",
                "estado",
                "evidencia",
                "observado_em",
            },
            {
                "id",
                "numero",
                "fonte",
                "grau",
                "cenario",
                "identidades_resultado_confirmadas",
                "estado",
                "evidencia",
                "observado_em",
            },
        )
        assert caso["id"] not in ids
        ids.add(caso["id"])
        assert caso["fonte"] in AVAILABLE_SOURCES
        assert validar_numero_cnj(caso["numero"], segmento=None, tribunal=None) == caso["numero"]
        par = (caso["fonte"], caso["numero"])
        assert par not in pares
        pares.add(par)
        assert caso["cenario"] and caso["evidencia"]
        assert caso["estado"] in {
            "observado",
            "historico",
            "candidato",
            "bloqueado",
            "nao_encontrado",
        }
        if "resultado_esperado" in caso:
            assert caso["resultado_esperado"] in {
                "movimentacoes_documentos_completos",
                "movimentacoes_documentos_multiplas_paginas",
                "movimentacoes_paginadas_completas",
                "zero_ou_comunicacoes_futuras_com_identidade_confirmada",
                "comunicacoes_mais_de_20_com_pagina_repetida",
                "comunicacoes_mais_de_20_paginadas",
            }
        if "metadados_capa" in caso:
            metadados = caso["metadados_capa"]
            assert set(metadados) == {"classe", "orgao_julgador", "vara", "observado_em"}
            assert all(
                isinstance(metadados[campo], str) for campo in ("classe", "orgao_julgador", "vara")
            )
            assert date.fromisoformat(metadados["observado_em"])
        if caso["estado"] != "candidato":
            assert date.fromisoformat(caso["observado_em"])
        else:
            assert caso["observado_em"] is None
        for identidade in caso.get("identidades_resultado_confirmadas", []):
            assert validar_numero_cnj(identidade, segmento="8", tribunal="26") == identidade


def test_referencias_de_evidencia_no_repositorio_existem():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    referencias = re.compile(r"(?<![\w/])((?:reports|docs)/[\w./-]+\.md)(?::\d+(?:,\d+)*)?")

    for caso in casos:
        for caminho in referencias.findall(caso["evidencia"]):
            assert (CATALOGO.parent.parent / caminho).is_file(), (caso["id"], caminho)


def test_catalogo_nao_promove_desafio_ou_protocolo_sem_endpoint_a_sucesso():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    assert all(
        caso["estado"] == "bloqueado" for caso in casos if caso["fonte"].startswith("eproc_tjsp")
    )
    assert not any(caso["fonte"] == "mni" for caso in casos)
    assert {"esaj", "esaj_tjsp_2g", "pje_tjmg", "datajud", "djen", "tjrj_1g"} <= {
        caso["fonte"] for caso in casos
    }


def test_catalogo_confere_tribunal_cnj_com_a_familia_do_adaptador():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    escopos = {
        "esaj": ("8", "26", "1G"),
        "esaj_tjsp_2g": ("8", "26", "2G"),
        "pje_tjmg": ("8", "13", "1G"),
        "eproc_tjsp_1g": ("8", "26", "1G"),
        "eproc_tjsp_2g": ("8", "26", "2G"),
        "tjrj_1g": ("8", "19", "1G"),
    }
    for caso in casos:
        escopo = escopos.get(caso["fonte"])
        if escopo is None:
            continue
        segmento, tribunal, grau = escopo
        assert (
            validar_numero_cnj(caso["numero"], segmento=segmento, tribunal=tribunal)
            == caso["numero"]
        )
        assert caso["grau"] == grau


def test_nao_encontrado_em_um_provedor_nao_e_promovido_a_positivo():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    caso = next(
        item for item in casos if item["id"] == "pje_tjmg_caso_documentado_sem_detalhe_publico"
    )

    assert caso["fonte"] == "pje_tjmg"
    assert caso["estado"] == "nao_encontrado"
    assert "não conta como amostra positiva" in caso["evidencia"]
    assert sum(item["fonte"] == "pje_tjmg" and item["estado"] == "observado" for item in casos) == 5

    datajud = next(item for item in casos if item["id"] == "datajud_rj_sem_registro_publicado")
    tjrj = next(item for item in casos if item["id"] == "tjrj_1g_movimentos_completos")
    assert datajud["numero"] == tjrj["numero"]
    assert datajud["fonte"] == "datajud"
    assert datajud["estado"] == "nao_encontrado"
    assert "226 movimentos" in datajud["evidencia"]


def test_amostra_djen_cobre_tres_tribunais_sem_reusar_numero():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    observados = [
        caso for caso in casos if caso["fonte"] == "djen" and caso["estado"] == "observado"
    ]
    codigos_tribunal = {caso["numero"].split(".")[-2] for caso in observados}
    assert len({caso["numero"] for caso in observados}) >= 5
    assert {"13", "19", "26"} <= codigos_tribunal


def test_amostra_pje_tjmg_registra_diversidade_de_classe_e_orgao_julgador():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    observados = [
        caso
        for caso in casos
        if caso["fonte"] == "pje_tjmg"
        and caso["estado"] == "observado"
        and "metadados_capa" in caso
    ]

    assert len(observados) == 5
    assert len({caso["metadados_capa"]["classe"] for caso in observados}) == 2
    assert len({caso["metadados_capa"]["orgao_julgador"] for caso in observados}) == 5
    assert all(caso["metadados_capa"]["vara"] == "" for caso in observados)


def test_amostra_esaj_tjsp_2g_registra_diversidade_de_camara():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    observados = [
        caso
        for caso in casos
        if caso["fonte"] == "esaj_tjsp_2g"
        and caso["estado"] == "observado"
        and "metadados_capa" in caso
    ]

    assert len(observados) == 4
    assert len({caso["metadados_capa"]["orgao_julgador"] for caso in observados}) == 3
    assert len({caso["metadados_capa"]["classe"] for caso in observados}) == 2
    assert all(caso["grau"] == "2G" for caso in observados)
    assert all(caso["metadados_capa"]["vara"] == "" for caso in observados)
    vinculos = next(caso for caso in casos if caso["id"] == "esaj_2g_vinculos")
    assert "metadados_capa" not in vinculos


def test_tjrj_1g_tem_piso_de_piloto_e_caso_cruzado_com_djen():
    casos = json.loads(CATALOGO.read_text(encoding="utf-8"))
    tjrj = [caso for caso in casos if caso["fonte"] == "tjrj_1g" and caso["estado"] == "observado"]
    assert len(tjrj) >= 3
    terceiro = next(caso for caso in tjrj if caso["id"] == "tjrj_1g_decisao_2023")
    djen = next(caso for caso in casos if caso["id"] == "djen_tjrj_caso_cross_source")
    assert terceiro["numero"] == djen["numero"] == "0184264-47.2023.8.19.0001"
    assert all(
        termo in terceiro["evidencia"]
        for termo in (
            "CNJ idêntico",
            "TJRJ/1G",
            "76 eventos de movimento",
            "movimentacoes_completas=true",
        )
    )
    assert all(termo in djen["evidencia"] for termo in ("9 comunicações", "CNJ idêntico", "TJRJ"))


def test_ampliacoes_recentes_exigem_identidade_e_escopo_na_evidencia():
    casos = {caso["id"]: caso for caso in json.loads(CATALOGO.read_text(encoding="utf-8"))}
    esaj = casos["esaj_1g_decisao_publicada"]
    assert esaj["numero"] == "1000876-57.2018.8.26.0696"
    assert esaj["estado"] == "observado"
    assert all(termo in esaj["evidencia"] for termo in ("CNJ idêntico", "TJSP", "CPoPG", "1G"))

    datajud = casos["datajud_mg_uberlandia"]
    assert datajud["numero"] == "0089724-21.2014.8.13.0702"
    assert datajud["estado"] == "observado"
    assert all(termo in datajud["evidencia"] for termo in ("CNJ idêntico", "TJMG", "G1"))

    djen = casos["djen_mg_uberlandia"]
    assert djen["numero"] == datajud["numero"]
    assert djen["estado"] == "observado"
    assert all(termo in djen["evidencia"] for termo in ("4 comunicações", "CNJ idêntico", "TJMG"))

    migracao = casos["djen_tjmg_eproc_migration"]
    assert migracao["numero"] == "5031212-74.2025.8.13.0701"
    assert migracao["estado"] == "observado"
    assert all(
        termo in migracao["evidencia"]
        for termo in (
            "quatro comunicações",
            "CNJ exato",
            "TJMG",
            "não confirma resultado nem situação atual do processo no eproc",
        )
    )

    pje = casos["pje_tjmg_uberlandia_documentos_completos"]
    assert pje["numero"] == datajud["numero"] == djen["numero"]
    assert pje["resultado_esperado"] == "movimentacoes_documentos_completos"
    assert all(
        termo in pje["evidencia"]
        for termo in ("CNJ/TJMG/1º grau", "movimentos e documentos completos")
    )

    pje_material = casos["pje_tjmg_material_capacitacao"]
    assert pje_material["numero"] == "6000890-97.2015.8.13.0024"
    assert pje_material["estado"] == "observado"
    assert pje_material["resultado_esperado"] == "movimentacoes_documentos_completos"
    assert all(
        termo in pje_material["evidencia"]
        for termo in ("28 movimentos", "2 documentos", "movimentos e documentos completos")
    )

    pje_precatoria = casos["pje_tjmg_carta_precatoria_completa"]
    assert pje_precatoria["numero"] == "5001232-88.2025.8.13.0408"
    assert pje_precatoria["estado"] == "observado"
    assert pje_precatoria["resultado_esperado"] == "movimentacoes_documentos_completos"
    assert all(
        termo in pje_precatoria["evidencia"]
        for termo in ("movimentos e documentos completos", "revalidação em 2026-11-13")
    )
    assert pje_precatoria["metadados_capa"]["orgao_julgador"] == (
        "Vara Única da Comarca de Matias Barbosa"
    )

    tjrj = casos["tjrj_1g_numero_antigo_manual"]
    assert tjrj["numero"] == "0000328-97.2015.8.19.0001"
    assert tjrj["estado"] == "observado"
    assert all(
        termo in tjrj["evidencia"]
        for termo in (
            "CNJ idêntico",
            "TJRJ/1G",
            "74 eventos de movimento",
            "todosMovimentos=true",
        )
    )
