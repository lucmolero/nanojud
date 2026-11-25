"""Cliente de alto nível configurável."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from copy import deepcopy
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from urllib.parse import urlsplit

import requests

from . import datajud, djen, eproc_tjsp, esaj, extraction, pje_tjmg, tjmg_legado, tjrj
from .batch import BatchItem, BatchSummary, DocketItem
from .cache import JsonFileCache
from .config import NanoJudConfig
from .exceptions import AcessoRestrito, DocumentoNaoEncontrado, DownloadIndisponivel
from .models import Extrato, ResumoProcesso
from .resumos import resumo_do_extrato as _resumo_do_extrato
from .sources import ALL_SOURCES
from .utils import eh_tjsp, validar_numero_cnj
from .version import __version__


class RateLimitedSession(requests.Session):
    """Sessão requests com timeout padrão, rate limit simples e logging."""

    def __init__(
        self,
        *,
        timeout: float,
        rate_limit_interval: float,
        logger: logging.Logger,
        user_agent: str,
    ) -> None:
        super().__init__()
        self.timeout = timeout
        self.rate_limit_interval = rate_limit_interval
        self.logger = logger
        self._last_request_at_by_origin: dict[str, float] = {}
        self._origin_locks: dict[str, threading.RLock] = {}
        self._origin_locks_guard = threading.Lock()
        self.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": f"{esaj.ESAJ_BASE}/open.do",
            }
        )

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout
        origin = _origin_for_log(url)
        with self._lock_for_origin(origin):
            self._wait_if_needed(origin)
            self.logger.debug("HTTP %s %s", method.upper(), origin)
            try:
                response = super().request(method, url, **kwargs)
            finally:
                self._last_request_at_by_origin[origin] = time.monotonic()
        self.logger.debug("HTTP %s %s -> %s", method.upper(), origin, response.status_code)
        return response

    def _lock_for_origin(self, origin: str) -> threading.RLock:
        with self._origin_locks_guard:
            lock = self._origin_locks.get(origin)
            if lock is None:
                lock = threading.RLock()
                self._origin_locks[origin] = lock
            return lock

    def _wait_if_needed(self, origin: str) -> None:
        last_request_at = self._last_request_at_by_origin.get(origin, 0.0)
        if self.rate_limit_interval <= 0 or last_request_at <= 0:
            return
        elapsed = time.monotonic() - last_request_at
        remaining = self.rate_limit_interval - elapsed
        if remaining > 0:
            self.logger.debug("Rate limit: aguardando %.2fs", remaining)
            time.sleep(remaining)


def _cache_key(**opcoes: Any) -> str:
    """Serializa parâmetros de cache sem colisões por delimitadores de texto."""
    return json.dumps(opcoes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _origin_for_log(url: str) -> str:
    """Retorna somente a origem para não registrar identificadores ou tokens da URL."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    if not parsed.scheme or not parsed.netloc:
        return "<invalid-url>"
    host = parsed.netloc.rsplit("@", 1)[-1].lower()
    return f"{parsed.scheme.lower()}://{host}"


class NanoJudClient:
    """Cliente configurável para uso profissional em integrações."""

    def __init__(
        self,
        config: NanoJudConfig | None = None,
        *,
        logger: logging.Logger | None = None,
        session: requests.Session | None = None,
        senha_processo_provider: Callable[[str, list[Any]], str | None] | None = None,
    ) -> None:
        self.config = config or NanoJudConfig()
        self.logger = logger or logging.getLogger("nanojud")
        self.session = session or RateLimitedSession(
            timeout=self.config.timeout,
            rate_limit_interval=self.config.rate_limit_interval,
            logger=self.logger,
            user_agent=self.config.resolved_user_agent(__version__),
        )
        # Não compartilha extratos autenticados no cache local: a autorização pode
        # variar entre identidades, e o cache não deve cruzar sessões de advogados.
        self._session_injected = session is not None
        self.senha_processo_provider = senha_processo_provider
        self._extratos: dict[str, Extrato] = {}  # último extrato completo por processo
        self.cache = (
            JsonFileCache(self.config.cache_dir, self.config.cache_ttl_seconds)
            if self.config.cache_enabled
            else None
        )

    def search_processo(self, numero: str) -> ResumoProcesso:
        """Resumo do processo. Reaproveita o extrato já buscado por este cliente."""
        numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
        if not eh_tjsp(numero_cnj):
            return datajud.resumo_do_datajud(self.consultar_datajud(numero_cnj))
        extrato = self._extratos.get(numero_cnj) or self.get_extrato(
            numero_cnj, limite_movimentacoes=esaj.LIMITE_RESUMO
        )
        return _resumo_do_extrato(extrato)

    def get_extrato(
        self,
        numero: str,
        baixar_pecas: bool = False,
        limite_pecas: int = 3,
        *,
        inspecionar_pecas: bool = False,
        limite_inspecao_pecas: int = 10,
        salvar_html: bool | None = None,
        limite_movimentacoes: int | None = -1,
        desde: str = "",
        pasta_pecas: Path | None = None,
        senha_processo: str | None = None,
        timeout: float | None = None,
    ) -> Extrato:
        """``limite_movimentacoes=-1`` usa o valor de ``NanoJudConfig``; ``None`` busca todas."""
        numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
        if limite_movimentacoes == -1:
            limite_movimentacoes = self.config.limite_movimentacoes
        salvar_html_efetivo = self.config.salvar_html if salvar_html is None else salvar_html
        cache_key = _cache_key(
            numero=numero,
            baixar_pecas=baixar_pecas,
            limite_pecas=limite_pecas,
            inspecionar_pecas=inspecionar_pecas,
            limite_inspecao_pecas=limite_inspecao_pecas,
            limite_movimentacoes=limite_movimentacoes,
            desde=desde,
            salvar_html=salvar_html_efetivo,
        )
        if (
            self.cache
            and not baixar_pecas
            and not self._session_injected
            and senha_processo is None
            and self.senha_processo_provider is None
        ):
            cached = self.cache.get("extrato", cache_key)
            if cached is not None:
                self.logger.debug("Cache hit para extrato.")
                return cached

        timeout_efetivo = self.config.timeout if timeout is None else timeout
        extrato = esaj.montar_extrato(
            numero,
            baixar_pecas=baixar_pecas,
            limite_pecas=limite_pecas,
            inspecionar_pecas=inspecionar_pecas,
            limite_inspecao_pecas=limite_inspecao_pecas,
            salvar_html=salvar_html_efetivo,
            session=self.session,
            timeout=timeout_efetivo,
            limite_movimentacoes=limite_movimentacoes,
            pausa_paginas=self.config.pausa_paginas,
            desde=desde,
            pasta_pecas=pasta_pecas,
            senha_processo=senha_processo,
            senha_processo_provider=self.senha_processo_provider,
        )
        if (
            self.cache
            and not baixar_pecas
            and not self._session_injected
            and senha_processo is None
            and self.senha_processo_provider is None
        ):
            self.cache.set("extrato", cache_key, extrato)
        if not desde and (extrato.get("origem") or {}).get("movimentacoes_completas") is not False:
            self._extratos[numero] = extrato
            while len(self._extratos) > 64:  # limite simples de memória
                self._extratos.pop(next(iter(self._extratos)))
        return extrato

    def get_partes(self, numero: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.get_extrato(numero).get(
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

    def consultar_djen(self, numero: str, data_inicio: str = "") -> list[dict[str, Any]]:
        numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
        cache_key = _cache_key(numero=numero, data_inicio=data_inicio)
        if self.cache:
            cached = self.cache.get("djen", cache_key)
            if cached is not None:
                self.logger.debug("Cache hit para DJEN.")
                return cast(list[dict[str, Any]], cached)
        detalhado = djen.consultar_processo_detalhado(
            numero,
            data_inicio=data_inicio,
            session=self.session,
            timeout=self.config.timeout,
        )
        resultado = cast(list[dict[str, Any]], detalhado["comunicacoes"])
        if self.cache and detalhado["completo"]:
            self.cache.set("djen", cache_key, resultado)
        return resultado

    def consultar_djen_detalhado(self, numero: str, data_inicio: str = "") -> dict[str, Any]:
        """Consulta DJEN sem ocultar se a paginação terminou ou foi limitada."""
        numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
        return djen.consultar_processo_detalhado(
            numero,
            data_inicio=data_inicio,
            session=self.session,
            timeout=self.config.timeout,
        )

    def consultar_datajud(
        self,
        numero: str,
        *,
        include_raw: bool = False,
        api_key: str | None = None,
        prazo_total: float | None = 60.0,
    ) -> dict[str, Any]:
        numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
        cache_key = _cache_key(numero=numero, include_raw=include_raw)
        if self.cache and not include_raw:
            cached = self.cache.get("datajud", cache_key)
            if cached is not None:
                self.logger.debug("Cache hit para DataJud.")
                return cast(dict[str, Any], cached)
        resultado = datajud.consultar_processo(
            numero,
            api_key=api_key or self.config.datajud_api_key,
            include_raw=include_raw,
            session=self.session,
            timeout=self.config.timeout,
            prazo_total=prazo_total,
        )
        if self.cache and not include_raw and resultado.get("status") in {"ok", "nao_encontrado"}:
            self.cache.set("datajud", cache_key, resultado)
        return cast(dict[str, Any], resultado)

    def extract_process(
        self,
        numero: str,
        *,
        sources: list[str] | tuple[str, ...] = ALL_SOURCES,
        include_raw: bool = False,
        datajud_api_key: str | None = None,
        djen_data_inicio: str = "",
        desde: str = "",
        limite_movimentacoes: int | None = None,
        datajud_retry: int = 3,
        prazo_total: float | None = extraction.PRAZO_TOTAL,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            extraction.extract_process(
                numero,
                sources=sources,
                include_raw=include_raw,
                datajud_api_key=(
                    self.config.datajud_api_key if datajud_api_key is None else datajud_api_key
                ),
                datajud_retry=datajud_retry,
                djen_data_inicio=djen_data_inicio,
                session=self.session,
                timeout=self.config.timeout,
                limite_movimentacoes=(
                    self.config.limite_movimentacoes
                    if limite_movimentacoes is None
                    else limite_movimentacoes
                ),
                desde=desde,
                prazo_total=prazo_total,
                mni_config=self.config.mni_config,
            ),
        )

    def iter_extract_processes(self, numeros: Iterable[str], **kwargs: Any) -> Iterator[BatchItem]:
        """Consulta CNJs em fluxo usando as opções deste cliente."""
        from .batch import iter_extract_processes

        if kwargs.get("max_workers", 1) != 1:
            raise ValueError("NanoJudClient mantém uma sessão HTTP; use max_workers=1.")
        kwargs.setdefault("timeout", self.config.timeout)
        kwargs.setdefault("limite_movimentacoes", self.config.limite_movimentacoes)
        if kwargs.get("datajud_api_key") is None:
            kwargs["datajud_api_key"] = self.config.datajud_api_key
        if kwargs.get("mni_config") is None:
            kwargs["mni_config"] = self.config.mni_config
        kwargs.setdefault("datajud_retry", 3)
        return iter_extract_processes(
            numeros, _extractor=partial(extraction.extract_process, session=self.session), **kwargs
        )

    def consultar_pje_tjmg(
        self,
        numero: str,
        *,
        timeout: float | None = None,
        prazo_total: float | None = pje_tjmg.PRAZO_TOTAL,
    ) -> dict[str, Any]:
        """Consulta páginas públicas PJe/TJMG usando a sessão do cliente."""
        return pje_tjmg.consultar_processo(
            numero,
            session=self.session,
            timeout=self.config.timeout if timeout is None else timeout,
            prazo_total=prazo_total,
        )

    def consultar_tjmg_2g_legado(
        self,
        numero: str,
        identificador_tjmg: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Consulta detalhe público legado TJMG 2G usando a sessão do cliente."""
        return tjmg_legado.consultar_processo(
            numero,
            identificador_tjmg,
            session=self.session,
            timeout=self.config.timeout if timeout is None else timeout,
        )

    def obter_documento_tjmg_2g_legado(
        self,
        numero: str,
        identificador_tjmg: str,
        cd_documento: str,
        ano_criacao_doc: str,
        *,
        timeout: float | None = None,
        max_bytes: int = tjmg_legado.MAX_DOCUMENT_BYTES,
    ) -> tuple[bytes, str]:
        """Obtém peça listada no detalhe público TJMG 2G usando sessão do cliente."""
        return tjmg_legado.obter_documento_publico(
            numero,
            identificador_tjmg,
            cd_documento,
            ano_criacao_doc,
            session=self.session,
            timeout=self.config.timeout if timeout is None else timeout,
            max_bytes=max_bytes,
        )

    def consultar_tjrj_1g(
        self,
        numero: str,
        *,
        timeout: float | None = None,
        max_paginas_movimentos: int = tjrj.MAX_PAGINAS_MOVIMENTOS,
    ) -> dict[str, Any]:
        """Consulta a rota pública TJRJ 1G usando a sessão configurada do cliente."""
        return tjrj.consultar_processo(
            numero,
            session=self.session,
            timeout=self.config.timeout if timeout is None else timeout,
            max_paginas_movimentos=max_paginas_movimentos,
        )

    def consultar_eproc_tjsp_1g(
        self,
        numero: str,
        *,
        timeout: float | None = None,
        headless: bool = False,
        aguardar_desafio_interativo: bool = False,
    ) -> dict[str, Any]:
        """Consulta o eproc/TJSP de primeiro grau pela interface pública oficial."""
        return eproc_tjsp.consultar_processo(
            numero,
            timeout=self.config.timeout if timeout is None else timeout,
            headless=headless,
            aguardar_desafio_interativo=aguardar_desafio_interativo,
        )

    def consultar_eproc_tjsp_2g(
        self,
        numero: str,
        *,
        timeout: float | None = None,
        headless: bool = False,
        aguardar_desafio_interativo: bool = False,
    ) -> dict[str, Any]:
        """Consulta o eproc/TJSP de segundo grau pela Consulta Unificada pública."""
        return eproc_tjsp.consultar_processo_2g(
            numero,
            timeout=self.config.timeout if timeout is None else timeout,
            headless=headless,
            aguardar_desafio_interativo=aguardar_desafio_interativo,
        )

    def ler_documento_pje_tjmg(
        self, url: str, *, max_chars: int = 4000, timeout: float | None = None
    ) -> dict[str, Any]:
        """Lê PDF oferecido publicamente pelo PJe/TJMG, sem salvá-lo em disco."""
        return pje_tjmg.ler_documento_publico(
            url,
            session=self.session,
            timeout=self.config.timeout if timeout is None else timeout,
            max_chars=max_chars,
        )

    def obter_pdf_pje_tjmg(
        self, url: str, *, max_bytes: int = pje_tjmg.MAX_EMBEDDED_DOCUMENT_BYTES
    ) -> bytes:
        """Obtém bytes de um PDF público PJe/TJMG limitado ao tamanho solicitado."""
        return pje_tjmg.obter_pdf_publico(
            url,
            session=self.session,
            timeout=self.config.timeout,
            max_bytes=max_bytes,
        )

    def baixar_documento_pje_tjmg(
        self,
        url: str,
        destino: Path,
        *,
        sobrescrever: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Baixa um PDF público do PJe/TJMG para o caminho escolhido pelo chamador."""
        return pje_tjmg.baixar_documento_publico(
            url,
            destino,
            session=self.session,
            timeout=self.config.timeout if timeout is None else timeout,
            sobrescrever=sobrescrever,
        )

    def extract_processes(self, numeros: Iterable[str], **kwargs: Any) -> BatchSummary:
        """Consulta um lote finito usando as opções deste cliente."""
        from .batch import extract_processes

        return extract_processes(numeros, _iterator=self.iter_extract_processes, **kwargs)

    def iter_extract_dockets(
        self, numeros: Iterable[str], *, destination: str | Path, **kwargs: Any
    ) -> Iterator[DocketItem]:
        """Consulta e obtém autos em fluxo usando sessão, timeout e pausas deste cliente."""
        from .batch import iter_extract_dockets

        kwargs.setdefault("timeout", self.config.timeout)
        timeout = kwargs["timeout"]
        return iter_extract_dockets(
            numeros,
            destination=str(destination),
            _get_extrato=partial(self.get_extrato, timeout=timeout),
            _read_documents=partial(self.ler_pecas, timeout=timeout),
            _consultar_pje=partial(self.consultar_pje_tjmg, timeout=timeout),
            _ler_pje=partial(self.ler_documento_pje_tjmg, timeout=timeout),
            _baixar_pje=partial(
                self.baixar_documento_pje_tjmg, sobrescrever=False, timeout=timeout
            ),
            **kwargs,
        )

    def _preparar_documentos(
        self, extrato: dict[str, Any], movimentos: list[dict[str, Any]], limite: int
    ) -> None:
        numero = (extrato.get("dados_basicos") or {}).get("numero") or (
            extrato.get("origem") or {}
        ).get("entrada", "")
        if numero:
            esaj.preparar_documentos(
                self.session, numero, movimentos, limite, timeout=self.config.timeout
            )

    def baixar_pecas(
        self,
        extrato: dict[str, Any],
        destino: Path,
        sobrescrever: bool = False,
        limite: int = 0,
        max_bytes: int = esaj.MAX_DOCUMENT_DOWNLOAD_BYTES,
    ) -> list[dict[str, Any]]:
        movimentos = []
        documentos = extrato.get("documentos", {}).get("publicos_candidatos_unicos", [])
        if documentos:
            movimentos = [{"documentos": documentos}]
        else:
            movimentos = extrato.get("movimentacoes", [])
        self._preparar_documentos(extrato, movimentos, limite)
        return esaj.baixar_pecas_publicas(
            self.session,
            movimentos,
            destino,
            limite=limite,
            sobrescrever=sobrescrever,
            max_bytes=max_bytes,
            timeout=self.config.timeout,
        )

    def obter_pdf_esaj(
        self,
        numero: str,
        cd_documento: str,
        *,
        max_bytes: int = esaj.MAX_IN_MEMORY_DOCUMENT_BYTES,
        senha_processo: str | None = None,
    ) -> bytes:
        """Obtém bytes de uma peça e-SAJ listada como acessível nesta sessão."""
        numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
        if not eh_tjsp(numero_cnj):
            raise ValueError("obter_pdf_esaj aceita apenas processos do TJSP.")
        documento_id = str(cd_documento).strip()
        if not documento_id or len(documento_id) > 128:
            raise ValueError("cd_documento deve conter de 1 a 128 caracteres.")
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or not 1 <= max_bytes <= esaj.MAX_DOCUMENT_DOWNLOAD_BYTES
        ):
            raise ValueError(f"max_bytes deve estar entre 1 e {esaj.MAX_DOCUMENT_DOWNLOAD_BYTES}.")

        extrato = self._extratos.get(numero_cnj)
        if (
            senha_processo is not None
            or extrato is None
            or (extrato.get("origem") or {}).get("movimentacoes_completas") is not True
        ):
            extrato = self.get_extrato(
                numero_cnj,
                limite_movimentacoes=None,
                senha_processo=senha_processo,
            )
        documentos = extrato.get("documentos") or {}
        candidatos = documentos.get("publicos_candidatos_unicos") or []
        selecionados = [
            doc for doc in candidatos if str(doc.get("cd_documento") or "") == documento_id
        ]
        if not selecionados:
            restritos = documentos.get("restritos_por_senha_unicos") or []
            if any(str(doc.get("cd_documento") or "") == documento_id for doc in restritos):
                raise AcessoRestrito(
                    "O e-SAJ marcou o documento como restrito; use uma sessão "
                    "e autorização válidas."
                )
            raise DocumentoNaoEncontrado(
                "O e-SAJ não listou esse documento entre as peças acessíveis do processo."
            )

        extrato_download = deepcopy(cast(dict[str, Any], extrato))
        documentos_download = extrato_download.setdefault("documentos", {})
        documentos_download["publicos_candidatos_unicos"] = [
            doc
            for doc in documentos_download.get("publicos_candidatos_unicos", [])
            if str(doc.get("cd_documento") or "") == documento_id
        ]
        with TemporaryDirectory(prefix="nanojud_esaj_pdf_") as temporario:
            baixados = self.baixar_pecas(
                extrato_download,
                Path(temporario),
                limite=1,
                max_bytes=max_bytes,
            )
            if not baixados:
                status = str(
                    documentos_download["publicos_candidatos_unicos"][0].get("download_status", "")
                )
                if status in {"sessao_expirada", "restrito_por_senha"}:
                    raise AcessoRestrito(
                        "O e-SAJ recusou o acesso ao documento nesta sessão ou autorização."
                    )
                if status == "documento_muito_grande":
                    raise DownloadIndisponivel(
                        f"O documento excede o limite de {max_bytes} bytes solicitado."
                    )
                raise DownloadIndisponivel(
                    "O e-SAJ não conseguiu disponibilizar o documento "
                    f"(status: {status or 'erro'})."
                )
            conteudo = Path(baixados[0]["arquivo"]).read_bytes()

        if len(conteudo) > max_bytes or not conteudo.startswith(b"%PDF"):
            raise DownloadIndisponivel("O e-SAJ não retornou um PDF válido dentro do limite.")
        return conteudo

    def ler_pecas(
        self,
        extrato: dict[str, Any],
        limite: int = 3,
        max_chars: int = 4000,
        *,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """Le pecas publicas candidatas em memoria, sem salvar PDFs em disco."""
        documentos = extrato.get("documentos", {}).get("publicos_candidatos_unicos", [])
        movimentos = (
            [{"documentos": documentos}] if documentos else extrato.get("movimentacoes", [])
        )
        self._preparar_documentos(extrato, movimentos, limite)
        return esaj.ler_pecas_publicas(
            self.session,
            movimentos,
            limite=limite,
            max_chars=max_chars,
            timeout=self.config.timeout if timeout is None else timeout,
        )
