"""Orquestracao leve de extracao, sem interpretacao juridica."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, cast

import requests

from . import datajud, djen, esaj
from .divergencias import detectar_divergencias
from .schemas import (
    SCHEMA_VERSION,
    ExtractionEnvelope,
    ExtractionError,
    ExtractionStatus,
    SourceStatus,
)
from .sources import ALL_SOURCES, DATAJUD, DJEN, ESAJ, normalizar_fonte
from .timeline import build_timeline
from .utils import validar_numero_cnj
from .version import __version__

PRAZO_TOTAL = 60.0


def _eh_tjsp(numero_cnj: str) -> bool:
    return numero_cnj.split(".")[-3:-1] == ["8", "26"]


def extract_process(
    numero: str,
    *,
    sources: list[str] | tuple[str, ...] = ALL_SOURCES,
    include_raw: bool = False,
    datajud_api_key: str | None = None,
    djen_data_inicio: str = "",
    session: requests.Session | None = None,
    timeout: float = 30.0,
    limite_movimentacoes: int | None = esaj.LIMITE_MOVIMENTACOES,
    desde: str = "",
    prazo_total: float | None = PRAZO_TOTAL,
) -> ExtractionEnvelope:
    """Extrai dados de uma ou mais fontes e retorna envelope versionado.

    As fontes rodam em paralelo; ``prazo_total`` (segundos) limita a espera e uma fonte
    que estoura o prazo vira erro isolado, sem perder as demais. ``desde`` (YYYY-MM-DD)
    restringe movimentações e comunicações e reduz a paginação do eSAJ.
    """
    numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
    fontes = [normalizar_fonte(fonte) for fonte in sources]
    data: dict[str, Any] = {}
    raw: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[ExtractionError] = []
    source_status: dict[str, SourceStatus] = {}

    def _esaj() -> dict[str, Any]:
        extrato = esaj.montar_extrato(
            numero_cnj,
            salvar_html=include_raw,
            session=session,
            timeout=timeout,
            limite_movimentacoes=limite_movimentacoes,
            desde=desde,
        )
        origem = extrato.get("origem") or {}
        avisos = (
            [f"eSAJ: {origem['aviso_movimentacoes']}"] if origem.get("aviso_movimentacoes") else []
        )
        return {
            "data": extrato,
            "status": {"status": "ok", "records": len(extrato.get("movimentacoes") or [])},
            "warnings": avisos,
            "raw": origem.get("html_bruto") if include_raw else None,
        }

    def _datajud() -> dict[str, Any]:
        extracao = datajud.consultar_processo(
            numero_cnj,
            api_key=datajud_api_key,
            include_raw=include_raw,
            session=session,
            timeout=timeout,
        )
        if desde and extracao.get("movimentos"):
            extracao["movimentos"] = [
                m for m in extracao["movimentos"] if (m.get("data") or desde) >= desde
            ]
        status = str(extracao.get("status") or "ok")
        avisos = []
        if status == "nao_encontrado":
            avisos.append("DataJud/CNJ consultado, mas nao retornou processo para o CNJ informado.")
        return {
            "data": extracao,
            "status": {"status": status, "records": len(extracao.get("movimentos") or [])},
            "warnings": avisos,
            "raw": extracao.get("raw") if include_raw else None,
        }

    def _djen() -> dict[str, Any]:
        comunicacoes = djen.consultar_processo(
            numero_cnj, data_inicio=djen_data_inicio or desde, session=session
        )
        return {
            "data": comunicacoes,
            "status": {"status": "ok", "records": len(comunicacoes)},
            "warnings": [],
            "raw": None,
        }

    tarefas = {ESAJ: _esaj, DATAJUD: _datajud, DJEN: _djen}
    selecionadas = {}
    for fonte in fontes:
        if fonte == ESAJ and not _eh_tjsp(numero_cnj):
            source_status[ESAJ] = {"status": "nao_aplicavel", "message": "eSAJ cobre só o TJSP."}
        else:
            selecionadas[fonte] = tarefas[fonte]

    resultados: dict[str, Any] = {}
    if selecionadas:
        executor = ThreadPoolExecutor(max_workers=len(selecionadas))
        futuros = {executor.submit(tarefa): fonte for fonte, tarefa in selecionadas.items()}
        _, pendentes = wait(futuros, timeout=prazo_total)
        executor.shutdown(wait=False, cancel_futures=True)
        for futuro, fonte in futuros.items():
            if futuro in pendentes:
                resultados[fonte] = TimeoutError(f"Fonte excedeu o prazo total de {prazo_total}s.")
            else:
                try:
                    resultados[fonte] = futuro.result()
                except Exception as exc:  # noqa: BLE001 - envelope preserva falha isolada
                    resultados[fonte] = exc

    for fonte in fontes:  # ordem estável, independente de quem terminou primeiro
        resultado = resultados.get(fonte)
        if resultado is None:
            continue
        if isinstance(resultado, Exception):
            errors.append(
                {"source": fonte, "message": str(resultado), "type": type(resultado).__name__}
            )
            source_status[fonte] = {
                "status": "error",
                "message": str(resultado),
                "type": type(resultado).__name__,
            }
            continue
        data[fonte] = resultado["data"]
        source_status[fonte] = resultado["status"]
        warnings.extend(resultado["warnings"])
        if resultado["raw"]:
            raw[fonte] = resultado["raw"]

    timeline = build_timeline(
        esaj_extrato=data.get(ESAJ),
        datajud_extracao=data.get(DATAJUD),
        djen_comunicacoes=data.get(DJEN),
        include_payload=include_raw,
    )
    if desde:
        timeline = [r for r in timeline if (r.get("data") or desde) >= desde]
    if not data:
        status: ExtractionStatus = "error"
    elif errors or warnings:
        status = "partial"
    else:
        status = "ok"

    envelope: ExtractionEnvelope = {
        "schema_version": SCHEMA_VERSION,
        "package_version": __version__,
        "status": status,
        "numero_cnj": numero_cnj,
        "sources": fontes,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "timeline": timeline,
        "warnings": warnings,
        "errors": errors,
        "source_status": source_status,
        "divergencias": cast(list[dict[str, Any]], detectar_divergencias(data)),
    }
    if include_raw:
        envelope["raw"] = raw
    return envelope
