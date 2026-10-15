"""Contratos de extracao versionados."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from typing_extensions import NotRequired

from .sources import SourceName

SCHEMA_VERSION = "1.0"

ExtractionStatus = Literal["ok", "partial", "error"]


class SourceMetadata(TypedDict, total=False):
    source: SourceName
    source_url: str
    extracted_at: str
    raw_available: bool


class ExtractionError(TypedDict):
    source: SourceName
    message: str
    type: str


class SourceStatus(TypedDict, total=False):
    status: str
    records: int
    message: str
    type: str


class TimelineRecord(TypedDict, total=False):
    id: str
    numero_cnj: str
    data: str
    data_original: str
    fonte: SourceName
    tipo_registro: Literal["movimentacao", "comunicacao"]
    codigo_original: str
    titulo: str
    texto: str
    texto_truncado: bool
    grau: str
    documentos: list[dict[str, Any]]
    payload_origem: dict[str, Any]


class DataJudExtraction(TypedDict, total=False):
    status: Literal["ok", "nao_encontrado"]
    numero_cnj: str
    tribunal: str
    indice: str
    grau: str
    classe: str
    orgao_julgador: str
    graus: list[dict[str, Any]]
    assuntos: list[dict[str, Any]]
    movimentos: list[dict[str, Any]]
    partes: list[dict[str, Any]]
    raw: dict[str, Any]
    metadata: SourceMetadata


class ExtractionEnvelope(TypedDict):
    schema_version: str
    package_version: str
    status: ExtractionStatus
    numero_cnj: str
    sources: list[SourceName]
    extracted_at: str
    data: dict[str, Any]
    timeline: list[TimelineRecord]
    warnings: list[str]
    errors: list[ExtractionError]
    source_status: dict[str, SourceStatus]
    raw: NotRequired[dict[str, Any]]
