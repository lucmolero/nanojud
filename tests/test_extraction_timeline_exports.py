import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from nanojud import exports, extraction, normalization, timeline


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
    monkeypatch.setattr(extraction.djen, "consultar_processo", fail)

    envelope = extraction.extract_process(
        "1076539-20.2019.8.26.0100",
        include_raw=True,
    )

    assert envelope["status"] == "error"
    assert envelope["raw"] == {}
    assert len(envelope["errors"]) == 3


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
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select titulo from records").fetchone()[0] == "Distribuicao"


def test_exportadores_vazios():
    tmp_dir = Path(".tmp") / f"test-exports-empty-{uuid4()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    assert exports.to_jsonl([]) == ""
    csv_path = exports.write_csv([], tmp_dir / "empty.csv")
    db_path = exports.write_sqlite([], tmp_dir / "empty.sqlite")

    assert csv_path.read_text(encoding="utf-8").strip() == ""
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from records").fetchone()[0] == 0


def test_timeline_gera_ids_unicos_para_movimentos_repetidos():
    from nanojud.timeline import build_timeline

    repetido = {"codigo": "581", "nome": "Documento", "data": "2020-06-01", "grau": "G1"}
    extracao = {"numero_cnj": "1076539-20.2019.8.26.0100", "movimentos": [repetido, dict(repetido)]}

    registros = build_timeline(datajud_extracao=extracao)

    assert len({r["id"] for r in registros}) == 2
    assert registros[0]["grau"] == "G1"
