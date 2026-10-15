"""Linha do tempo cronologica sem interpretacao juridica."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from .normalization import normalizar_data
from .schemas import TimelineRecord
from .sources import DATAJUD, DJEN, ESAJ, SourceName


def build_timeline(
    *,
    esaj_extrato: dict[str, Any] | None = None,
    datajud_extracao: dict[str, Any] | None = None,
    djen_comunicacoes: list[dict[str, Any]] | None = None,
    include_payload: bool = False,
) -> list[TimelineRecord]:
    """Combina registros extraidos em ordem cronologica, preservando a fonte."""
    registros: list[TimelineRecord] = []
    registros.extend(_timeline_esaj(esaj_extrato or {}, include_payload=include_payload))
    registros.extend(_timeline_datajud(datajud_extracao or {}, include_payload=include_payload))
    registros.extend(_timeline_djen(djen_comunicacoes or [], include_payload=include_payload))
    _garantir_ids_unicos(registros)
    return sorted(
        registros,
        key=lambda item: (
            item.get("data") or "9999-99-99",
            _source_order(item.get("fonte")),
            item.get("id", ""),
        ),
    )


def _garantir_ids_unicos(registros: list[TimelineRecord]) -> None:
    """Movimentos repetidos (mesma data, código e título) ganham sufixo sequencial no id."""
    vistos: dict[str, int] = {}
    for registro in registros:
        base = registro["id"]
        n = vistos.get(base, 0)
        vistos[base] = n + 1
        if n:
            registro["id"] = hashlib.sha1(f"{base}|{n}".encode()).hexdigest()


def compactar_timeline(
    registros: list[TimelineRecord],
    *,
    limit: int = 0,
    recent_first: bool = False,
    include_text: bool = True,
    max_text_chars: int = 0,
) -> list[TimelineRecord]:
    """Reduz timeline para consumo por agentes sem alterar a timeline original."""
    saida = [cast(TimelineRecord, dict(item)) for item in registros]
    if recent_first:
        saida = list(reversed(saida))
    if limit > 0:
        saida = saida[:limit]
    for item in saida:
        if not include_text:
            item.pop("texto", None)
            continue
        texto = item.get("texto", "")
        if max_text_chars > 0 and len(texto) > max_text_chars:
            item["texto"] = texto[:max_text_chars]
            item["texto_truncado"] = True
    return saida


def _timeline_esaj(extrato: dict[str, Any], *, include_payload: bool) -> list[TimelineRecord]:
    numero = str((extrato.get("dados_basicos") or {}).get("numero") or "")
    saida: list[TimelineRecord] = []
    for movimento in extrato.get("movimentacoes") or []:
        data = normalizar_data(movimento.get("data"))
        record: TimelineRecord = {
            "id": _id_registro(ESAJ, numero, data["iso"], "", movimento.get("titulo") or ""),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": data["original"],
            "fonte": ESAJ,
            "tipo_registro": "movimentacao",
            "codigo_original": "",
            "titulo": str(movimento.get("titulo") or ""),
            "texto": str(movimento.get("teor") or movimento.get("texto") or ""),
            "documentos": list(movimento.get("documentos") or []),
        }
        if include_payload:
            record["payload_origem"] = movimento
        saida.append(record)
    return saida


def _timeline_datajud(extracao: dict[str, Any], *, include_payload: bool) -> list[TimelineRecord]:
    numero = str(extracao.get("numero_cnj") or "")
    saida: list[TimelineRecord] = []
    for movimento in extracao.get("movimentos") or []:
        data = normalizar_data(movimento.get("data") or movimento.get("data_hora"))
        codigo = str(movimento.get("codigo") or "")
        titulo = str(movimento.get("nome") or "")
        record: TimelineRecord = {
            "id": _id_registro(DATAJUD, numero, data["iso"], codigo, titulo),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": data["original"],
            "fonte": DATAJUD,
            "tipo_registro": "movimentacao",
            "codigo_original": codigo,
            "titulo": titulo,
            "texto": str(movimento.get("complementos") or ""),
            "documentos": [],
        }
        if movimento.get("grau"):
            record["grau"] = str(movimento["grau"])
        if include_payload:
            payload = movimento.get("payload_origem")
            record["payload_origem"] = payload if isinstance(payload, dict) else movimento
        saida.append(record)
    return saida


def _timeline_djen(
    comunicacoes: list[dict[str, Any]],
    *,
    include_payload: bool,
) -> list[TimelineRecord]:
    saida: list[TimelineRecord] = []
    for comunicacao in comunicacoes:
        data = normalizar_data(
            comunicacao.get("dataDisponibilizacao") or comunicacao.get("data_disponibilizacao")
        )
        codigo = str(comunicacao.get("id") or "")
        numero = str(comunicacao.get("numeroProcesso") or comunicacao.get("numero_processo") or "")
        titulo = str(comunicacao.get("tipoComunicacao") or comunicacao.get("tipoDocumento") or "")
        record: TimelineRecord = {
            "id": _id_registro(DJEN, numero, data["iso"], codigo, titulo),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": data["original"],
            "fonte": DJEN,
            "tipo_registro": "comunicacao",
            "codigo_original": codigo,
            "titulo": titulo,
            "texto": str(comunicacao.get("texto") or ""),
            "documentos": [],
        }
        if include_payload:
            record["payload_origem"] = comunicacao
        saida.append(record)
    return saida


def _id_registro(fonte: SourceName, numero: str, data: str, codigo: str, titulo: str) -> str:
    base = "|".join([fonte, numero, data, codigo, titulo])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _source_order(fonte: object) -> int:
    if fonte == DATAJUD:
        return 0
    if fonte == ESAJ:
        return 1
    if fonte == DJEN:
        return 2
    return 99
