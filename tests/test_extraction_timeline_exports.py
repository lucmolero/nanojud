import json
import runpy
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from nanojud import exports, extraction, normalization, timeline


def test_exemplo_resposta_cita_registro_e_preserva_estado_fonte():
    exemplo = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "examples" / "consulta_processual_com_tabela.py")
    )
    registro = {
        "id": "evt-001",
        "fonte": "tjrj_1g",
        "data": "2026-11-12",
        "titulo": "Evento [público](https://example.invalid)",
    }
    registros = exemplo["_registros_com_estado"]([registro], {"tjrj_1g": {"status": "ok"}})

    resposta = exemplo["_resposta_factual"](registros, 20)
    tabela = exports.to_table(registros)

    assert "[tjrj_1g:evt-001]" in resposta
    assert r"\[público\]\(https://example\.invalid\)" in resposta
    assert "sem interpretação jurídica" in resposta
    assert tabela["rows"][0]["status_fonte"] == "ok"


def test_normalization_extrai_cnj_unico():
    texto = "Processo 1076539-20.2019.8.26.0100 e 10765392020198260100."

    assert normalization.extrair_numeros_cnj(texto) == ["1076539-20.2019.8.26.0100"]


def test_normalization_datas_texto_oab_e_fonte():
    assert normalization.extrair_numeros_cnj("sem numero") == []
    assert normalization.normalizar_data("31/07/2026 10:00")["iso"] == "2026-07-31"
    assert normalization.normalizar_data("2026-07-31T10:00:00")["iso"] == "2026-07-31"
    assert normalization.normalizar_data("ilegivel")["iso"] == ""
    assert normalization.normalizar_texto_extraido(" a   b ") == "a b"
    assert normalization.normalizar_oab("OAB: 123/sp") == "123/SP"


def test_build_timeline_cronologica_sem_interpretacao():
    resultado = timeline.build_timeline(
        esaj_extrato={
            "dados_basicos": {"numero": "1076539-20.2019.8.26.0100"},
            "movimentacoes": [{"data": "21/08/2019", "titulo": "Conclusos"}],
        },
        datajud_extracao={
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "movimentos": [{"data": "2019-08-20", "codigo": "26", "nome": "Distribuicao"}],
        },
        djen_comunicacoes=[
            {
                "numeroProcesso": "1076539-20.2019.8.26.0100",
                "id": "d1",
                "dataDisponibilizacao": "2019-08-22",
                "tipoComunicacao": "Intimacao",
                "texto": "Texto",
            }
        ],
    )

    assert [item["fonte"] for item in resultado] == ["datajud", "esaj", "djen"]
    assert resultado[0]["tipo_registro"] == "movimentacao"
    assert "relevancia" not in resultado[0]
    assert "fase" not in resultado[0]


def test_extraction_avisa_quando_djen_entrega_caractere_substituido(monkeypatch):
    monkeypatch.setattr(
        extraction.djen,
        "consultar_processo_detalhado",
        lambda *args, **kwargs: {
            "status": "ok",
            "completo": True,
            "paginas": 1,
            "comunicacoes": [
                {
                    "id": "1",
                    "texto": "Procedimento Comum C\ufffdvel",
                    "dataDisponibilizacao": "2026-11-03",
                }
            ],
            "avisos": [],
        },
    )
    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100", sources=["djen"], prazo_total=5
    )

    assert envelope["status"] == "partial"
    assert envelope["source_status"]["djen"]["status"] == "partial"
    assert len(envelope["warnings"]) == 1
    assert "própria fonte" in envelope["warnings"][0]


def test_extract_process_aplica_timeout_configurado_ao_djen(monkeypatch):
    chamadas = {}

    def consultar(numero, data_inicio="", **kwargs):
        chamadas.update(kwargs)
        return {
            "status": "ok",
            "completo": True,
            "paginas": 1,
            "comunicacoes": [],
            "avisos": [],
        }

    monkeypatch.setattr(extraction.djen, "consultar_processo_detalhado", consultar)

    extraction.extract_process(
        "1076539-20.2019.8.26.0100", sources=["djen"], timeout=7, prazo_total=5
    )

    assert chamadas["timeout"] == 7


def test_extraction_preserva_djen_parcial_e_expoe_completude(monkeypatch):
    monkeypatch.setattr(
        extraction.djen,
        "consultar_processo_detalhado",
        lambda *args, **kwargs: {
            "status": "partial",
            "completo": False,
            "paginas": 1,
            "comunicacoes": [{"id": "1", "numero_processo": "1076539-20.2019.8.26.0100"}],
            "avisos": ["DJEN atingiu o limite de 1 páginas; o resultado pode estar incompleto."],
        },
    )

    envelope = extraction.extract_process("1076539-20.2019.8.26.0100", sources=["djen"])

    assert envelope["source_status"]["djen"]["status"] == "partial"
    assert envelope["source_status"]["djen"]["records_complete"] is False
    assert envelope["source_status"]["djen"]["pages"] == 1
    assert len(envelope["data"]["djen"]) == 1
    assert "limite de 1 páginas" in envelope["warnings"][0]


def test_extract_process_consulta_eproc_tjsp_1g(monkeypatch):
    numero = "1001194-30.2024.8.26.0114"
    extrato = {
        "status": "ok",
        "dados_basicos": {"numero": numero},
        "movimentacoes": [{"data": "2026-11-11", "titulo": "Teste"}],
        "origem": {
            "movimentacoes_completas": True,
            "grau": "1G",
            "url_final": "https://eproc-consulta.tjsp.jus.br/detalhes",
        },
    }
    monkeypatch.setattr(extraction.eproc_tjsp, "consultar_processo", lambda *a, **k: extrato)

    envelope = extraction.extract_process(numero, sources=["eproc_tjsp_1g"], prazo_total=5)

    assert envelope["status"] == "ok"
    assert envelope["data"]["eproc_tjsp_1g"] == extrato
    assert envelope["source_status"]["eproc_tjsp_1g"]["records"] == 1
    assert len(envelope["timeline"]) == 1
    assert envelope["timeline"][0]["fonte"] == "eproc_tjsp_1g"
    assert envelope["timeline"][0]["grau"] == "1g"
    assert envelope["timeline"][0]["url_origem"] == extrato["origem"]["url_final"]


def test_extract_process_eproc_1g_nao_atribui_incompletude_ao_limite_sem_evidencia(monkeypatch):
    numero = "1001194-30.2024.8.26.0114"
    monkeypatch.setattr(
        extraction.eproc_tjsp,
        "consultar_processo",
        lambda *args, **kwargs: {
            "status": "partial",
            "dados_basicos": {"numero": numero},
            "movimentacoes": [{"data": "2026-11-11", "titulo": "Teste"}],
            "origem": {"movimentacoes_completas": False, "grau": "1G"},
        },
    )

    envelope = extraction.extract_process(numero, sources=["eproc_tjsp_1g"], prazo_total=5)

    assert envelope["status"] == "partial"
    assert "limite" not in " ".join(envelope["warnings"]).lower()
    assert "não foi confirmada" in envelope["warnings"][0]


def test_extract_process_consulta_eproc_tjsp_2g_preserva_grau_e_fonte(monkeypatch):
    numero = "4167517-54.2026.8.26.0000"
    extrato = {
        "status": "partial",
        "dados_basicos": {"numero": numero},
        "movimentacoes": [{"data": "2026-11-11", "titulo": "Distribuído", "ordem": 1}],
        "origem": {"movimentacoes_completas": False, "grau": "2G"},
    }
    monkeypatch.setattr(
        extraction.eproc_tjsp, "consultar_processo_2g", lambda *args, **kwargs: extrato
    )
    envelope = extraction.extract_process(numero, sources=["eproc_tjsp_2g"], prazo_total=5)
    assert envelope["data"]["eproc_tjsp_2g"] == extrato
    assert envelope["source_status"]["eproc_tjsp_2g"]["status"] == "partial"
    assert envelope["timeline"][0]["fonte"] == "eproc_tjsp_2g"
    assert envelope["timeline"][0]["grau"] == "2g"


def test_extract_process_mni_configuravel_normaliza_e_adiciona_timeline(monkeypatch):
    from nanojud.mni import MNI3Config

    numero = "1001194-30.2024.8.26.0114"
    extrato = {
        "status": "partial",
        "origem": {
            "sistema": "MNI 3.0",
            "tribunal": "TJSP",
            "grau": "1G",
            "endpoint_host": "mni.tj.example",
            "movimentacoes_completas": False,
            "aviso_movimentacoes": "Completude não confirmada",
        },
        "dados_basicos": {"numero": numero},
        "movimentacoes": [
            {
                "titulo": "Conclusos para decisão",
                "teor": "Gabinete",
                "data": "2026-11-12",
                "data_original": "2026-11-12T10:00:00-03:00",
                "metadados": {"codigo_nacional": "123"},
                "documentos": [],
            }
        ],
    }
    configs = []

    class ClienteMNI:
        def __init__(self, config):
            configs.append(config)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def consultar_extrato(self, numero_consultado):
            assert numero_consultado == numero
            return extrato

    monkeypatch.setattr(extraction, "MNI3Client", ClienteMNI)
    config = MNI3Config(
        endpoint="https://mni.tj.example/Servico",
        token="token",
        timeout=10,
        tribunal="TJSP",
        grau="1G",
    )
    envelope = extraction.extract_process(
        numero, sources=["mni"], mni_config=config, timeout=5, prazo_total=5
    )

    assert envelope["status"] == "partial"
    assert envelope["source_status"]["mni"] == {"status": "partial", "records": 1}
    assert envelope["warnings"] == ["Completude não confirmada"]
    assert envelope["timeline"][0]["fonte"] == "mni"
    assert envelope["timeline"][0]["codigo_original"] == "123"
    assert envelope["timeline"][0]["grau"] == "1G"
    assert configs[0].timeout == 5


def test_extract_process_mni_sem_configuracao_retorna_erro_tipado(monkeypatch):
    for nome in (
        "ENDPOINT",
        "TOKEN",
        "USERNAME",
        "PASSWORD",
        "PESSOA_VINCULADA",
        "TRIBUNAL",
        "GRAU",
        "MOVIMENTACOES_COMPLETAS",
    ):
        monkeypatch.delenv(f"NANOJUD_MNI_{nome}", raising=False)

    envelope = extraction.extract_process(
        "1001194-30.2024.8.26.0114", sources=["mni"], prazo_total=5
    )

    assert envelope["status"] == "error"
    assert envelope["data"] == {}
    assert envelope["errors"][0]["type"] == "ConsultaIndisponivel"
    assert "NANOJUD_MNI_*" in envelope["errors"][0]["message"]


def test_extract_process_mni_carrega_configuracao_do_ambiente(monkeypatch):
    numero = "1001194-30.2024.8.26.0114"
    monkeypatch.setenv("NANOJUD_MNI_ENDPOINT", "https://mni.example/Servico")
    monkeypatch.setenv("NANOJUD_MNI_TOKEN", "token")
    configuracoes = []

    class ClienteMNI:
        def __init__(self, config):
            configuracoes.append(config)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def consultar_extrato(self, numero_consultado):
            assert numero_consultado == numero
            return {
                "status": "partial",
                "origem": {"movimentacoes_completas": False},
                "dados_basicos": {"numero": numero},
                "movimentacoes": [],
            }

    monkeypatch.setattr(extraction, "MNI3Client", ClienteMNI)
    envelope = extraction.extract_process(numero, sources=["mni"], prazo_total=5)

    assert envelope["source_status"]["mni"]["status"] == "partial"
    assert configuracoes[0].endpoint == "https://mni.example/Servico"
    assert configuracoes[0].token == "token"


def test_extract_process_marca_eproc_tjsp_nao_aplicavel_fora_de_sp():
    envelope = extraction.extract_process(
        "5060583-19.2021.8.13.0024", sources=["eproc_tjsp_1g"], prazo_total=5
    )
    assert envelope["source_status"]["eproc_tjsp_1g"]["status"] == "nao_aplicavel"


def test_extract_process_marca_esaj_parcial_quando_movimentacoes_incompletas(monkeypatch):
    monkeypatch.setattr(
        extraction.esaj,
        "montar_extrato",
        lambda *args, **kwargs: {
            "status": "ok",
            "dados_basicos": {"numero": "1076539-20.2019.8.26.0100"},
            "movimentacoes": [{"data": "2026-11-10", "titulo": "Movimento parcial"}],
            "origem": {
                "movimentacoes_completas": False,
                "aviso_movimentacoes": "Página 2 indisponível",
            },
        },
    )

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100", sources=["esaj"], prazo_total=5
    )

    assert envelope["status"] == "partial"
    assert envelope["source_status"]["esaj"]["status"] == "partial"
    assert "eSAJ: Página 2 indisponível" in envelope["warnings"]


def test_extract_process_pje_tjmg_preserva_status_avisos_e_timeline(monkeypatch):
    numero = "5060583-19.2021.8.13.0024"
    documento = {"titulo": "Decisão", "href": "https://pje.example/documento"}
    monkeypatch.setattr(
        extraction.pje_tjmg,
        "consultar_processo",
        lambda *args, **kwargs: {
            "status": "partial",
            "dados_basicos": {"numero": numero},
            "movimentacoes": [
                {"data": "10/02/2021", "titulo": "Distribuição", "documentos": [documento]}
            ],
            "origem": {"aviso_movimentacoes": "Página 2 indisponível"},
        },
    )

    envelope = extraction.extract_process(numero, sources=["pje_tjmg"], prazo_total=5)

    assert envelope["status"] == "partial"
    assert envelope["source_status"]["pje_tjmg"] == {"status": "partial", "records": 1}
    assert envelope["warnings"] == ["Página 2 indisponível"]
    assert envelope["data"]["pje_tjmg"]["movimentacoes"][0]["documentos"] == [documento]
    assert envelope["timeline"][0]["fonte"] == "pje_tjmg"
    assert envelope["timeline"][0]["data"] == "2021-02-10"


def test_extract_process_pje_tjmg_nao_aplicavel_nao_chama_provedor(monkeypatch):
    monkeypatch.setattr(
        extraction.pje_tjmg,
        "consultar_processo",
        lambda *args, **kwargs: pytest.fail("PJe/TJMG não deve receber CNJ de outro tribunal"),
    )

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100", sources=["pje_tjmg"], prazo_total=5
    )

    assert envelope["status"] == "error"
    assert envelope["data"] == {}
    assert envelope["errors"] == []
    assert envelope["source_status"]["pje_tjmg"] == {
        "status": "nao_aplicavel",
        "message": "PJe/TJMG cobre apenas processos estaduais de Minas Gerais.",
    }


def test_extract_process_preserva_dados_de_pje_quando_datajud_falha(monkeypatch):
    numero = "5060583-19.2021.8.13.0024"
    monkeypatch.setattr(
        extraction.pje_tjmg,
        "consultar_processo",
        lambda *args, **kwargs: {
            "status": "ok",
            "dados_basicos": {"numero": numero},
            "movimentacoes": [{"data": "2021-02-10", "titulo": "Distribuição"}],
        },
    )
    monkeypatch.setattr(
        extraction.datajud,
        "consultar_processo",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("DataJud indisponível")),
    )

    envelope = extraction.extract_process(numero, sources=["pje_tjmg", "datajud"], prazo_total=5)

    assert envelope["status"] == "partial"
    assert envelope["source_status"]["pje_tjmg"]["status"] == "ok"
    assert envelope["source_status"]["datajud"]["status"] == "error"
    assert [item["fonte"] for item in envelope["timeline"]] == ["pje_tjmg"]


def test_build_timeline_payload_e_datas_ausentes():
    resultado = timeline.build_timeline(
        esaj_extrato={
            "dados_basicos": {"numero": "1076539-20.2019.8.26.0100"},
            "movimentacoes": [{"titulo": "Sem data", "documentos": [{"id": "1"}]}],
        },
        datajud_extracao={
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "movimentos": [{"data_hora": "2026-07-31T12:00:00", "nome": "Mov"}],
        },
        djen_comunicacoes=[{"id": "1", "tipoDocumento": "Comunicacao"}],
        include_payload=True,
    )

    assert len(resultado) == 3
    assert any("payload_origem" in item for item in resultado)


def test_compactar_timeline_para_agentes():
    registros = [
        {"data": "2020-01-01", "fonte": "esaj", "texto": "a" * 20},
        {"data": "2026-07-31", "fonte": "djen", "texto": "b" * 20},
    ]

    resultado = timeline.compactar_timeline(
        registros,
        limit=1,
        recent_first=True,
        max_text_chars=5,
    )

    assert resultado == [
        {
            "data": "2026-07-31",
            "fonte": "djen",
            "texto": "bbbbb",
            "texto_truncado": True,
        }
    ]


def test_timeline_fonte_desconhecida_fica_por_ultimo():
    registros = timeline.build_timeline(
        esaj_extrato={
            "dados_basicos": {"numero": "1076539-20.2019.8.26.0100"},
            "movimentacoes": [{"data": "31/07/2026", "titulo": "eSAJ"}],
        },
        datajud_extracao={
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "movimentos": [{"data": "2026-07-31", "codigo": "1", "nome": "DataJud"}],
        },
    )
    registros.append(
        {
            "id": "x",
            "data": "2026-07-31",
            "fonte": "externa",
            "tipo_registro": "movimentacao",
        }
    )

    ordenado = sorted(
        registros,
        key=lambda item: (
            item.get("data") or "9999-99-99",
            timeline._source_order(item.get("fonte")),
            item.get("id", ""),
        ),
    )

    assert ordenado[-1]["fonte"] == "externa"


def test_extract_process_preserva_falha_isolada(monkeypatch):
    monkeypatch.setattr(
        extraction.esaj,
        "montar_extrato",
        lambda *a, **k: {
            "dados_basicos": {"numero": "1076539-20.2019.8.26.0100"},
            "movimentacoes": [{"data": "2019-08-21", "titulo": "Movimento eSAJ"}],
        },
    )

    def fake_datajud(*args, **kwargs):
        raise RuntimeError("sem chave")

    monkeypatch.setattr(extraction.datajud, "consultar_processo", fake_datajud)
    monkeypatch.setattr(extraction.djen, "consultar_processo", lambda *a, **k: [])

    envelope = extraction.extract_process("1076539-20.2019.8.26.0100")

    assert envelope["status"] == "partial"
    assert envelope["data"]["esaj"]["movimentacoes"][0]["titulo"] == "Movimento eSAJ"
    assert envelope["errors"][0]["source"] == "datajud"
    assert envelope["timeline"][0]["fonte"] == "esaj"
    assert envelope["source_status"]["datajud"]["status"] == "error"


def test_extract_process_error_e_raw(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("falhou")

    monkeypatch.setattr(extraction.esaj, "montar_extrato", fail)
    monkeypatch.setattr(extraction.datajud, "consultar_processo", fail)
    monkeypatch.setattr(extraction.djen, "consultar_processo_detalhado", fail)

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100",
        include_raw=True,
    )

    assert envelope["status"] == "error"
    assert envelope["raw"] == {}
    assert len(envelope["errors"]) == 3


def test_extract_process_redige_detalhes_de_erro_http(monkeypatch):
    import requests

    marcador = "https://portal.example/documento?token=segredo-sentinela"

    def fail(*args, **kwargs):
        raise requests.ConnectionError(f"conexão encerrada em {marcador}")

    monkeypatch.setattr(extraction.datajud, "consultar_processo", fail)
    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100",
        sources=["datajud"],
    )

    erro = envelope["errors"][0]
    estado = envelope["source_status"]["datajud"]
    assert erro["type"] == estado["type"] == "ConnectionError"
    assert erro["message"] == estado["message"] == "Falha HTTP (ConnectionError)."
    assert marcador not in str(envelope)


def test_extract_process_datajud_only_ok(monkeypatch):
    monkeypatch.setattr(
        extraction.datajud,
        "consultar_processo",
        lambda *a, **k: {
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "movimentos": [{"data": "2026-07-31", "codigo": "1", "nome": "Mov"}],
            "raw": {"ok": True},
        },
    )

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100",
        sources=("datajud",),
        include_raw=True,
    )

    assert envelope["status"] == "ok"
    assert envelope["raw"]["datajud"] == {"ok": True}
    assert envelope["source_status"]["datajud"]["records"] == 1


def test_extract_process_propaga_tempo_restante_para_datajud(monkeypatch):
    kwargs_recebidos = {}
    monkeypatch.setattr(
        extraction.datajud,
        "consultar_processo",
        lambda *args, **kwargs: (
            kwargs_recebidos.update(kwargs)
            or {
                "status": "ok",
                "numero_cnj": "1076539-20.2019.8.26.0100",
                "movimentos": [],
            }
        ),
    )

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100", sources=("datajud",), prazo_total=5
    )

    assert envelope["status"] == "ok"
    assert 0 < kwargs_recebidos["prazo_total"] <= 5


def test_extract_process_propaga_tempo_restante_para_pje_tjmg(monkeypatch):
    kwargs_recebidos = {}
    monkeypatch.setattr(
        extraction.pje_tjmg,
        "consultar_processo",
        lambda *args, **kwargs: (
            kwargs_recebidos.update(kwargs)
            or {
                "status": "ok",
                "origem": {
                    "movimentacoes_completas": True,
                    "documentos_completos": True,
                },
                "movimentacoes": [],
                "documentos": {"publicos_candidatos_unicos": []},
            }
        ),
    )

    envelope = extraction.extract_process(
        "5060583-19.2021.8.13.0024", sources=("pje_tjmg",), prazo_total=5
    )

    assert envelope["status"] == "ok"
    assert 0 < kwargs_recebidos["prazo_total"] <= 5


def test_extract_process_classifica_expiracao_datajud_como_erro_da_fonte(monkeypatch):
    kwargs_recebidos = {}

    def expirar(*args, **kwargs):
        kwargs_recebidos.update(kwargs)
        raise extraction.ConsultaIndisponivel("DataJud excedeu o prazo total da consulta.")

    monkeypatch.setattr(extraction.datajud, "consultar_processo", expirar)

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100", sources=("datajud",), prazo_total=5
    )

    assert envelope["status"] == "error"
    assert envelope["source_status"]["datajud"]["status"] == "error"
    assert envelope["source_status"]["datajud"]["type"] == "ConsultaIndisponivel"
    assert 0 < kwargs_recebidos["prazo_total"] <= 5


def test_extract_process_preserva_incompletude_do_datajud(monkeypatch):
    aviso = "DataJud retornou 10 de 11 registros; o limite pode ter truncado o resultado."
    monkeypatch.setattr(
        extraction.datajud,
        "consultar_processo",
        lambda *a, **k: {
            "status": "partial",
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "movimentos": [{"data": "2026-07-31", "codigo": "1", "nome": "Mov"}],
            "warnings": [aviso],
            "metadata": {"records_complete": False, "records_returned": 10, "total_hits": 11},
        },
    )

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100",
        sources=("datajud",),
    )

    assert envelope["status"] == "partial"
    assert envelope["warnings"] == [aviso]
    assert envelope["source_status"]["datajud"]["status"] == "partial"
    assert envelope["data"]["datajud"]["metadata"]["records_complete"] is False


def test_extract_process_rejeita_lista_de_fontes_vazia():
    with pytest.raises(ValueError, match="Selecione ao menos uma fonte"):
        extraction.extract_process("1076539-20.2019.8.26.0100", sources=[])


def test_extract_process_datajud_nao_encontrado_vira_partial(monkeypatch):
    monkeypatch.setattr(
        extraction.datajud,
        "consultar_processo",
        lambda *a, **k: {
            "status": "nao_encontrado",
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "movimentos": [],
        },
    )

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100",
        sources=("datajud",),
    )

    assert envelope["status"] == "partial"
    assert envelope["warnings"]
    assert envelope["source_status"]["datajud"]["status"] == "nao_encontrado"


def test_exportadores_jsonl_csv_sqlite():
    records = [{"fonte": "datajud", "titulo": "Distribuicao", "payload": {"codigo": 26}}]
    tmp_path = Path(".tmp") / f"test-exports-{uuid4()}"
    tmp_path.mkdir(parents=True, exist_ok=True)

    json_path = exports.write_json({"records": records}, tmp_path / "out.json")
    jsonl_path = exports.write_jsonl(records, tmp_path / "out.jsonl")
    csv_path = exports.write_csv(records, tmp_path / "out.csv")
    db_path = exports.write_sqlite(records, tmp_path / "out.sqlite")

    assert json.loads(json_path.read_text(encoding="utf-8"))["records"][0]["fonte"] == "datajud"
    assert jsonl_path.read_text(encoding="utf-8").strip()
    assert "Distribuicao" in csv_path.read_text(encoding="utf-8")
    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            assert conn.execute("select titulo from records").fetchone()[0] == "Distribuicao"


def test_exportadores_vazios():
    tmp_dir = Path(".tmp") / f"test-exports-empty-{uuid4()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    assert exports.to_jsonl([]) == ""
    csv_path = exports.write_csv([], tmp_dir / "empty.csv")
    db_path = exports.write_sqlite([], tmp_dir / "empty.sqlite")

    assert csv_path.read_text(encoding="utf-8").strip() == ""
    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            assert conn.execute("select count(*) from records").fetchone()[0] == 0


def test_to_table_preserva_proveniencia_e_gera_csv_deterministico():
    registros = [
        {
            "id": "evt-1",
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "fonte": "djen",
            "texto": "Intimação",
        },
        {"id": "evt-2", "numero_cnj": "1076539-20.2019.8.26.0100", "fonte": "esaj"},
    ]

    tabela = exports.to_table(registros, columns=["id", "numero_cnj", "fonte", "texto"])

    assert tabela["status"] == "ok"
    assert tabela["row_count"] == 2
    assert tabela["columns"] == ["id", "numero_cnj", "fonte", "texto"]
    assert tabela["rows"][0]["fonte"] == "djen"
    assert tabela["rows"][1]["texto"] is None
    assert tabela["csv"].splitlines()[0] == "id,numero_cnj,fonte,texto"
    assert "1076539-20.2019.8.26.0100" in tabela["csv"]


def test_to_table_neutraliza_formula_csv_sem_mudar_registro_estruturado():
    tabela = exports.to_table([{"texto": '=HYPERLINK("https://bad.test")'}])

    assert tabela["rows"][0]["texto"].startswith("=")
    assert "'=HYPERLINK" in tabela["csv"]


def test_to_table_rejeita_limites_excedidos_e_registros_nao_mapeaveis():
    with pytest.raises(ValueError, match="limite de 1 registros"):
        exports.to_table([{"id": 1}, {"id": 2}], max_rows=1)
    with pytest.raises(TypeError, match="mapeamento"):
        exports.to_table(["não é registro"])


def test_to_table_rejeita_limite_de_caracteres_sem_truncar():
    with pytest.raises(ValueError, match="limite de 5 caracteres"):
        exports.to_table([{"id": "longo"}], max_chars=5)
    assert exports.to_table([]) == {
        "status": "empty",
        "row_count": 0,
        "columns": [],
        "rows": [],
        "csv": "",
    }


def test_to_table_rejeita_colunas_que_nao_existam_nos_registros():
    with pytest.raises(ValueError, match="Colunas não encontradas.*ausente"):
        exports.to_table([{"numero_cnj": "1076539-20.2019.8.26.0100"}], columns=["ausente"])


@pytest.mark.parametrize(
    ("registros", "colunas", "mensagem"),
    [
        ([{1: "valor"}], None, "nomes das colunas"),
        ([{"numero_cnj": "1076539-20.2019.8.26.0100"}], [""], "nomes das colunas"),
        ([{"numero_cnj": "1076539-20.2019.8.26.0100"}], ["numero_cnj", "numero_cnj"], "duplicatas"),
        ([{"numero_cnj": "1076539-20.2019.8.26.0100"}], [], "ao menos uma coluna"),
    ],
)
def test_to_table_rejeita_chaves_e_selecao_de_colunas_invalidas(registros, colunas, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        exports.to_table(registros, columns=colunas)


@pytest.mark.parametrize(
    ("opcao", "valor"),
    [("max_rows", True), ("max_rows", 0), ("max_chars", False), ("max_chars", 1.5)],
)
def test_to_table_exige_limites_inteiros_positivos(opcao, valor):
    with pytest.raises(ValueError, match="inteiro positivo"):
        exports.to_table([], **{opcao: valor})


def test_to_csv_aplica_limite_antes_de_escrever_cabecalho():
    with pytest.raises(ValueError, match="limite de 3 caracteres"):
        exports.to_csv([], columns=["fonte"], max_chars=3)


def test_to_table_serializa_valores_estruturados_e_primitivos_sem_perder_fonte():
    tabela = exports.to_table(
        [{"fonte": "djen", "ordem": 7, "ativo": True, "data": None, "metadados": {"grau": "1G"}}]
    )

    assert tabela["rows"][0] == {
        "ativo": True,
        "data": None,
        "fonte": "djen",
        "metadados": {"grau": "1G"},
        "ordem": 7,
    }
    assert tabela["csv"].splitlines()[1] == 'True,,djen,"{""grau"": ""1G""}",7'


def test_timeline_gera_ids_unicos_para_movimentos_repetidos():
    from nanojud.timeline import build_timeline

    repetido = {"codigo": "581", "nome": "Documento", "data": "2020-06-01", "grau": "G1"}
    extracao = {"numero_cnj": "1076539-20.2019.8.26.0100", "movimentos": [repetido, dict(repetido)]}

    registros = build_timeline(datajud_extracao=extracao)

    assert len({r["id"] for r in registros}) == 2
    assert registros[0]["grau"] == "G1"


def test_extraction_processa_fonte_repetida_uma_vez(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        extraction.djen,
        "consultar_processo_detalhado",
        lambda numero, **kwargs: (
            chamadas.append(numero)
            or {
                "status": "ok",
                "completo": True,
                "paginas": 1,
                "comunicacoes": [{"id": "1", "texto": "caractere \ufffd"}],
                "avisos": [],
            }
        ),
    )
    numero = "1076539-20.2019.8.26.0100"
    envelope = extraction.extract_process(numero, sources=["DJEN", " djen "])

    assert chamadas == [numero]
    assert envelope["sources"] == ["djen"]
    assert len(envelope["warnings"]) == 1
