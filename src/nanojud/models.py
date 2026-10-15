"""Contratos tipados da API pública."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from typing_extensions import NotRequired

StatusConsulta = Literal["ok", "erro"]


class Origem(TypedDict, total=False):
    sistema: str
    tribunal: str
    grau: str
    consulta: str
    entrada: str
    url_final: str
    data_coleta: str
    html_bruto: str
    movimentacoes_completas: bool
    aviso_movimentacoes: str


class DadosBasicos(TypedDict, total=False):
    numero: str
    codigo_esaj: str
    classe: str
    assunto: str
    foro: str
    vara: str
    juiz: str
    distribuicao: str
    controle: str
    area: str
    valor_acao: str
    url: str
    campos_rotulados: dict[str, str]
    outros_assuntos: list[str]
    processo_dependencia: str
    situacao: str
    etiquetas: list[str]


class Parte(TypedDict, total=False):
    tipo: str
    nomes: list[str]
    advogados: list[str]


class Partes(TypedDict):
    principais: list[Parte]
    todas: list[Parte]
    polo_ativo: list[Parte]
    polo_passivo: list[Parte]
    polo_desconhecido: list[Parte]


class Documento(TypedDict, total=False):
    cd_documento: str
    sequencial_movimentacao: str
    titulo: str
    href: str
    status_acesso: Literal["publico_candidato", "restrito_por_senha", "outro"]
    data_documento: str
    pasta_digital: dict[str, Any]
    download_status: str
    arquivo: str


class Movimentacao(TypedDict, total=False):
    ordem: int
    data: str
    titulo: str
    teor: str
    texto: str
    metadados: dict[str, Any]
    documentos: list[Documento]


class Documentos(TypedDict, total=False):
    publicos_candidatos_unicos: list[Documento]
    restritos_por_senha_unicos: list[Documento]
    pecas_publicas_inspecionadas: list[dict[str, Any]]
    baixados: list[dict[str, Any]]


class Extrato(TypedDict, total=False):
    status: StatusConsulta
    mensagem: str
    origem: Origem
    dados_basicos: DadosBasicos
    partes: Partes
    movimentacoes: list[Movimentacao]
    documentos: Documentos
    peticoes_diversas: list[dict[str, str]]
    audiencias: list[dict[str, str]]
    relacionados: dict[str, list[dict[str, str]]]


class ResumoProcesso(TypedDict):
    numero: str
    classe: str
    assunto: str
    foro: str
    vara: str
    juiz: str
    ultima_movimentacao: str
    ultima_data: str
    url: str
    status: StatusConsulta
    mensagem: str
    erro: NotRequired[str]
    fonte: NotRequired[str]
