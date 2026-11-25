"""API pública de alto nível para advogados, escritórios e sistemas."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, cast

from . import batch as batch_api
from . import datajud, djen, eproc_tjsp, esaj, esaj_tjsp_2g, extraction, pje_tjmg, tjmg_legado, tjrj
from .batch import BatchItem, BatchSummary, DocketItem
from .client import NanoJudClient
from .config import NanoJudConfig
from .mni_222 import MNIConfig
from .models import Extrato, ResumoProcesso
from .resumos import resumo_do_extrato as _resumo_do_extrato
from .sources import ALL_SOURCES
from .utils import eh_tjsp, validar_numero_cnj


def consultar_esaj_tjsp_2g(
    numero: str, *, timeout: float = 30.0, max_paginas: int = esaj_tjsp_2g.MAX_PAGINAS
) -> dict[str, Any]:
    """Consulta capa e movimentações públicas dos resultados no e-SAJ/TJSP de 2º grau."""
    return esaj_tjsp_2g.consultar_processo(numero, timeout=timeout, max_paginas=max_paginas)


def consultar_eproc_tjsp_1g(
    numero: str,
    *,
    timeout: float = 30.0,
    headless: bool = False,
    aguardar_desafio_interativo: bool = False,
) -> dict[str, Any]:
    """Consulta capa e histórico públicos do eproc/TJSP de primeiro grau."""
    return eproc_tjsp.consultar_processo(
        numero,
        timeout=timeout,
        headless=headless,
        aguardar_desafio_interativo=aguardar_desafio_interativo,
    )


def consultar_eproc_tjsp_2g(
    numero: str,
    *,
    timeout: float = 30.0,
    headless: bool = False,
    aguardar_desafio_interativo: bool = False,
) -> dict[str, Any]:
    """Consulta capa e histórico públicos do eproc/TJSP de segundo grau."""
    return eproc_tjsp.consultar_processo_2g(
        numero,
        timeout=timeout,
        headless=headless,
        aguardar_desafio_interativo=aguardar_desafio_interativo,
    )


def consultar_tjrj_1g(
    numero: str,
    *,
    timeout: float = 30.0,
    session: Any | None = None,
    max_paginas_movimentos: int = tjrj.MAX_PAGINAS_MOVIMENTOS,
) -> dict[str, Any]:
    """Consulta capa e movimentos públicos do TJRJ de primeiro grau."""
    return tjrj.consultar_processo(
        numero,
        timeout=timeout,
        session=session,
        max_paginas_movimentos=max_paginas_movimentos,
    )


def obter_pdf_esaj_tjsp_2g(
    numero: str,
    cd_documento: str,
    *,
    timeout: float = 30.0,
    max_paginas: int = esaj_tjsp_2g.MAX_PAGINAS,
    max_bytes: int = esaj.MAX_IN_MEMORY_DOCUMENT_BYTES,
) -> bytes:
    """Obtém o PDF de um vínculo público do CPoSG pelo CNJ próprio do resultado."""
    return esaj_tjsp_2g.obter_pdf_publico(
        numero, cd_documento, timeout=timeout, max_paginas=max_paginas, max_bytes=max_bytes
    )


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
    pasta_pecas: Path | None = None,
    session: Any | None = None,
    senha_processo: str | None = None,
    timeout: float = 30.0,
) -> Extrato:
    """Monta extrato eSAJ/TJSP usando a sessão e credencial autorizadas.

    ``session`` pode ser uma ``requests.Session`` autenticada previamente pelo
    fluxo oficial do tribunal. ``senha_processo`` é enviada somente ao formulário
    oficial do processo e não é incluída no extrato nem no cache.
    """
    return esaj.montar_extrato(
        numero,
        baixar_pecas=baixar_pecas,
        limite_pecas=limite_pecas,
        inspecionar_pecas=inspecionar_pecas,
        limite_inspecao_pecas=limite_inspecao_pecas,
        salvar_html=salvar_html,
        limite_movimentacoes=limite_movimentacoes,
        desde=desde,
        pasta_pecas=pasta_pecas,
        session=session,
        senha_processo=senha_processo,
        timeout=timeout,
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
    *,
    session: Any | None = None,
    max_bytes: int = esaj.MAX_DOCUMENT_DOWNLOAD_BYTES,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Baixa documentos acessíveis pela sessão oficial já presentes no extrato.

    Usa os documentos liberados no extrato e respeita o limite informado. Quando
    o portal solicitar autenticação, use uma sessão e/ou senha obtidas pelo fluxo
    oficial e autorizadas para o processo.
    """
    movimentos = []
    documentos = extrato.get("documentos", {}).get("publicos_candidatos_unicos", [])
    if documentos:
        movimentos = [{"documentos": documentos}]
    else:
        movimentos = extrato.get("movimentacoes", [])
    session = session or esaj.criar_session(timeout=timeout)
    _preparar_documentos(session, extrato, movimentos, limite, timeout=timeout)
    return esaj.baixar_pecas_publicas(
        session,
        movimentos,
        destino,
        limite=limite,
        sobrescrever=sobrescrever,
        max_bytes=max_bytes,
        timeout=timeout,
    )


def obter_pdf_esaj(
    numero: str,
    cd_documento: str,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
    max_bytes: int = esaj.MAX_IN_MEMORY_DOCUMENT_BYTES,
    senha_processo: str | None = None,
    senha_processo_provider: Callable[[str, list[Any]], str | None] | None = None,
) -> bytes:
    """Obtém bytes de uma peça e-SAJ acessível pela sessão autorizada."""
    cliente = NanoJudClient(
        config=NanoJudConfig(timeout=timeout),
        session=session,
        senha_processo_provider=senha_processo_provider,
    )
    return cliente.obter_pdf_esaj(
        numero,
        cd_documento,
        max_bytes=max_bytes,
        senha_processo=senha_processo,
    )


def ler_pecas(
    extrato: dict[str, Any],
    limite: int = 3,
    max_chars: int = 4000,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Lê documentos acessíveis pela sessão, sem salvar PDFs em disco."""
    documentos = extrato.get("documentos", {}).get("publicos_candidatos_unicos", [])
    movimentos = [{"documentos": documentos}] if documentos else extrato.get("movimentacoes", [])
    session = session or esaj.criar_session(timeout=timeout)
    _preparar_documentos(session, extrato, movimentos, limite, timeout=timeout)
    return esaj.ler_pecas_publicas(
        session, movimentos, limite=limite, max_chars=max_chars, timeout=timeout
    )


def _preparar_documentos(
    session: Any,
    extrato: dict[str, Any],
    movimentos: list[dict[str, Any]],
    limite: int,
    *,
    timeout: float,
) -> None:
    numero = (extrato.get("dados_basicos") or {}).get("numero") or (
        extrato.get("origem") or {}
    ).get("entrada", "")
    if numero:
        esaj.preparar_documentos(session, numero, movimentos, limite, timeout=timeout)


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


def consultar_djen_detalhado(numero: str, data_inicio: str = "") -> dict[str, Any]:
    """Consulta DJEN incluindo estado de completude e diagnóstico da paginação."""
    return djen.consultar_processo_detalhado(numero, data_inicio=data_inicio)


def consultar_datajud(
    numero: str,
    *,
    api_key: str | None = None,
    include_raw: bool = False,
    prazo_total: float | None = 60.0,
) -> dict[str, Any]:
    """Consulta DataJud/CNJ com prazo total cooperativo de 60 s por padrão."""
    return cast(
        dict[str, Any],
        datajud.consultar_processo(
            numero,
            api_key=api_key,
            include_raw=include_raw,
            prazo_total=prazo_total,
        ),
    )


def consultar_pje_tjmg(
    numero: str,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
    prazo_total: float | None = pje_tjmg.PRAZO_TOTAL,
) -> dict[str, Any]:
    """Consulta as páginas públicas de movimentos/documentos do PJe/TJMG.

    Percorre até 100 páginas por tabela e marca o resultado parcial quando a
    paginação falha, não pode ser verificada ou excede o limite. O provedor ainda
    não está incluído no perfil de fontes padrão. Para obter uma peça listada,
    reutilize a mesma `session` em `obter_pdf_pje_tjmg`; o portal pode vincular a
    URL temporária do documento à sessão que consultou o processo.
    """
    return pje_tjmg.consultar_processo(
        numero, session=session, timeout=timeout, prazo_total=prazo_total
    )


def consultar_tjmg_2g_legado(
    numero: str,
    identificador_tjmg: str,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Lê extrato público legado TJMG 2G com CNJ e ID interno da fonte.

    O ID interno é exigido porque não pode ser derivado do CNJ. O retorno é
    conservadoramente parcial: a paginação e a completude não foram comprovadas.
    """
    return tjmg_legado.consultar_processo(
        numero, identificador_tjmg, session=session, timeout=timeout
    )


def obter_documento_tjmg_2g_legado(
    numero: str,
    identificador_tjmg: str,
    cd_documento: str,
    ano_criacao_doc: str,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
    max_bytes: int = tjmg_legado.MAX_DOCUMENT_BYTES,
) -> tuple[bytes, str]:
    """Obtém em memória peça ligada à página pública TJMG 2G legado."""
    return tjmg_legado.obter_documento_publico(
        numero,
        identificador_tjmg,
        cd_documento,
        ano_criacao_doc,
        session=session,
        timeout=timeout,
        max_bytes=max_bytes,
    )


def ler_documento_pje_tjmg(
    url: str,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Lê um documento que o detalhe público do PJe/TJMG oferece para visualização."""
    return pje_tjmg.ler_documento_publico(
        url, session=session, timeout=timeout, max_chars=max_chars
    )


def obter_pdf_pje_tjmg(
    url: str,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
    max_bytes: int = pje_tjmg.MAX_EMBEDDED_DOCUMENT_BYTES,
) -> bytes:
    """Obtém bytes do PDF público PJe/TJMG dentro do limite solicitado.

    Passe a mesma `session` usada em `consultar_pje_tjmg` para preservar o contexto
    do portal associado à URL temporária do documento.
    """
    return pje_tjmg.obter_pdf_publico(url, session=session, timeout=timeout, max_bytes=max_bytes)


def baixar_documento_pje_tjmg(
    url: str,
    destino: Path,
    *,
    session: Any | None = None,
    timeout: float = 30.0,
    sobrescrever: bool = False,
) -> dict[str, Any]:
    """Baixa um PDF público do PJe/TJMG usando a ação oficial de geração de PDF."""
    return pje_tjmg.baixar_documento_publico(
        url,
        destino,
        session=session,
        timeout=timeout,
        sobrescrever=sobrescrever,
    )


def extract_process(
    numero: str,
    *,
    sources: list[str] | tuple[str, ...] = ALL_SOURCES,
    include_raw: bool = False,
    datajud_api_key: str | None = None,
    datajud_retry: int = 3,
    djen_data_inicio: str = "",
    limite_movimentacoes: int | None = esaj.LIMITE_MOVIMENTACOES,
    desde: str = "",
    timeout: float = 30.0,
    prazo_total: float | None = extraction.PRAZO_TOTAL,
    mni_config: MNIConfig | None = None,
) -> dict[str, Any]:
    """Extrai dados das fontes solicitadas em envelope versionado."""
    return cast(
        dict[str, Any],
        extraction.extract_process(
            numero,
            sources=sources,
            include_raw=include_raw,
            datajud_api_key=datajud_api_key,
            datajud_retry=datajud_retry,
            djen_data_inicio=djen_data_inicio,
            limite_movimentacoes=limite_movimentacoes,
            desde=desde,
            timeout=timeout,
            prazo_total=prazo_total,
            mni_config=mni_config,
        ),
    )


def iter_extract_processes(numeros: Iterable[str], **kwargs: Any) -> Iterator[BatchItem]:
    """Consulta CNJs em fluxo, com resultado isolado para cada entrada."""
    return cast(Iterator[BatchItem], batch_api.iter_extract_processes(numeros, **kwargs))


def extract_processes(numeros: Iterable[str], **kwargs: Any) -> BatchSummary:
    """Consulta um lote finito de CNJs e retorna resumo e resultados por processo."""
    return batch_api.extract_processes(numeros, **kwargs)


def iter_extract_dockets(numeros: Iterable[str], **kwargs: Any) -> Iterator[DocketItem]:
    """Consulta processos e obtém documentos públicos em lote no TJSP/eSAJ ou TJMG/PJe."""
    return batch_api.iter_extract_dockets(numeros, **kwargs)


def create_client(config: NanoJudConfig | None = None) -> NanoJudClient:
    """Cria cliente configurável para automações profissionais."""
    return NanoJudClient(config=config)


def _nomes_polo(partes: list[Any]) -> str:
    nomes = []
    for parte in partes:
        if isinstance(parte, dict):
            nomes.extend(parte.get("nomes", []))
    return ", ".join([nome for nome in nomes if nome])[:250]
