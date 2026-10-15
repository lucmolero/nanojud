"""Orquestracao leve de extracao, sem interpretacao juridica."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from . import datajud, djen, esaj
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


def extract_process(
    numero: str,
    *,
    sources: list[str] | tuple[str, ...] = ALL_SOURCES,
    include_raw: bool = False,
    datajud_api_key: str | None = None,
    djen_data_inicio: str = "",
    session: requests.Session | None = None,
    timeout: float = 30.0,
) -> ExtractionEnvelope:
    """Extrai dados de uma ou mais fontes e retorna envelope versionado."""
    numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
    fontes = [normalizar_fonte(fonte) for fonte in sources]
    data: dict[str, Any] = {}
    raw: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[ExtractionError] = []
    source_status: dict[str, SourceStatus] = {}

    if ESAJ in fontes:
        try:
            esaj_extrato = esaj.montar_extrato(
                numero_cnj,
                salvar_html=include_raw,
                session=session,
                timeout=timeout,
            )
            data[ESAJ] = esaj_extrato
            aviso_movimentacoes = (esaj_extrato.get("origem") or {}).get("aviso_movimentacoes")
            if aviso_movimentacoes:
                warnings.append(f"eSAJ: {aviso_movimentacoes}")
            source_status[ESAJ] = {
                "status": "ok",
                "records": len(esaj_extrato.get("movimentacoes") or []),
            }
            if include_raw and (esaj_extrato.get("origem") or {}).get("html_bruto"):
                raw[ESAJ] = (esaj_extrato.get("origem") or {}).get("html_bruto")
        except Exception as exc:  # noqa: BLE001 - envelope preserva falha isolada por fonte
            errors.append({"source": ESAJ, "message": str(exc), "type": type(exc).__name__})
            source_status[ESAJ] = {
                "status": "error",
                "message": str(exc),
                "type": type(exc).__name__,
            }

    if DATAJUD in fontes:
        try:
            datajud_extracao = datajud.consultar_processo(
                numero_cnj,
                api_key=datajud_api_key,
                include_raw=include_raw,
                session=session,
                timeout=timeout,
            )
            data[DATAJUD] = datajud_extracao
            datajud_status = str(datajud_extracao.get("status") or "ok")
            movimentos_datajud = datajud_extracao.get("movimentos") or []
            source_status[DATAJUD] = {
                "status": datajud_status,
                "records": len(movimentos_datajud),
            }
            if datajud_status == "nao_encontrado":
                warnings.append(
                    "DataJud/CNJ consultado, mas nao retornou processo para o CNJ informado."
                )
            if include_raw and datajud_extracao.get("raw"):
                raw[DATAJUD] = datajud_extracao["raw"]
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": DATAJUD, "message": str(exc), "type": type(exc).__name__})
            source_status[DATAJUD] = {
                "status": "error",
                "message": str(exc),
                "type": type(exc).__name__,
            }

    if DJEN in fontes:
        try:
            djen_comunicacoes = djen.consultar_processo(
                numero_cnj,
                data_inicio=djen_data_inicio,
                session=session,
            )
            data[DJEN] = djen_comunicacoes
            source_status[DJEN] = {"status": "ok", "records": len(djen_comunicacoes)}
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": DJEN, "message": str(exc), "type": type(exc).__name__})
            source_status[DJEN] = {
                "status": "error",
                "message": str(exc),
                "type": type(exc).__name__,
            }

    timeline = build_timeline(
        esaj_extrato=data.get(ESAJ),
        datajud_extracao=data.get(DATAJUD),
        djen_comunicacoes=data.get(DJEN),
        include_payload=include_raw,
    )
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
    }
    if include_raw:
        envelope["raw"] = raw
    return envelope
