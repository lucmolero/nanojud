"""Amostragem ampliada opt-in; valida identidade sem fixar contagens mutáveis."""

import json
import os
from pathlib import Path

import pytest

from nanojud import api, datajud, djen, eproc_tjsp, esaj, esaj_tjsp_2g, pje_tjmg, tjrj
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado
from nanojud.utils import validar_numero_cnj

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("NANOJUD_RUN_LIVE") != "1" or os.getenv("NANOJUD_LIVE_PROFILE") != "ampliado",
        reason="defina NANOJUD_RUN_LIVE=1 e NANOJUD_LIVE_PROFILE=ampliado",
    ),
]

CASOS = {
    caso["id"]: caso
    for caso in json.loads(Path(__file__).with_name("live_cases.json").read_text(encoding="utf-8"))
}


def ids_observados(fonte):
    """Inclui somente positivos observados naquela fonte, nunca candidatos/históricos."""
    return [
        caso["id"]
        for caso in CASOS.values()
        if caso["fonte"] == fonte and caso["estado"] == "observado"
    ]


def ids_estado(fonte, estado):
    """Seleciona um estado específico da fonte para revalidar positivos ou negativos."""
    return [
        caso["id"] for caso in CASOS.values() if caso["fonte"] == fonte and caso["estado"] == estado
    ]


@pytest.mark.parametrize("id_caso", ids_observados("esaj"))
def test_live_esaj_1g_amostras_distintas(id_caso):
    numero = CASOS[id_caso]["numero"]
    with esaj.criar_session(timeout=25) as sessao:
        extrato = esaj.montar_extrato(
            numero,
            session=sessao,
            salvar_html=False,
            baixar_pecas=False,
            limite_movimentacoes=100,
            timeout=25,
        )
    assert extrato["dados_basicos"]["numero"] == numero
    assert extrato["movimentacoes"]


def test_live_esaj_1g_nao_localiza_recurso_confirmado_em_2g():
    caso = CASOS["esaj_1g_recurso_2g_nao_localizado"]
    resultado = api.extract_process(
        caso["numero"],
        sources=("esaj",),
        limite_movimentacoes=1,
        timeout=20,
        prazo_total=25,
    )
    status = resultado["source_status"]["esaj"]
    assert status["status"] == "error"
    assert status["type"] == "ProcessoNaoEncontrado"


@pytest.mark.parametrize(
    ("id_caso", "status_esperado", "movimentacoes_completas"),
    [
        ("esaj_1g_documentos", "ok", True),
        ("esaj_1g_longo", "partial", False),
    ],
    ids=("documentos-mistos", "historico-longo"),
)
def test_live_esaj_1g_le_pdf_publico_em_memoria_sem_expor_conteudo(
    id_caso, status_esperado, movimentacoes_completas
):
    caso = CASOS[id_caso]
    numero = caso["numero"]
    with esaj.criar_session(timeout=25) as sessao:
        extrato = esaj.montar_extrato(
            numero,
            session=sessao,
            salvar_html=False,
            baixar_pecas=False,
            limite_movimentacoes=100,
            timeout=25,
        )
        documentos = extrato["documentos"]
        publicos = documentos["publicos_candidatos_unicos"]
        assert extrato["dados_basicos"]["numero"] == numero
        assert extrato["origem"]["tribunal"] == "TJSP"
        assert extrato["origem"]["grau"] == "1g"
        assert extrato["status"] == status_esperado
        assert extrato["origem"]["movimentacoes_completas"] is movimentacoes_completas
        assert publicos
        assert documentos["restritos_por_senha_unicos"]

        lidos = esaj.ler_pecas_publicas(
            sessao,
            extrato["movimentacoes"],
            limite=1,
            max_chars=160,
            timeout=25,
            max_bytes=8 * 1024 * 1024,
        )

    assert len(lidos) == 1
    assert lidos[0]["status"] in {"texto_extraido", "pdf_parser_indisponivel"}
    assert lidos[0]["bytes"] > 0
    assert "application/pdf" in lidos[0]["mime_type"].lower()
    assert lidos[0].get("truncado") is True or lidos[0]["status"] == "pdf_parser_indisponivel"


@pytest.mark.parametrize("id_caso", ids_observados("esaj_tjsp_2g"))
def test_live_esaj_2g_preserva_consulta_e_identidade_dos_resultados(id_caso):
    caso = CASOS[id_caso]
    numero = caso["numero"]
    extrato = esaj_tjsp_2g.consultar_processo(numero, timeout=25, max_paginas=2)
    assert extrato["numero_consultado"] == numero
    assert extrato["resultados_listados"]
    numeros_resultados = {item["numero"] for item in extrato["resultados_listados"]}
    esperados = set(CASOS[id_caso].get("identidades_resultado_confirmadas", [numero]))
    assert esperados <= numeros_resultados
    for resultado in extrato["resultados_listados"]:
        assert (
            validar_numero_cnj(resultado["numero"], segmento="8", tribunal="26")
            == resultado["numero"]
        )
    metadados = caso.get("metadados_capa")
    if metadados:
        resultado_exato = next(
            (
                item
                for item in extrato["resultados"]
                if item.get("dados_basicos", {}).get("numero") == numero
            ),
            None,
        )
        assert resultado_exato is not None
        dados = resultado_exato["dados_basicos"]
        assert dados["classe"] == metadados["classe"]
        assert dados["orgao_julgador"] == metadados["orgao_julgador"]


def test_live_esaj_2g_obtem_pdf_publico_ligado_ao_cnj_proprio():
    caso = CASOS["esaj_2g_agravo"]
    numero = caso["numero"]
    extrato = esaj_tjsp_2g.consultar_processo(numero, timeout=25)
    assert extrato["numero_consultado"] == numero
    resultado = next(
        item
        for item in extrato["resultados"]
        if item.get("dados_basicos", {}).get("numero") == numero
    )
    assert resultado["movimentacoes_completas"] is True
    documentos = [
        documento
        for movimento in resultado["movimentacoes"]
        for documento in movimento.get("documentos", [])
        if documento.get("cd_documento")
    ]
    assert documentos, "A amostra deixou de expor o vínculo documental conhecido."
    pdf = esaj_tjsp_2g.obter_pdf_publico(
        numero, documentos[0]["cd_documento"], timeout=25, max_bytes=8 * 1024 * 1024
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) <= 8 * 1024 * 1024


def test_live_esaj_2g_conflito_obtem_pdf_vinculado_ao_resultado_proprio():
    caso = CASOS["esaj_2g_conflito"]
    numero = caso["numero"]
    extrato = esaj_tjsp_2g.consultar_processo(numero, timeout=25, max_paginas=2)
    assert extrato["numero_consultado"] == numero
    resultado = next(
        (
            item
            for item in extrato["resultados"]
            if item.get("dados_basicos", {}).get("numero") == numero
        ),
        None,
    )
    assert resultado is not None, "A busca não retornou o resultado do CNJ consultado."
    documentos = [
        documento
        for movimento in resultado["movimentacoes"]
        for documento in movimento.get("documentos", [])
        if documento.get("cd_documento")
    ]
    assert documentos, "A amostra deixou de expor vínculo documental no resultado próprio."
    pdf = esaj_tjsp_2g.obter_pdf_publico(
        numero, documentos[0]["cd_documento"], timeout=25, max_bytes=8 * 1024 * 1024
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) <= 8 * 1024 * 1024


@pytest.mark.parametrize("id_caso", ids_observados("pje_tjmg"))
def test_live_pje_tjmg_confere_identidade_e_paginacao(id_caso):
    caso = CASOS[id_caso]
    numero = caso["numero"]
    extrato = pje_tjmg.consultar_processo(numero, timeout=25)
    assert extrato["dados_basicos"]["numero"] == numero
    assert extrato["movimentacoes"]
    assert "movimentacoes_completas" in extrato["origem"]
    assert "documentos_completos" in extrato["origem"]
    metadados = caso.get("metadados_capa")
    if metadados:
        dados = extrato["dados_basicos"]
        assert dados["classe"] == metadados["classe"]
        assert dados["orgao_julgador"] == metadados["orgao_julgador"]
        assert dados["foro"] == dados["orgao_julgador"]
        assert dados["vara"] == metadados["vara"]
    esperado = caso.get("resultado_esperado")
    if esperado == "movimentacoes_completas_documentos_parciais":
        assert extrato["origem"]["movimentacoes_completas"] is True
        assert extrato["origem"]["documentos_completos"] is False
    elif esperado == "movimentacoes_documentos_completos":
        assert extrato["status"] == "ok"
        assert extrato["origem"]["movimentacoes_completas"] is True
        assert extrato["origem"]["documentos_completos"] is True
    elif esperado == "movimentacoes_documentos_multiplas_paginas":
        assert extrato["status"] == "ok"
        assert extrato["origem"]["movimentacoes_completas"] is True
        assert extrato["origem"]["documentos_completos"] is True
        assert extrato["origem"]["paginas_documentos_total"] > 1
        assert (
            extrato["origem"]["paginas_documentos_lidas"]
            == extrato["origem"]["paginas_documentos_total"]
        )
        documentos = extrato["documentos"]["publicos_candidatos_unicos"]
        ids = [documento["cd_documento"] for documento in documentos]
        assert len(ids) >= 2
        assert len(ids) == len(set(ids))


def test_live_pje_tjmg_obtem_pdf_publico_na_mesma_sessao():
    caso = CASOS["pje_tjmg_uberlandia_documentos_completos"]
    numero = caso["numero"]
    with pje_tjmg.criar_sessao() as session:
        extrato = pje_tjmg.consultar_processo(numero, session=session, timeout=25)
        assert extrato["dados_basicos"]["numero"] == numero
        documentos = extrato["documentos"]["publicos_candidatos_unicos"]
        assert documentos, "A amostra deixou de expor o vínculo documental conhecido."
        pdf = pje_tjmg.obter_pdf_publico(
            documentos[0]["href"], session=session, timeout=25, max_bytes=8 * 1024 * 1024
        )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) <= 8 * 1024 * 1024


@pytest.mark.parametrize("id_caso", ids_estado("pje_tjmg", "nao_encontrado"))
def test_live_pje_tjmg_preserva_estado_sem_detalhe_publico(id_caso):
    numero = CASOS[id_caso]["numero"]
    with pytest.raises(ProcessoNaoEncontrado):
        pje_tjmg.consultar_processo(numero, timeout=25)


@pytest.mark.parametrize("id_caso", ids_observados("tjrj_1g"))
def test_live_tjrj_1g_confere_identidade_e_completude_de_movimentos(id_caso):
    numero = CASOS[id_caso]["numero"]
    extrato = tjrj.consultar_processo(numero, timeout=25)
    assert extrato["dados_basicos"]["numero"] == numero
    assert extrato["origem"]["tribunal"] == "TJRJ"
    assert extrato["origem"]["grau"] == "1G"
    assert extrato["movimentacoes"]
    assert extrato["origem"]["movimentacoes_completas"] is True
    if CASOS[id_caso].get("resultado_esperado") == "movimentacoes_paginadas_completas":
        assert extrato["origem"]["movimentacoes_paginas"] >= 100
        assert extrato["origem"]["movimentacoes_registros"] >= 1000


@pytest.mark.parametrize("id_caso", ids_observados("datajud"))
def test_live_datajud_confere_cnj_sem_exigir_igualdade_de_acervo(id_caso):
    numero = CASOS[id_caso]["numero"]
    try:
        resultado = datajud.consultar_processo(numero, timeout=20, retry=1)
    except ConsultaIndisponivel as exc:
        causa = str(exc)
        if not any(motivo in causa for motivo in ("ReadTimeout", "ConnectTimeout", "HTTP 429")):
            raise
        pytest.skip("DataJud sem resposta por timeout/limite temporário; identidade inconclusiva.")
    assert resultado["status"] == "ok"
    assert resultado["numero_cnj"] == numero
    indice = datajud.indice_datajud(numero)
    assert indice and resultado["tribunal"] == indice.upper()
    assert resultado["graus"]


@pytest.mark.parametrize("id_caso", ids_estado("datajud", "nao_encontrado"))
def test_live_datajud_preserva_ausencia_no_indice_sem_generalizar(id_caso):
    numero = CASOS[id_caso]["numero"]
    try:
        resultado = datajud.consultar_processo(numero, timeout=20, retry=1)
    except ConsultaIndisponivel as exc:
        pytest.skip(f"DataJud indisponível; resultado da fonte permanece inconclusivo: {exc}")
    assert resultado["status"] == "nao_encontrado"
    assert resultado["numero_cnj"] == numero
    assert resultado["indice"] == "tjrj"


@pytest.mark.parametrize("id_caso", ids_observados("djen"))
def test_live_djen_confere_identidade_sem_fixar_quantidade(id_caso):
    caso = CASOS[id_caso]
    numero = caso["numero"]
    paginacao_caso_volumoso = caso.get("resultado_esperado") == "comunicacoes_mais_de_20_paginadas"
    resultado = djen.consultar_processo_detalhado(
        numero,
        timeout=20,
        max_pages=10 if paginacao_caso_volumoso else 2,
        page_size=5 if paginacao_caso_volumoso else djen.PAGE_SIZE,
        retry=1,
    )
    comunicacoes = resultado["comunicacoes"]
    if paginacao_caso_volumoso:
        if len(comunicacoes) <= 20:
            pytest.skip("O volume atual do caso deixou de exercitar mais de 20 comunicações.")
        assert resultado["status"] == "ok"
        assert resultado["completo"] is True
        assert resultado["paginas"] >= 2
        assert {item["numero_processo"] for item in comunicacoes} == {numero}
        ids = [item["id"] for item in comunicacoes if item["id"]]
        assert len(ids) == len(set(ids))
        return
    assert resultado["status"] == "ok"
    assert resultado["completo"] is True
    if caso.get("resultado_esperado") == "zero_ou_comunicacoes_futuras_com_identidade_confirmada":
        assert not comunicacoes or {item["numero_processo"] for item in comunicacoes} == {numero}
    else:
        assert comunicacoes
        assert {item["numero_processo"] for item in comunicacoes} == {numero}
    indice = datajud.indice_datajud(numero)
    if indice and comunicacoes:
        assert {item["siglaTribunal"] for item in comunicacoes} == {indice.upper()}
    elif comunicacoes:
        assert all(item["siglaTribunal"] for item in comunicacoes)


@pytest.mark.parametrize("id_caso", ["eproc_tjsp_1g_pdf_publico", "eproc_tjsp_2g_apelacao_publica"])
def test_live_eproc_confere_identidade_ou_estado_publico(id_caso):
    caso = CASOS[id_caso]
    consulta = (
        eproc_tjsp.consultar_processo
        if caso["fonte"] == "eproc_tjsp_1g"
        else eproc_tjsp.consultar_processo_2g
    )
    try:
        extrato = consulta(caso["numero"], timeout=30, headless=True)
    except AcessoRestrito:
        assert caso["estado"] == "bloqueado"
        return
    except ConsultaIndisponivel as exc:
        pytest.skip(f"Consulta eproc inconclusiva por indisponibilidade: {exc}")
    assert extrato["dados_basicos"]["numero"] == caso["numero"]
    assert extrato["movimentacoes"]
