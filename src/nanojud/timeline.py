"""Linha do tempo cronologica sem interpretacao juridica."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from .normalization import normalizar_data
from .schemas import TimelineRecord
from .sources import (
    DATAJUD,
    DJEN,
    EPROC_TJSP_1G,
    EPROC_TJSP_2G,
    ESAJ,
    ESAJ_TJSP_2G,
    MNI,
    PJE_TJMG,
    TJRJ_1G,
    SourceName,
)


def build_timeline(
    *,
    esaj_extrato: dict[str, Any] | None = None,
    datajud_extracao: dict[str, Any] | None = None,
    djen_comunicacoes: list[dict[str, Any]] | None = None,
    pje_tjmg_extracao: dict[str, Any] | None = None,
    eproc_tjsp_1g_extracao: dict[str, Any] | None = None,
    eproc_tjsp_2g_extracao: dict[str, Any] | None = None,
    mni_extracao: dict[str, Any] | None = None,
    tjrj_extracao: dict[str, Any] | None = None,
    cposg_extracao: dict[str, Any] | None = None,
    include_payload: bool = False,
) -> list[TimelineRecord]:
    """Combina registros extraidos em ordem cronologica, preservando a fonte."""
    registros: list[TimelineRecord] = []
    registros.extend(_timeline_esaj(esaj_extrato or {}, include_payload=include_payload))
    registros.extend(_timeline_datajud(datajud_extracao or {}, include_payload=include_payload))
    registros.extend(_timeline_djen(djen_comunicacoes or [], include_payload=include_payload))
    registros.extend(_timeline_pje_tjmg(pje_tjmg_extracao or {}, include_payload=include_payload))
    registros.extend(
        _timeline_eproc_tjsp_1g(eproc_tjsp_1g_extracao or {}, include_payload=include_payload)
    )
    registros.extend(
        _timeline_eproc_tjsp_2g(eproc_tjsp_2g_extracao or {}, include_payload=include_payload)
    )
    registros.extend(_timeline_mni(mni_extracao or {}, include_payload=include_payload))
    registros.extend(_timeline_tjrj(tjrj_extracao or {}, include_payload=include_payload))
    for recurso in (cposg_extracao or {}).get("resultados", []):
        registros.extend(
            _timeline_esaj(recurso, include_payload=include_payload, fonte=ESAJ_TJSP_2G)
        )
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


def limite_movimentacoes_para(limit: int, recent_first: bool, padrao: int | None) -> int | None:
    """Quantas movimentações do eSAJ buscar para entregar ``limit`` eventos mais recentes.

    O eSAJ lista do mais novo para o mais antigo; para os N eventos mais recentes da timeline
    unificada bastam as N mais recentes do eSAJ.
    """
    return max(limit, 5) if recent_first and limit > 0 else padrao


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


def _timeline_esaj(
    extrato: dict[str, Any], *, include_payload: bool, fonte: SourceName = ESAJ
) -> list[TimelineRecord]:
    numero = str((extrato.get("dados_basicos") or {}).get("numero") or "")
    saida: list[TimelineRecord] = []
    for movimento in extrato.get("movimentacoes") or []:
        data = normalizar_data(movimento.get("data"))
        record: TimelineRecord = {
            "id": _id_registro(fonte, numero, data["iso"], "", movimento.get("titulo") or ""),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": data["original"],
            "fonte": fonte,
            "tipo_registro": "movimentacao",
            "codigo_original": "",
            "titulo": str(movimento.get("titulo") or ""),
            "texto": str(movimento.get("teor") or movimento.get("texto") or ""),
            "documentos": list(movimento.get("documentos") or []),
        }
        if fonte == ESAJ_TJSP_2G:
            record["grau"] = "2g"
            record["url_origem"] = str(extrato.get("url") or "")
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


def _timeline_pje_tjmg(extrato: dict[str, Any], *, include_payload: bool) -> list[TimelineRecord]:
    numero = str((extrato.get("dados_basicos") or {}).get("numero") or "")
    saida: list[TimelineRecord] = []
    for movimento in extrato.get("movimentacoes") or []:
        data = normalizar_data(movimento.get("data") or movimento.get("data_original"))
        titulo = str(movimento.get("titulo") or "")
        record: TimelineRecord = {
            "id": _id_registro(PJE_TJMG, numero, data["iso"], "", titulo),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": data["original"],
            "fonte": PJE_TJMG,
            "tipo_registro": "movimentacao",
            "codigo_original": "",
            "titulo": titulo,
            "texto": str(movimento.get("teor") or movimento.get("texto") or ""),
            "documentos": list(movimento.get("documentos") or []),
        }
        if include_payload:
            record["payload_origem"] = movimento
        saida.append(record)
    return saida


def _timeline_eproc_tjsp_1g(
    extrato: dict[str, Any], *, include_payload: bool
) -> list[TimelineRecord]:
    numero = str((extrato.get("dados_basicos") or {}).get("numero") or "")
    origem = extrato.get("origem") or {}
    saida: list[TimelineRecord] = []
    for movimento in extrato.get("movimentacoes") or []:
        data = normalizar_data(movimento.get("data") or movimento.get("data_original"))
        titulo = str(movimento.get("titulo") or "")
        record: TimelineRecord = {
            "id": _id_registro(
                EPROC_TJSP_1G, numero, data["iso"], str(movimento.get("ordem") or ""), titulo
            ),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": data["original"],
            "fonte": EPROC_TJSP_1G,
            "tipo_registro": "movimentacao",
            "codigo_original": str(movimento.get("ordem") or ""),
            "titulo": titulo,
            "texto": str(movimento.get("teor") or ""),
            "documentos": list(movimento.get("documentos") or []),
            "grau": "1g",
            "url_origem": str(origem.get("url_final") or ""),
        }
        if include_payload:
            record["payload_origem"] = movimento
        saida.append(record)
    return saida


def _timeline_eproc_tjsp_2g(
    extrato: dict[str, Any], *, include_payload: bool
) -> list[TimelineRecord]:
    registros = _timeline_eproc_tjsp_1g(extrato, include_payload=include_payload)
    for registro in registros:
        registro["id"] = _id_registro(
            EPROC_TJSP_2G,
            str(registro.get("numero_cnj") or ""),
            str(registro.get("data") or ""),
            str(registro.get("codigo_original") or ""),
            str(registro.get("titulo") or ""),
        )
        registro["fonte"] = EPROC_TJSP_2G
        registro["grau"] = "2g"
    return registros


def _id_registro(fonte: SourceName, numero: str, data: str, codigo: str, titulo: str) -> str:
    base = "|".join([fonte, numero, data, codigo, titulo])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _source_order(fonte: object) -> int:
    if fonte == DATAJUD:
        return 0
    if fonte in (ESAJ, ESAJ_TJSP_2G):
        return 1
    if fonte == DJEN:
        return 3
    if fonte == PJE_TJMG:
        return 2
    if fonte == MNI:
        return 4
    if fonte == TJRJ_1G:
        return 2
    return 99


def _timeline_mni(extrato: dict[str, Any], *, include_payload: bool) -> list[TimelineRecord]:
    numero = str((extrato.get("dados_basicos") or {}).get("numero") or "")
    origem = extrato.get("origem") or {}
    saida: list[TimelineRecord] = []
    for movimento in extrato.get("movimentacoes") or []:
        metadados = movimento.get("metadados") or {}
        data = normalizar_data(movimento.get("data"))
        codigo = str(metadados.get("codigo_nacional") or metadados.get("codigo_local") or "")
        titulo = str(movimento.get("titulo") or "")
        record: TimelineRecord = {
            "id": _id_registro(MNI, numero, data["iso"], codigo, titulo),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": str(movimento.get("data_original") or data["original"]),
            "fonte": MNI,
            "tipo_registro": "movimentacao",
            "codigo_original": codigo,
            "titulo": titulo,
            "texto": str(movimento.get("teor") or ""),
            "documentos": list(movimento.get("documentos") or []),
        }
        if origem.get("grau"):
            record["grau"] = str(origem["grau"])
        if include_payload:
            record["payload_origem"] = movimento
        saida.append(record)
    return saida


def _timeline_tjrj(extrato: dict[str, Any], *, include_payload: bool) -> list[TimelineRecord]:
    numero = str((extrato.get("dados_basicos") or {}).get("numero") or "")
    origem = extrato.get("origem") or {}
    saida: list[TimelineRecord] = []
    for movimento in extrato.get("movimentacoes") or []:
        data = normalizar_data(movimento.get("data") or movimento.get("data_original"))
        titulo = str(movimento.get("titulo") or "")
        codigo = str(movimento.get("ordem") or "")
        record: TimelineRecord = {
            "id": _id_registro(TJRJ_1G, numero, data["iso"], codigo, titulo),
            "numero_cnj": numero,
            "data": data["iso"],
            "data_original": data["original"],
            "fonte": TJRJ_1G,
            "tipo_registro": "movimentacao",
            "codigo_original": codigo,
            "titulo": titulo,
            "texto": str(movimento.get("teor") or ""),
            "documentos": list(movimento.get("documentos") or []),
            "grau": "1g",
            "url_origem": str(origem.get("url_final") or ""),
        }
        if include_payload:
            record["payload_origem"] = movimento
        saida.append(record)
    return saida
