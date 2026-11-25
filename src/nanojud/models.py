"""Contratos tipados da API pública."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

StatusConsulta = Literal["ok", "partial", "erro"]
StatusAutorizacao = Literal[
    "identificacao_do_advogado_necessaria",
    "redirecionamento_externo_nao_seguido",
    "erro_http_do_portal",
    "senha_invalida",
    "erro_de_comunicacao",
    "liberado_pelo_portal",
    "nao_liberado_pelo_portal",
    "formulario_senha_indisponivel",
    "identificador_de_recurso_ausente",
]


class Origem(TypedDict, total=False):
    sistema: str
    tribunal: str
    grau: str
    consulta: str
    entrada: str
    url_final: str
    endpoint_host: str
    data_coleta: str
    html_bruto: str
    movimentacoes_completas: bool
    movimentacoes_paginas: int
    movimentacoes_registros: int
    partes_completas: bool
    documentos_completos: bool
    aviso_movimentacoes: str
    aviso_documentos: str


class DadosBasicos(TypedDict, total=False):
    numero: str
    numero_tjmg: str
    codigo_esaj: str
    classe: str
    classe_codigo: str
    assunto: str
    assunto_codigo: str
    orgao_julgador: str
    relator: str
    secao: str
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
    metadados: dict[str, Any]


class Partes(TypedDict):
    principais: list[Parte]
    todas: list[Parte]
    polo_ativo: list[Parte]
    polo_passivo: list[Parte]
    polo_desconhecido: list[Parte]


class Documento(TypedDict, total=False):
    cd_documento: str
    id_documento: str
    id_recurso: str
    sequencial_movimentacao: str
    titulo: str
    href: str
    status_acesso: Literal["publico_candidato", "restrito_por_senha", "outro"]
    status_autorizacao: StatusAutorizacao
    data_documento: str
    codigo_tipo_documento: str
    mimetype: str
    nivel_sigilo: str
    metadados: dict[str, Any]
    pasta_digital: dict[str, Any]
    download_status: str
    download_message: str
    arquivo: str


class Movimentacao(TypedDict, total=False):
    ordem: int
    data: str
    data_original: str
    titulo: str
    teor: str
    texto: str
    metadados: dict[str, Any]
    documentos: list[Documento]


class Documentos(TypedDict, total=False):
    publicos_candidatos_unicos: list[Documento]
    todos_mni: list[Documento]
    restritos_por_senha_unicos: list[Documento]
    pecas_publicas_inspecionadas: list[dict[str, Any]]
    baixados: list[dict[str, Any]]
    tentativas_autorizacao: list[dict[str, Any]]


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
    fonte: str
    grau: str
    data_coleta: str
    coleta_completa: bool | None
    erro: NotRequired[str]
    situacao: NotRequired[str]
