"""Orquestracao leve de extracao, sem interpretacao juridica."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import requests

from . import datajud, djen, eproc_tjsp, esaj, esaj_tjsp_2g, pje_tjmg, tjrj
from .divergencias import detectar_divergencias
from .exceptions import ConsultaIndisponivel, mensagem_erro_segura
from .mni import MNI3Client
from .mni_222 import MNI222Client, MNI222Config, MNIConfig, configuracao_mni_desde_env
from .schemas import (
    SCHEMA_VERSION,
    ExtractionEnvelope,
    ExtractionError,
    ExtractionStatus,
    SourceStatus,
)
from .sources import (
    ALL_SOURCES,
    DATAJUD,
    DJEN,
    EPROC_TJSP_1G,
    EPROC_TJSP_2G,
    ESAJ,
    ESAJ_TJSP_2G,
    MNI,
    PJE_TJMG,
    TJRJ_1G,
    normalizar_fontes,
)
from .timeline import build_timeline
from .utils import eh_tjsp, validar_numero_cnj, validar_prazo_total, validar_timeout
from .version import __version__

PRAZO_TOTAL = 60.0
_PJE_RESULT_MARGIN = 0.5
MAX_SOURCE_WORKERS = 32
_SOURCE_EXECUTOR = ThreadPoolExecutor(
    max_workers=MAX_SOURCE_WORKERS, thread_name_prefix="nanojud-source"
)
_SOURCE_CAPACITY = threading.BoundedSemaphore(MAX_SOURCE_WORKERS)


def _executar_fonte(tarefa: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Libera a vaga global mesmo quando uma tarefa de fonte falha."""
    try:
        return tarefa()
    finally:
        _SOURCE_CAPACITY.release()


def extract_process(
    numero: str,
    *,
    sources: list[str] | tuple[str, ...] = ALL_SOURCES,
    include_raw: bool = False,
    datajud_api_key: str | None = None,
    djen_data_inicio: str = "",
    session: requests.Session | None = None,
    timeout: float = 30.0,
    datajud_retry: int = 3,
    limite_movimentacoes: int | None = esaj.LIMITE_MOVIMENTACOES,
    desde: str = "",
    prazo_total: float | None = PRAZO_TOTAL,
    mni_config: MNIConfig | None = None,
) -> ExtractionEnvelope:
    """Extrai dados de uma ou mais fontes e retorna envelope versionado.

    As fontes rodam em paralelo; ``prazo_total`` (segundos) limita a espera e uma fonte
    que estoura o prazo vira erro isolado, sem perder as demais. ``desde`` (YYYY-MM-DD)
    restringe movimentações e comunicações e reduz a paginação do eSAJ.
    """
    validar_timeout(timeout)
    validar_prazo_total(prazo_total)
    prazo_final = time.monotonic() + prazo_total if prazo_total is not None else None
    if isinstance(datajud_retry, bool) or not isinstance(datajud_retry, int) or datajud_retry < 1:
        raise ValueError("datajud_retry deve ser pelo menos 1.")
    numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
    fontes = list(normalizar_fontes(sources))
    data: dict[str, Any] = {}
    raw: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[ExtractionError] = []
    source_status: dict[str, SourceStatus] = {}

    def _esaj() -> dict[str, Any]:
        extrato = esaj.montar_extrato(
            numero_cnj,
            salvar_html=include_raw,
            session=session,
            timeout=timeout,
            limite_movimentacoes=limite_movimentacoes,
            desde=desde,
        )
        origem = extrato.get("origem") or {}
        movimentacoes_completas = origem.get("movimentacoes_completas") is True
        aviso = origem.get("aviso_movimentacoes")
        avisos = []
        if not movimentacoes_completas:
            avisos.append(
                f"eSAJ: {aviso}"
                if aviso
                else "eSAJ: a completude das movimentações não foi confirmada."
            )
        return {
            "data": extrato,
            "status": {
                "status": "ok" if movimentacoes_completas else "partial",
                "records": len(extrato.get("movimentacoes") or []),
            },
            "warnings": avisos,
            "raw": origem.get("html_bruto") if include_raw else None,
        }

    def _datajud() -> dict[str, Any]:
        prazo_datajud = None if prazo_final is None else max(0.0, prazo_final - time.monotonic())
        extracao = datajud.consultar_processo(
            numero_cnj,
            api_key=datajud_api_key,
            include_raw=include_raw,
            session=session,
            timeout=timeout,
            retry=datajud_retry,
            prazo_total=prazo_datajud,
        )
        if desde and extracao.get("movimentos"):
            extracao["movimentos"] = [
                m for m in extracao["movimentos"] if (m.get("data") or desde) >= desde
            ]
        status = str(extracao.get("status") or "ok")
        avisos = list(extracao.get("warnings") or [])
        if status == "nao_encontrado":
            avisos.append("DataJud/CNJ consultado, mas nao retornou processo para o CNJ informado.")
        return {
            "data": extracao,
            "status": {"status": status, "records": len(extracao.get("movimentos") or [])},
            "warnings": avisos,
            "raw": extracao.get("raw") if include_raw else None,
        }

    def _djen() -> dict[str, Any]:
        resultado_djen = djen.consultar_processo_detalhado(
            numero_cnj,
            data_inicio=djen_data_inicio or desde,
            session=session,
            timeout=timeout,
        )
        comunicacoes = resultado_djen["comunicacoes"]
        texto_corrompido = sum(
            1
            for comunicacao in comunicacoes
            if any(
                "\ufffd" in str(comunicacao.get(campo) or "")
                for campo in ("tipoComunicacao", "nomeOrgao", "texto")
            )
        )
        avisos = list(resultado_djen["avisos"])
        if texto_corrompido:
            avisos.append(
                f"DJEN: {texto_corrompido} comunicação(ões) contém caracteres de texto "
                "substituídos pela própria fonte; confira o teor no diário oficial."
            )
        return {
            "data": comunicacoes,
            "status": {
                "status": (
                    "partial" if resultado_djen["status"] != "ok" or texto_corrompido else "ok"
                ),
                "records": len(comunicacoes),
                "pages": resultado_djen["paginas"],
                "records_complete": resultado_djen["completo"],
            },
            "warnings": avisos,
            "raw": None,
        }

    def _pje_tjmg() -> dict[str, Any]:
        prazo_pje = (
            None
            if prazo_final is None
            else max(0.0, prazo_final - time.monotonic() - _PJE_RESULT_MARGIN)
        )
        extrato = pje_tjmg.consultar_processo(
            numero_cnj, session=session, timeout=timeout, prazo_total=prazo_pje
        )
        origem = extrato.get("origem") or {}
        avisos = [
            str(origem[key])
            for key in ("aviso_movimentacoes", "aviso_documentos")
            if origem.get(key)
        ]
        return {
            "data": extrato,
            "status": {
                "status": "partial" if extrato.get("status") == "partial" else "ok",
                "records": len(extrato.get("movimentacoes") or []),
            },
            "warnings": avisos,
            "raw": None,
        }

    def _cposg() -> dict[str, Any]:
        extrato = esaj_tjsp_2g.consultar_processo(numero_cnj, timeout=timeout)
        resultados = extrato["resultados"]
        avisos = [f"CPoSG: {aviso}" for aviso in extrato["avisos"]]
        if extrato["status"] == "partial":
            avisos.append("CPoSG: confira os avisos e erros por resultado de segundo grau.")
        status = "error" if extrato["status"] == "erro" else extrato["status"]
        falha: ExtractionError | None = None
        if status == "error":
            falha = {
                "source": ESAJ_TJSP_2G,
                "message": "Nenhuma capa do CPoSG foi confirmada.",
                "type": "ConsultaInconclusiva",
            }
        return {
            "data": extrato,
            "status": {
                "status": status,
                "records": sum(len(item.get("movimentacoes", [])) for item in resultados),
            },
            "warnings": avisos,
            "error": falha,
            "raw": None,
        }

    def _eproc_tjsp_1g() -> dict[str, Any]:
        extrato = eproc_tjsp.consultar_processo(numero_cnj, timeout=timeout)
        completo = (extrato.get("origem") or {}).get("movimentacoes_completas") is True
        return {
            "data": extrato,
            "status": {
                "status": "ok" if completo else "partial",
                "records": len(extrato.get("movimentacoes") or []),
            },
            "warnings": []
            if completo
            else ["eproc/TJSP 1G: a completude do histórico não foi confirmada."],
            "raw": None,
        }

    def _eproc_tjsp_2g() -> dict[str, Any]:
        extrato = eproc_tjsp.consultar_processo_2g(numero_cnj, timeout=timeout)
        completo = (extrato.get("origem") or {}).get("movimentacoes_completas") is True
        return {
            "data": extrato,
            "status": {
                "status": "ok" if completo else "partial",
                "records": len(extrato.get("movimentacoes") or []),
            },
            "warnings": [] if completo else ["eproc/TJSP 2G: o histórico pode estar incompleto."],
            "raw": None,
        }

    def _mni() -> dict[str, Any]:
        config = mni_config or configuracao_mni_desde_env()
        if config is None:
            raise ConsultaIndisponivel(
                "A fonte MNI foi selecionada, mas não há instalação configurada. "
                "Informe mni_config ou configure as variáveis NANOJUD_MNI_* do endpoint "
                "e da credencial fornecida pelo tribunal."
            )
        config = replace(config, timeout=min(timeout, config.timeout))
        if isinstance(config, MNI222Config):
            with MNI222Client(config) as cliente:
                extrato = cliente.consultar_extrato(numero_cnj)
        else:
            with MNI3Client(config) as cliente:
                extrato = cliente.consultar_extrato(numero_cnj)
        origem = extrato.get("origem") or {}
        avisos = [
            str(origem[chave])
            for chave in ("aviso_movimentacoes", "aviso_documentos")
            if origem.get(chave)
        ]
        return {
            "data": extrato,
            "status": {
                "status": "partial" if extrato.get("status") == "partial" else "ok",
                "records": len(extrato.get("movimentacoes") or []),
            },
            "warnings": avisos,
            "raw": None,
        }

    def _tjrj_1g() -> dict[str, Any]:
        extrato = tjrj.consultar_processo(numero_cnj, session=session, timeout=timeout)
        origem = extrato.get("origem") or {}
        completo = origem.get("movimentacoes_completas") is True
        aviso = origem.get("aviso_movimentacoes")
        return {
            "data": extrato,
            "status": {
                "status": "ok" if completo else "partial",
                "records": len(extrato.get("movimentacoes") or []),
            },
            "warnings": [str(aviso)] if aviso else [],
            "raw": None,
        }

    tarefas = {
        ESAJ: _esaj,
        DATAJUD: _datajud,
        DJEN: _djen,
        PJE_TJMG: _pje_tjmg,
        ESAJ_TJSP_2G: _cposg,
        EPROC_TJSP_1G: _eproc_tjsp_1g,
        EPROC_TJSP_2G: _eproc_tjsp_2g,
        MNI: _mni,
        TJRJ_1G: _tjrj_1g,
    }
    selecionadas = {}
    for fonte in fontes:
        if fonte in (ESAJ, ESAJ_TJSP_2G) and not eh_tjsp(numero_cnj):
            source_status[fonte] = {"status": "nao_aplicavel", "message": "eSAJ cobre só o TJSP."}
        elif fonte == PJE_TJMG and numero_cnj.split(".")[2:4] != ["8", "13"]:
            source_status[PJE_TJMG] = {
                "status": "nao_aplicavel",
                "message": "PJe/TJMG cobre apenas processos estaduais de Minas Gerais.",
            }
        elif fonte == TJRJ_1G and numero_cnj.split(".")[2:4] != ["8", "19"]:
            source_status[fonte] = {
                "status": "nao_aplicavel",
                "message": "TJRJ cobre apenas processos estaduais do Rio de Janeiro.",
            }
        elif fonte == EPROC_TJSP_1G and numero_cnj.split(".")[2:4] != ["8", "26"]:
            source_status[fonte] = {
                "status": "nao_aplicavel",
                "message": "eproc/TJSP 1G cobre apenas processos estaduais de São Paulo.",
            }
        elif fonte == EPROC_TJSP_2G and numero_cnj.split(".")[2:4] != ["8", "26"]:
            source_status[fonte] = {
                "status": "nao_aplicavel",
                "message": "eproc/TJSP 2G cobre apenas processos estaduais de São Paulo.",
            }
        else:
            selecionadas[fonte] = tarefas[fonte]

    resultados: dict[str, Any] = {}
    if selecionadas:
        futuros: dict[Future[dict[str, Any]], str] = {}
        for fonte, tarefa in selecionadas.items():
            restante = None if prazo_final is None else max(0.0, prazo_final - time.monotonic())
            vaga_livre = (
                _SOURCE_CAPACITY.acquire()
                if restante is None
                else _SOURCE_CAPACITY.acquire(timeout=restante)
            )
            if not vaga_livre:
                resultados[fonte] = TimeoutError(f"Fonte excedeu o prazo total de {prazo_total}s.")
                continue
            try:
                futuro = _SOURCE_EXECUTOR.submit(_executar_fonte, tarefa)
            except Exception as exc:  # noqa: BLE001 - falha de agendamento isolada por fonte
                _SOURCE_CAPACITY.release()
                resultados[fonte] = exc
                continue
            futuros[futuro] = fonte

        restante = None if prazo_final is None else max(0.0, prazo_final - time.monotonic())
        _, pendentes = wait(futuros, timeout=restante)
        for futuro, fonte_nome in futuros.items():
            if futuro in pendentes:
                if futuro.cancel():
                    _SOURCE_CAPACITY.release()
                resultados[fonte_nome] = TimeoutError(
                    f"Fonte excedeu o prazo total de {prazo_total}s."
                )
            else:
                try:
                    resultados[fonte_nome] = futuro.result()
                except Exception as exc:  # noqa: BLE001 - envelope preserva falha isolada
                    resultados[fonte_nome] = exc

    for fonte in fontes:  # ordem estável, independente de quem terminou primeiro
        resultado = resultados.get(fonte)
        if resultado is None:
            continue
        if isinstance(resultado, Exception):
            errors.append(
                {
                    "source": fonte,
                    "message": mensagem_erro_segura(resultado),
                    "type": type(resultado).__name__,
                }
            )
            source_status[fonte] = {
                "status": "error",
                "message": mensagem_erro_segura(resultado),
                "type": type(resultado).__name__,
            }
            continue
        data[fonte] = resultado["data"]
        source_status[fonte] = resultado["status"]
        falha = resultado.get("error")
        if falha:
            errors.append(falha)
            source_status[fonte]["message"] = falha["message"]
            source_status[fonte]["type"] = falha["type"]
        warnings.extend(resultado["warnings"])
        if resultado["raw"]:
            raw[fonte] = resultado["raw"]

    timeline = build_timeline(
        esaj_extrato=data.get(ESAJ),
        datajud_extracao=data.get(DATAJUD),
        djen_comunicacoes=data.get(DJEN),
        pje_tjmg_extracao=data.get(PJE_TJMG),
        cposg_extracao=data.get(ESAJ_TJSP_2G),
        eproc_tjsp_1g_extracao=data.get(EPROC_TJSP_1G),
        eproc_tjsp_2g_extracao=data.get(EPROC_TJSP_2G),
        mni_extracao=data.get(MNI),
        tjrj_extracao=data.get(TJRJ_1G),
        include_payload=include_raw,
    )
    if desde:
        timeline = [r for r in timeline if (r.get("data") or desde) >= desde]
    if not any(source_status[fonte]["status"] != "error" for fonte in data):
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
        "extracted_at": datetime.now(UTC).isoformat(),
        "data": data,
        "timeline": timeline,
        "warnings": warnings,
        "errors": errors,
        "source_status": source_status,
        "divergencias": cast(list[dict[str, Any]], detectar_divergencias(data)),
    }
    if include_raw:
        envelope["raw"] = raw
    return envelope
