"""Consulta em lote com resultados isolados, backpressure e circuit breaker."""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from .exceptions import AcessoRestrito, URLInvalida, mensagem_erro_segura
from .mni_222 import MNIConfig
from .schemas import SCHEMA_VERSION, ExtractionEnvelope
from .sources import ALL_SOURCES, ESAJ_TJSP_2G, SourceName, normalizar_fonte
from .utils import salvar_pdf_atomico, validar_numero_cnj, validar_prazo_total, validar_timeout
from .version import __version__

BatchStatus = Literal["ok", "partial", "error"]
MAX_BATCH_WORKERS = 8
SUCCESSFUL_TEXT_STATUSES = frozenset({"texto_extraido", "texto_html_extraido"})


class BatchError(TypedDict):
    type: str
    message: str


class BatchItem(TypedDict, total=False):
    index: int
    input: str
    numero_cnj: str
    status: BatchStatus
    result: ExtractionEnvelope
    error: BatchError


class BatchSummary(TypedDict):
    schema_version: str
    total: int
    succeeded: int
    partial: int
    failed: int
    items: list[BatchItem]


class DocketItem(TypedDict, total=False):
    index: int
    input: str
    numero_cnj: str
    status: Literal["ok", "partial", "error", "unsupported", "no_documents"]
    document_candidates: int
    restricted_documents: int
    downloaded: list[dict[str, Any]]
    documents_read: list[dict[str, Any]]
    document_statuses: list[dict[str, Any]]
    authorization_attempts: list[dict[str, Any]]
    warnings: list[str]
    output_directory: str
    summary: dict[str, Any]
    extrato: dict[str, Any]
    error: BatchError


ProcessExtractor = Callable[..., ExtractionEnvelope]


def iter_extract_processes(
    numeros: Iterable[str],
    *,
    sources: Iterable[str] = ALL_SOURCES,
    include_raw: bool = False,
    datajud_api_key: str | None = None,
    mni_config: MNIConfig | None = None,
    djen_data_inicio: str = "",
    desde: str = "",
    timeout: float = 30.0,
    datajud_retry: int = 3,
    limite_movimentacoes: int | None = 100,
    prazo_total: float | None = 60.0,
    max_workers: int = 1,
    circuit_breaker_threshold: int = 1,
    circuit_breaker_cooldown: float = 60.0,
    _extractor: ProcessExtractor | None = None,
) -> Iterator[BatchItem]:
    """Processa números CNJ em fluxo e preserva a ordem de entrada.

    Cada número produz um resultado independente, inclusive quando a validação ou uma
    fonte falha. A concorrência é limitada; o padrão sequencial protege portais públicos.
    Falhas transitórias repetidas abrem um circuito temporário por fonte para evitar
    refazer a mesma chamada indisponível para todos os processos seguintes.
    """
    validar_timeout(timeout)
    validar_prazo_total(prazo_total)
    if (
        isinstance(max_workers, bool)
        or not isinstance(max_workers, int)
        or not 1 <= max_workers <= MAX_BATCH_WORKERS
    ):
        raise ValueError(f"max_workers deve estar entre 1 e {MAX_BATCH_WORKERS}.")
    if (
        isinstance(circuit_breaker_threshold, bool)
        or not isinstance(circuit_breaker_threshold, int)
        or circuit_breaker_threshold < 1
    ):
        raise ValueError("circuit_breaker_threshold deve ser pelo menos 1.")
    if isinstance(circuit_breaker_cooldown, bool) or not isinstance(
        circuit_breaker_cooldown, (int, float)
    ):
        raise ValueError("circuit_breaker_cooldown deve ser número finito não negativo.")
    try:
        cooldown_finito = math.isfinite(circuit_breaker_cooldown)
    except OverflowError:
        cooldown_finito = False
    if not cooldown_finito or circuit_breaker_cooldown < 0:
        raise ValueError("circuit_breaker_cooldown deve ser número finito não negativo.")
    if isinstance(datajud_retry, bool) or not isinstance(datajud_retry, int) or datajud_retry < 1:
        raise ValueError("datajud_retry deve ser pelo menos 1.")

    fontes = tuple(dict.fromkeys(normalizar_fonte(fonte) for fonte in sources))
    if not fontes:
        raise ValueError("Informe pelo menos uma fonte.")
    if "mni" in fontes and max_workers != 1:
        raise ValueError(
            "Lotes MNI usam max_workers=1 até que os limites da instalação estejam confirmados."
        )

    if _extractor is None:
        from .extraction import extract_process

        _extractor = cast(ProcessExtractor, extract_process)

    falhas_por_fonte: dict[SourceName, int] = {fonte: 0 for fonte in fontes}
    circuito_aberto_ate: dict[SourceName, float] = {}

    def estado_circuito() -> tuple[float, dict[SourceName, float]]:
        """Copia o estado no coordenador para não compartilhar mutação com workers."""
        agora = time.monotonic()
        fontes_pausadas = {fonte: ate for fonte, ate in circuito_aberto_ate.items() if ate > agora}
        return agora, fontes_pausadas

    def processar(
        index: int,
        entrada: str,
        agora: float,
        fontes_pausadas: dict[SourceName, float],
    ) -> BatchItem:
        item: BatchItem = {"index": index, "input": entrada, "status": "error"}
        try:
            numero_cnj = validar_numero_cnj(entrada, segmento=None, tribunal=None)
        except Exception as exc:  # entrada inválida não interrompe o lote
            item["error"] = {"type": type(exc).__name__, "message": mensagem_erro_segura(exc)}
            return item

        item["numero_cnj"] = numero_cnj
        fontes_ativas = tuple(fonte for fonte in fontes if fonte not in fontes_pausadas)
        if fontes_ativas:
            try:
                resultado = _extractor(
                    numero_cnj,
                    sources=fontes_ativas,
                    include_raw=include_raw,
                    datajud_api_key=datajud_api_key,
                    mni_config=mni_config,
                    djen_data_inicio=djen_data_inicio,
                    desde=desde,
                    timeout=timeout,
                    datajud_retry=datajud_retry,
                    limite_movimentacoes=limite_movimentacoes,
                    prazo_total=prazo_total,
                )
            except Exception as exc:  # erro de um processo não cancela os demais
                item["error"] = {"type": type(exc).__name__, "message": mensagem_erro_segura(exc)}
                return item
        else:
            resultado = {
                "schema_version": SCHEMA_VERSION,
                "package_version": __version__,
                "status": "error",
                "numero_cnj": numero_cnj,
                "sources": list(fontes),
                "extracted_at": datetime.now(UTC).isoformat(),
                "data": {},
                "timeline": [],
                "warnings": [],
                "errors": [],
                "source_status": {},
                "divergencias": [],
            }
            if include_raw:
                resultado["raw"] = {}

        if fontes_pausadas:
            for fonte, ate in fontes_pausadas.items():
                segundos = max(0, int(ate - agora))
                mensagem = (
                    f"Fonte temporariamente pausada pelo circuit breaker; nova tentativa em "
                    f"aproximadamente {segundos}s."
                )
                resultado["source_status"][fonte] = {
                    "status": "skipped",
                    "type": "CircuitBreakerOpen",
                    "message": mensagem,
                }
                resultado["errors"].append(
                    {"source": fonte, "type": "CircuitBreakerOpen", "message": mensagem}
                )
                resultado["warnings"].append(f"{fonte}: {mensagem}")
            resultado["sources"] = list(fontes)
            resultado["status"] = "partial" if resultado["data"] else "error"

        item["status"] = cast(BatchStatus, resultado["status"])
        item["result"] = resultado
        return item

    def observar(item: BatchItem) -> None:
        resultado = item.get("result")
        if not resultado:
            return
        agora = time.monotonic()
        for erro in resultado.get("errors", []):
            fonte = cast(SourceName, erro.get("source", ""))
            if fonte not in falhas_por_fonte or erro.get("type") not in {
                "ConsultaIndisponivel",
                "TimeoutError",
            }:
                continue
            falhas_por_fonte[fonte] += 1
            if falhas_por_fonte[fonte] >= circuit_breaker_threshold:
                circuito_aberto_ate[fonte] = agora + circuit_breaker_cooldown

        for fonte_status_key, estado in resultado.get("source_status", {}).items():
            if estado.get("status") in {"ok", "partial", "nao_encontrado"}:
                falhas_por_fonte[cast(SourceName, fonte_status_key)] = 0
                circuito_aberto_ate.pop(cast(SourceName, fonte_status_key), None)

    indexed = enumerate(numeros)
    if max_workers == 1:
        for index, entrada in indexed:
            agora, fontes_pausadas = estado_circuito()
            item = processar(index, entrada, agora, fontes_pausadas)
            observar(item)
            yield item
        return

    pendentes: deque[tuple[int, Future[BatchItem]]] = deque()
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="nanojud-batch") as pool:
        try:
            for index, entrada in indexed:
                agora, fontes_pausadas = estado_circuito()
                pendentes.append(
                    (index, pool.submit(processar, index, entrada, agora, fontes_pausadas))
                )
                if len(pendentes) >= max_workers:
                    _, futuro = pendentes.popleft()
                    item = futuro.result()
                    observar(item)
                    yield item
            while pendentes:
                _, futuro = pendentes.popleft()
                item = futuro.result()
                observar(item)
                yield item
        finally:
            for _, futuro in pendentes:
                futuro.cancel()


def extract_processes(
    numeros: Iterable[str],
    *,
    _iterator: Callable[..., Iterator[BatchItem]] = iter_extract_processes,
    **kwargs: Any,
) -> BatchSummary:
    """Versão agregada de iter_extract_processes para lotes que cabem em memória."""
    itens = list(_iterator(numeros, **kwargs))
    return {
        "schema_version": "1.0",
        "total": len(itens),
        "succeeded": sum(item.get("status") == "ok" for item in itens),
        "partial": sum(item.get("status") == "partial" for item in itens),
        "failed": sum(item.get("status") == "error" for item in itens),
        "items": itens,
    }


def _extrair_autos_pje(
    numero_cnj: str,
    item: DocketItem,
    *,
    root: Path,
    max_documents_per_process: int,
    read_documents: bool,
    document_max_chars: int,
    include_extract: bool,
    consultar: Callable[[str], Any],
    ler: Callable[..., Any],
    baixar: Callable[[str, Path], Any],
) -> DocketItem:
    """Consulta e obtém apenas os documentos públicos apresentados pelo PJe/TJMG."""
    try:
        extrato = consultar(numero_cnj)
        origem = extrato.get("origem") or {}
        docs = extrato.get("documentos") or {}
        candidatos = docs.get("publicos_candidatos_unicos") or []
        item["document_candidates"] = len(candidatos)
        completa_movimentos = origem.get("movimentacoes_completas") is True
        completa_documentos = origem.get("documentos_completos") is True
        item["summary"] = {
            "classe": (extrato.get("dados_basicos") or {}).get("classe", ""),
            "movements": len(extrato.get("movimentacoes") or []),
            "movimentacoes_completas": completa_movimentos,
            "documentos_completos": completa_documentos,
        }
        if include_extract:
            item["extrato"] = cast(dict[str, Any], extrato)

        avisos = [
            str(origem[key])
            for key in ("aviso_movimentacoes", "aviso_documentos")
            if origem.get(key)
        ]
        if not completa_movimentos and not origem.get("aviso_movimentacoes"):
            avisos.append("A consulta PJe não confirmou a completude das movimentações.")
        if not completa_documentos and not origem.get("aviso_documentos"):
            avisos.append("A consulta PJe não confirmou a completude dos documentos.")
        if extrato.get("status") == "partial" and not avisos:
            avisos.append("A consulta pública do PJe retornou resultado parcial.")
        limite = (
            min(len(candidatos), max_documents_per_process)
            if max_documents_per_process
            else len(candidatos)
        )
        if max_documents_per_process and len(candidatos) > max_documents_per_process:
            avisos.append(
                f"Peças limitadas a {max_documents_per_process} de "
                f"{len(candidatos)} candidatas públicas listadas."
            )

        pasta = root / numero_cnj
        lidos: list[dict[str, Any]] = []
        baixados: list[dict[str, Any]] = []
        estados: list[dict[str, Any]] = []
        for documento in candidatos[:limite]:
            url = str(documento.get("href") or "")
            documento_id = str(documento.get("cd_documento") or "")
            titulo = str(documento.get("titulo") or "Documento")
            try:
                if read_documents:
                    resultado = ler(url, max_chars=document_max_chars)
                    status_doc = str(resultado.get("status") or "error")
                    registro = {"cd_documento": documento_id, "titulo": titulo, **resultado}
                    lidos.append(registro)
                    mensagem = str(resultado.get("mensagem") or "")
                    if status_doc == "pdf_sem_texto_extraido" and not mensagem:
                        mensagem = "O PDF foi obtido, mas não contém texto extraível."
                else:
                    identidade = f"id:{documento_id}" if documento_id else f"url:{url}"
                    chave = sha256(identidade.encode()).hexdigest()
                    destino = pasta / f"documento-{chave}.pdf"
                    resultado = baixar(url, destino)
                    status_doc = str(resultado.get("status") or "error")
                    if status_doc in {"baixado", "existente"}:
                        baixados.append(
                            {"cd_documento": documento_id, "titulo": titulo, **resultado}
                        )
                    mensagem = str(resultado.get("mensagem") or "")
            except Exception as exc:  # noqa: BLE001 - uma peça não deve cancelar as demais
                status_doc = "error"
                mensagem = mensagem_erro_segura(exc)
                if read_documents:
                    lidos.append(
                        {
                            "cd_documento": documento_id,
                            "titulo": titulo,
                            "status": status_doc,
                            "mensagem": mensagem,
                        }
                    )
            estados.append(
                {
                    "cd_documento": documento_id,
                    "titulo": titulo,
                    "status": status_doc,
                    "message": mensagem,
                }
            )

        if read_documents:
            item["documents_read"] = lidos
        else:
            item["downloaded"] = baixados
            item["output_directory"] = str(pasta)
        item["document_statuses"] = estados
        if avisos:
            item["warnings"] = avisos

        falha_documento = any(
            estado["status"] not in {"baixado", "existente"}
            if not read_documents
            else estado["status"] not in SUCCESSFUL_TEXT_STATUSES
            for estado in estados
        )
        if falha_documento:
            estados_falhos = [
                estado
                for estado in estados
                if estado["status"]
                not in (SUCCESSFUL_TEXT_STATUSES if read_documents else {"baixado", "existente"})
            ]
            avisos.append(
                f"{len(estados_falhos)} de {len(estados)} peça(s) selecionada(s) não foi(ram) "
                "obtida(s) ou não teve(ram) texto extraído."
            )
            item["warnings"] = avisos
        if not candidatos and completa_documentos and completa_movimentos and not avisos:
            item["status"] = "no_documents"
        elif not completa_movimentos or not completa_documentos or bool(avisos) or falha_documento:
            item["status"] = "partial"
        else:
            item["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - isola falha do processo no lote
        item["status"] = "error"
        item["error"] = {"type": type(exc).__name__, "message": mensagem_erro_segura(exc)}
        if isinstance(exc, URLInvalida):
            item["status"] = "unsupported"
    return item


def _extrair_vinculos_cposg(
    numero_cnj: str,
    item: DocketItem,
    *,
    root: Path,
    limite: int,
    ler: bool,
    max_chars: int,
    incluir_extrato: bool,
    desde: str,
    timeout: float,
) -> DocketItem:
    from . import esaj, esaj_tjsp_2g
    from .normalization import normalizar_data

    pasta = root / numero_cnj / "cposg"
    estados: list[dict[str, Any]] = []
    obtidos: list[dict[str, Any]] = []
    try:
        with esaj.criar_session(timeout=timeout) as sessao:
            extrato = esaj_tjsp_2g._consultar(sessao, numero_cnj, timeout)
            avisos = list(extrato["avisos"])
            candidatos: dict[tuple[str, str], tuple[str, str]] = {}
            for resultado in extrato["resultados"]:
                if resultado["status"] == "erro":
                    avisos.append(f"{resultado['numero']}: {resultado['erro']['mensagem']}")
                    continue
                if resultado["aviso_movimentacoes"]:
                    avisos.append(f"{resultado['numero']}: {resultado['aviso_movimentacoes']}")
                numero = resultado["numero"]
                codigo = resultado["dados_basicos"]["codigo_esaj"]
                for movimento in resultado["movimentacoes"]:
                    if desde and (normalizar_data(movimento["data"])["iso"] or desde) < desde:
                        continue
                    for doc in movimento["documentos"]:
                        candidatos.setdefault(
                            (codigo, doc["cd_documento"]), (numero, doc["titulo"])
                        )

            item["document_candidates"] = len(candidatos)
            item["summary"] = {
                "fonte": ESAJ_TJSP_2G,
                "grau": "2g",
                "escopo_documentos": "vinculos_movimentacoes",
                "autos_completos": False,
                "movimentacoes_completas": extrato["status"] == "ok",
            }
            if incluir_extrato:
                item["extrato"] = extrato
            if limite and len(candidatos) > limite:
                avisos.append(f"Peças limitadas a {limite} de {len(candidatos)} vínculos listados.")

            for (codigo, documento), (numero, titulo) in list(candidatos.items())[: limite or None]:
                registro = {
                    "numero_cnj": numero,
                    "codigo_esaj": codigo,
                    "cd_documento": documento,
                    "titulo": titulo,
                }
                mensagem = ""
                try:
                    pdf = esaj_tjsp_2g._baixar_pdf_vinculado(
                        sessao,
                        numero,
                        codigo,
                        documento,
                        timeout,
                        esaj.MAX_IN_MEMORY_DOCUMENT_BYTES,
                    )
                    if ler:
                        texto, status = esaj.extrair_texto_pdf_bytes(pdf, max_chars)
                        mensagem = esaj.mensagem_status_extracao_pdf(status)
                        obtidos.append({**registro, "status": status, "texto": texto})
                    else:
                        destino = pasta / numero / codigo / f"peca-{documento}.pdf"
                        destino.parent.mkdir(parents=True, exist_ok=True)
                        salvar_pdf_atomico(pdf, destino)
                        status = "baixado"
                        obtidos.append({**registro, "status": status, "arquivo": str(destino)})
                except Exception as exc:  # noqa: BLE001 - uma peça não cancela os demais vínculos
                    status = "restrito" if isinstance(exc, AcessoRestrito) else "error"
                    mensagem = mensagem_erro_segura(exc)
                estados.append({**registro, "status": status, "message": mensagem})
    except Exception as exc:  # noqa: BLE001 - uma falha de consulta não cancela os demais CNJs
        item["error"] = {"type": type(exc).__name__, "message": mensagem_erro_segura(exc)}
        return item

    item["document_statuses"] = estados
    item["restricted_documents"] = sum(estado["status"] == "restrito" for estado in estados)
    if ler:
        item["documents_read"] = obtidos
    else:
        item["downloaded"] = obtidos
        item["output_directory"] = str(pasta)
    aceitos = SUCCESSFUL_TEXT_STATUSES if ler else {"baixado"}
    if extrato["status"] == "erro":
        item["error"] = {
            "type": "ConsultaInconclusiva",
            "message": "Nenhuma capa do CPoSG foi confirmada.",
        }
    elif avisos or any(estado["status"] not in aceitos for estado in estados):
        item["status"] = "partial"
    else:
        item["status"] = "ok" if candidatos else "no_documents"
    if avisos:
        item["warnings"] = avisos
    return item


def iter_extract_dockets(
    numeros: Iterable[str],
    *,
    destination: str,
    max_documents_per_process: int = 10,
    read_documents: bool = False,
    document_max_chars: int = 4000,
    include_extract: bool = False,
    limite_movimentacoes: int | None = 100,
    desde: str = "",
    timeout: float = 30.0,
    source: str | None = None,
    _get_extrato: Callable[..., Any] | None = None,
    _read_documents: Callable[..., Any] | None = None,
    _consultar_pje: Callable[[str], Any] | None = None,
    _ler_pje: Callable[..., Any] | None = None,
    _baixar_pje: Callable[[str, Path], Any] | None = None,
) -> Iterator[DocketItem]:
    """Obtém extratos e documentos públicos em lote no eSAJ/TJSP ou PJe/TJMG.

    Cada processo é tratado sequencialmente para não sobrecarregar o portal. PDFs são
    salvos em uma pasta por CNJ quando `read_documents=False`; no modo de leitura o texto
    é extraído em memória e não são criados PDFs locais.
    """
    validar_timeout(timeout)
    if source not in (None, ESAJ_TJSP_2G):
        raise ValueError("source deve ser esaj_tjsp_2g ou omitido para roteamento padrão.")
    if (
        isinstance(max_documents_per_process, bool)
        or not isinstance(max_documents_per_process, int)
        or max_documents_per_process < 0
    ):
        raise ValueError("max_documents_per_process deve ser inteiro não negativo.")
    if (
        isinstance(document_max_chars, bool)
        or not isinstance(document_max_chars, int)
        or document_max_chars < 0
    ):
        raise ValueError("document_max_chars deve ser inteiro não negativo.")

    from . import api, pje_tjmg
    from .utils import eh_tjsp

    obter_extrato = _get_extrato or partial(api.get_extrato, timeout=timeout)
    ler_documentos = _read_documents or partial(api.ler_pecas, timeout=timeout)
    sessao_pje: Any = None

    def obter_sessao_pje() -> Any:
        nonlocal sessao_pje
        if sessao_pje is None:
            sessao_pje = pje_tjmg.criar_sessao()
        return sessao_pje

    def consultar_pje(numero: str) -> Any:
        if _consultar_pje is not None:
            return _consultar_pje(numero)
        return api.consultar_pje_tjmg(numero, session=obter_sessao_pje(), timeout=timeout)

    def ler_pje(url: str, *, max_chars: int) -> Any:
        if _ler_pje is not None:
            return _ler_pje(url, max_chars=max_chars)
        return api.ler_documento_pje_tjmg(
            url, session=obter_sessao_pje(), max_chars=max_chars, timeout=timeout
        )

    def baixar_pje(url: str, destino: Path) -> Any:
        if _baixar_pje is not None:
            return _baixar_pje(url, destino)
        return api.baixar_documento_pje_tjmg(
            url, destino, session=obter_sessao_pje(), timeout=timeout
        )

    root = Path(destination)
    try:
        for index, entrada in enumerate(numeros):
            item: DocketItem = {"index": index, "input": entrada, "status": "error"}
            try:
                numero_cnj = validar_numero_cnj(entrada, segmento=None, tribunal=None)
                item["numero_cnj"] = numero_cnj
            except Exception as exc:
                item["error"] = {"type": type(exc).__name__, "message": mensagem_erro_segura(exc)}
                yield item
                continue

            if source == ESAJ_TJSP_2G:
                if eh_tjsp(numero_cnj):
                    yield _extrair_vinculos_cposg(
                        numero_cnj,
                        item,
                        root=root,
                        limite=max_documents_per_process,
                        ler=read_documents,
                        max_chars=document_max_chars,
                        incluir_extrato=include_extract,
                        desde=desde,
                        timeout=timeout,
                    )
                else:
                    item["status"] = "unsupported"
                    item["error"] = {
                        "type": "AutosSourceUnsupported",
                        "message": "CPoSG cobre apenas o TJSP.",
                    }
                    yield item
                continue

            if eh_tjsp(numero_cnj):
                pass
            elif numero_cnj.split(".")[2:4] == ["8", "13"]:
                item = _extrair_autos_pje(
                    numero_cnj,
                    item,
                    root=root,
                    max_documents_per_process=max_documents_per_process,
                    read_documents=read_documents,
                    document_max_chars=document_max_chars,
                    include_extract=include_extract,
                    consultar=consultar_pje,
                    ler=ler_pje,
                    baixar=baixar_pje,
                )
                yield item
                continue
            else:
                item["status"] = "unsupported"
                item["error"] = {
                    "type": "AutosSourceUnsupported",
                    "message": (
                        "Autos em lote estão disponíveis para eSAJ/TJSP e PJe/TJMG nesta versão."
                    ),
                }
                yield item
                continue

            pasta = root / numero_cnj
            try:
                extrato = obter_extrato(
                    numero_cnj,
                    baixar_pecas=not read_documents,
                    limite_pecas=max_documents_per_process,
                    limite_movimentacoes=limite_movimentacoes,
                    desde=desde,
                    pasta_pecas=pasta,
                )
                docs = extrato.get("documentos", {})
                candidatos = docs.get("publicos_candidatos_unicos", [])
                restritos = docs.get("restritos_por_senha_unicos", [])
                item["document_candidates"] = len(candidatos)
                item["restricted_documents"] = len(restritos)
                if docs.get("tentativas_autorizacao"):
                    item["authorization_attempts"] = docs["tentativas_autorizacao"]
                item["summary"] = {
                    "classe": (extrato.get("dados_basicos") or {}).get("classe", ""),
                    "movements": len(extrato.get("movimentacoes", [])),
                    "movimentacoes_completas": (extrato.get("origem") or {}).get(
                        "movimentacoes_completas", False
                    ),
                }
                if read_documents:
                    item["documents_read"] = ler_documentos(
                        cast(dict[str, Any], extrato),
                        limite=max_documents_per_process,
                        max_chars=document_max_chars,
                    )
                else:
                    item["downloaded"] = docs.get("baixados", [])
                    item["output_directory"] = str(pasta)
                if include_extract:
                    item["extrato"] = cast(dict[str, Any], extrato)
                avisos: list[str] = []
                if restritos:
                    avisos.append(f"{len(restritos)} documento(s) restrito(s) não foram acessados.")
                if max_documents_per_process and len(candidatos) > max_documents_per_process:
                    avisos.append(
                        f"Peças limitadas a {max_documents_per_process} de "
                        f"{len(candidatos)} candidatas públicas."
                    )
                if not item["summary"]["movimentacoes_completas"]:
                    aviso_movimentacoes = (extrato.get("origem") or {}).get("aviso_movimentacoes")
                    avisos.append(
                        str(aviso_movimentacoes)
                        if aviso_movimentacoes
                        else "O extrato não contém todas as movimentações disponíveis."
                    )
                if avisos:
                    item["warnings"] = avisos
                sem_documentos = not candidatos
                limite_efetivo = (
                    min(len(candidatos), max_documents_per_process)
                    if max_documents_per_process
                    else len(candidatos)
                )
                status_downloads = [
                    doc.get("download_status") for doc in candidatos[:limite_efetivo]
                ]
                if read_documents:
                    leituras = item.get("documents_read", [])
                    item["document_statuses"] = [
                        {
                            "cd_documento": registro.get("cd_documento", ""),
                            "status": registro.get("status", ""),
                            "message": registro.get("mensagem", ""),
                        }
                        for registro in leituras
                    ]
                    erro_download = len(leituras) < limite_efetivo or any(
                        registro.get("status") not in SUCCESSFUL_TEXT_STATUSES
                        for registro in leituras
                    )
                else:
                    item["document_statuses"] = [
                        {
                            "cd_documento": doc.get("cd_documento", ""),
                            "status": doc.get("download_status", "pendente"),
                            "message": doc.get("download_message", ""),
                        }
                        for doc in candidatos[:limite_efetivo]
                    ]
                    erro_download = any(
                        status not in {"baixado", "existente"} for status in status_downloads
                    )
                if sem_documentos and not restritos and item["summary"]["movimentacoes_completas"]:
                    item["status"] = "no_documents"
                elif sem_documentos or restritos or erro_download or avisos:
                    item["status"] = "partial"
                else:
                    item["status"] = "ok"
            except Exception as exc:
                item["error"] = {"type": type(exc).__name__, "message": mensagem_erro_segura(exc)}
            yield item
    finally:
        if sessao_pje is not None:
            sessao_pje.close()
