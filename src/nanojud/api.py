"""API pública de alto nível para advogados, escritórios e sistemas."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from . import datajud, djen, esaj, extraction
from .client import NanoJudClient
from .config import NanoJudConfig
from .models import Extrato, Movimentacao, ResumoProcesso
from .normalization import normalizar_data
from .utils import eh_tjsp, validar_numero_cnj


def search_processo(numero: str) -> ResumoProcesso:
    """Consulta um processo e retorna um resumo objetivo.

    No TJSP usa o eSAJ; nos demais tribunais, o DataJud (sem partes, foro nem juiz).
    """
    numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
    if not eh_tjsp(numero_cnj):
        return datajud.resumo_do_datajud(consultar_datajud(numero_cnj))
    extrato = get_extrato(numero_cnj, limite_movimentacoes=esaj.LIMITE_RESUMO)
    return _resumo_do_extrato(extrato)


def get_extrato(
    numero: str,
    baixar_pecas: bool = False,
    limite_pecas: int = 3,
    *,
    inspecionar_pecas: bool = False,
    limite_inspecao_pecas: int = 10,
    salvar_html: bool = False,
    limite_movimentacoes: int | None = esaj.LIMITE_MOVIMENTACOES,
    desde: str = "",
) -> Extrato:
    """Monta extrato estruturado do processo eSAJ/TJSP."""
    return esaj.montar_extrato(
        numero,
        baixar_pecas=baixar_pecas,
        limite_pecas=limite_pecas,
        inspecionar_pecas=inspecionar_pecas,
        limite_inspecao_pecas=limite_inspecao_pecas,
        salvar_html=salvar_html,
        limite_movimentacoes=limite_movimentacoes,
        desde=desde,
    )


def get_partes(numero: str) -> dict[str, Any]:
    """Retorna as partes classificadas do processo eSAJ/TJSP."""
    extrato = get_extrato(numero)
    return cast(
        dict[str, Any],
        extrato.get(
            "partes",
            {
                "principais": [],
                "todas": [],
                "polo_ativo": [],
                "polo_passivo": [],
                "polo_desconhecido": [],
            },
        ),
    )


def baixar_pecas(
    extrato: dict[str, Any],
    destino: Path,
    sobrescrever: bool = False,
    limite: int = 0,
) -> list[dict[str, Any]]:
    """Baixa peças públicas candidatas já presentes em um extrato.

    A função usa os `href` dos documentos públicos candidatos e respeita o limite
    informado. Documentos restritos por senha não são acessados.
    """
    movimentos = []
    documentos = extrato.get("documentos", {}).get("publicos_candidatos_unicos", [])
    if documentos:
        movimentos = [{"documentos": documentos}]
    else:
        movimentos = extrato.get("movimentacoes", [])
    session = esaj.criar_session()
    _preparar_documentos(session, extrato, movimentos, limite)
    return esaj.baixar_pecas_publicas(
        session,
        movimentos,
        destino,
        limite=limite,
        sobrescrever=sobrescrever,
    )


def ler_pecas(
    extrato: dict[str, Any],
    limite: int = 3,
    max_chars: int = 4000,
) -> list[dict[str, Any]]:
    """Le pecas publicas candidatas em memoria, sem salvar PDFs em disco."""
    documentos = extrato.get("documentos", {}).get("publicos_candidatos_unicos", [])
    movimentos = [{"documentos": documentos}] if documentos else extrato.get("movimentacoes", [])
    session = esaj.criar_session()
    _preparar_documentos(session, extrato, movimentos, limite)
    return esaj.ler_pecas_publicas(session, movimentos, limite=limite, max_chars=max_chars)


def _preparar_documentos(
    session: Any, extrato: dict[str, Any], movimentos: list[dict[str, Any]], limite: int
) -> None:
    numero = (extrato.get("dados_basicos") or {}).get("numero") or (
        extrato.get("origem") or {}
    ).get("entrada", "")
    if numero:
        esaj.preparar_documentos(session, numero, movimentos, limite)


def resumo_rapido(numero: str) -> str:
    """Gera um resumo textual curto para briefing, e-mail ou triagem."""
    extrato = get_extrato(numero, limite_movimentacoes=esaj.LIMITE_RESUMO)
    info = _resumo_do_extrato(extrato)
    partes = extrato.get("partes", {})
    ativo = _nomes_polo(partes.get("polo_ativo", []))
    passivo = _nomes_polo(partes.get("polo_passivo", []))
    return (
        f"Processo {info.get('numero')} | Classe: {info.get('classe')} | Vara: {info.get('vara')}\n"
        f"Última movimentação: {info.get('ultima_movimentacao')} em {info.get('ultima_data')}\n"
        f"Parte ativa: {ativo or 'não disponível'} | Parte passiva: {passivo or 'não disponível'}"
    )


def consultar_djen(numero: str, data_inicio: str = "") -> list[dict[str, Any]]:
    """Consulta comunicações do DJEN para um processo."""
    return djen.consultar_processo(numero, data_inicio=data_inicio)


def consultar_datajud(
    numero: str,
    *,
    api_key: str | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Consulta dados processuais estruturados na API publica DataJud/CNJ."""
    return cast(
        dict[str, Any],
        datajud.consultar_processo(numero, api_key=api_key, include_raw=include_raw),
    )


def extract_process(
    numero: str,
    *,
    sources: list[str] | tuple[str, ...] = ("esaj", "datajud", "djen"),
    include_raw: bool = False,
    datajud_api_key: str | None = None,
    djen_data_inicio: str = "",
    limite_movimentacoes: int | None = esaj.LIMITE_MOVIMENTACOES,
    desde: str = "",
    prazo_total: float | None = extraction.PRAZO_TOTAL,
) -> dict[str, Any]:
    """Extrai dados das fontes solicitadas em envelope versionado."""
    return cast(
        dict[str, Any],
        extraction.extract_process(
            numero,
            sources=sources,
            include_raw=include_raw,
            datajud_api_key=datajud_api_key,
            djen_data_inicio=djen_data_inicio,
            limite_movimentacoes=limite_movimentacoes,
            desde=desde,
            prazo_total=prazo_total,
        ),
    )


def create_client(config: NanoJudConfig | None = None) -> NanoJudClient:
    """Cria cliente configurável para automações profissionais."""
    return NanoJudClient(config=config)


def _resumo_do_extrato(extrato: Extrato) -> ResumoProcesso:
    basicos = extrato.get("dados_basicos", {})
    movimentos = extrato.get("movimentacoes", [])
    ultima = _ultima_movimentacao(movimentos)
    return {
        "numero": basicos.get("numero", ""),
        "classe": basicos.get("classe", ""),
        "assunto": basicos.get("assunto", ""),
        "foro": basicos.get("foro", ""),
        "vara": basicos.get("vara", ""),
        "juiz": basicos.get("juiz", ""),
        "ultima_movimentacao": ultima.get("titulo") or ultima.get("texto", ""),
        "ultima_data": ultima.get("data", ""),
        "url": extrato.get("origem", {}).get("url_final", ""),
        "status": extrato.get("status", "ok"),
        "mensagem": "Processo consultado com sucesso",
        "situacao": basicos.get("situacao", ""),
    }


def _nomes_polo(partes: list[Any]) -> str:
    nomes = []
    for parte in partes:
        if isinstance(parte, dict):
            nomes.extend(parte.get("nomes", []))
    return ", ".join([nome for nome in nomes if nome])[:250]


def _ultima_movimentacao(movimentos: list[Movimentacao]) -> Movimentacao | dict[str, Any]:
    if not movimentos:
        return {}
    com_data = []
    for indice, movimento in enumerate(movimentos):
        data_iso = normalizar_data(movimento.get("data"))["iso"]
        if data_iso:
            com_data.append((data_iso, -indice, movimento))
    if com_data:
        return max(com_data, key=lambda item: (item[0], item[1]))[2]
    return movimentos[0]
