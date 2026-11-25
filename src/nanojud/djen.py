"""Cliente DJEN para comunicacoes e publicacoes."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from .exceptions import AcessoRestrito, ConsultaIndisponivel, FormatoCNJInvalido
from .utils import validar_inteiro, validar_numero_cnj, validar_timeout

API_BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
CNJ_ITEM_RE = re.compile(r"(?<!\d)(?:\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d{20})(?!\d)")
PAGE_SIZE = 100
MAX_PAGES = 100
RETRY = 3
BACKOFF = 1.0
MAX_RETRY_AFTER_SECONDS = 60


def _parse_data(item: dict[str, Any]) -> str:
    raw = item.get("data_disponibilizacao", "")
    if raw and str(raw)[:4].isdigit():
        return str(raw)[:10]
    data_br = item.get("datadisponibilizacao", "")
    if data_br and "/" in str(data_br):
        partes = str(data_br).split("/")
        if len(partes) == 3:
            return f"{partes[2]}-{partes[1]}-{partes[0]}"
    return ""


def _extrair_items(data: Any) -> list[dict[str, Any]]:
    items = data
    if isinstance(data, dict):
        items = next(
            (
                data[key]
                for key in ("items", "content", "comunicacoes", "resultado")
                if isinstance(data.get(key), list)
            ),
            None,
        )
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ConsultaIndisponivel("DJEN retornou JSON com estrutura inesperada.")
    return items


def _incidente(texto: str) -> str:
    """Sufixo do incidente (ex.: /47) quando a comunicação é de um incidente do processo."""
    match = re.match(r"\s*Processo\s+\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}/(\d+)", texto)
    return match.group(1) if match else ""


def _normalizar_item(item: dict[str, Any]) -> dict[str, Any]:
    texto = str(item.get("texto", ""))
    return {
        "id": item.get("id", ""),
        "fonte": "djen",
        "tipoComunicacao": item.get("tipoComunicacao", item.get("tipoDocumento", "")),
        "nomeOrgao": item.get("nomeOrgao", ""),
        "dataDisponibilizacao": _parse_data(item),
        "siglaTribunal": item.get("siglaTribunal", ""),
        "nomeClasse": item.get("nomeClasse", ""),
        "texto": texto,
        "numero_processo": str(
            item.get("numeroprocessocommascara") or item.get("numero_processo") or ""
        ),
        "incidente": _incidente(texto),
        "numero_comunicacao": item.get("numeroComunicacao", ""),
        "hash": item.get("hash", ""),
        "status": item.get("status", ""),
        # Ausencia do campo nao comprova atividade; preserve o desconhecido.
        "ativo": item.get("ativo"),
        "data_cancelamento": item.get("data_cancelamento", ""),
        "motivo_cancelamento": item.get("motivo_cancelamento", ""),
        "advogados": item.get("destinatarioadvogados", []),
        "destinatarios": item.get("destinatarios", []),
        "link": item.get("link", ""),
        "meio": item.get("meio", ""),
    }


def _identidade_item(item: dict[str, Any]) -> str:
    """Retorna o CNJ explicitamente associado à comunicação, se for verificável."""
    raw = (
        item.get("numeroprocessocommascara")
        or item.get("numero_processo")
        or item.get("numeroProcesso")
    )
    if raw is None:
        return ""
    match = CNJ_ITEM_RE.search(str(raw))
    if match is None:
        return ""
    try:
        return validar_numero_cnj(match.group(), segmento=None, tribunal=None)
    except FormatoCNJInvalido:
        return ""


def _retry_after_seconds(response: Any) -> float | None:
    """Interpreta Retry-After como segundos ou data HTTP."""
    headers = getattr(response, "headers", {})
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if raw is None:
        return None
    valor = str(raw).strip()
    try:
        segundos = int(valor)
    except ValueError:
        try:
            data_retentativa = parsedate_to_datetime(valor)
        except (TypeError, ValueError, OverflowError):
            return None
        if data_retentativa.tzinfo is None:
            data_retentativa = data_retentativa.replace(tzinfo=UTC)
        return max(0.0, (data_retentativa - datetime.now(UTC)).total_seconds())
    return float(segundos) if segundos >= 0 else None


def consultar_processo_detalhado(
    numero: str,
    data_inicio: str = "",
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
    retry: int = RETRY,
    backoff: float = BACKOFF,
    total_timeout: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Consulta comunicações do DJEN com estado de completude da paginação."""
    numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
    timeout = validar_timeout(timeout)
    total_timeout = validar_timeout(total_timeout, nome="total_timeout")
    for nome, valor in (("page_size", page_size), ("max_pages", max_pages), ("retry", retry)):
        validar_inteiro(valor, nome=nome, minimo=1)
    if page_size not in (5, 100):
        raise ValueError("page_size deve ser 5 ou 100, conforme a API do DJEN")
    session = session or requests.Session()
    resultados: list[dict[str, Any]] = []
    ids_vistos = set()
    paginas = 0
    completo = False
    avisos: list[str] = []
    params: dict[str, Any] = {"numeroProcesso": numero, "itensPorPagina": page_size}
    if data_inicio:
        params["dataInicio"] = data_inicio
    deadline = monotonic() + total_timeout

    def falha(error: ConsultaIndisponivel | AcessoRestrito) -> dict[str, Any]:
        if paginas == 0:
            raise error
        avisos.append(str(error))
        return {
            "status": "partial",
            "completo": False,
            "paginas": paginas,
            "comunicacoes": resultados,
            "avisos": avisos,
        }

    def esperar(segundos: float) -> bool:
        if segundos >= deadline - monotonic():
            return False
        sleep(segundos)
        return True

    for page in range(1, max_pages + 1):
        params["pagina"] = page
        response = None
        for tentativa in range(retry):
            restante = deadline - monotonic()
            if restante <= 0:
                return falha(ConsultaIndisponivel("DJEN atingiu o limite de tempo total."))
            try:
                response = session.get(API_BASE, params=params, timeout=min(timeout, restante))
            except requests.RequestException as exc:
                if tentativa + 1 >= retry:
                    return falha(
                        ConsultaIndisponivel(
                            f"Falha de comunicação com DJEN ({type(exc).__name__})."
                        )
                    )
                if not esperar(backoff * (tentativa + 1)):
                    return falha(ConsultaIndisponivel("DJEN atingiu o limite de tempo total."))
                continue

            if response.status_code == 200:
                break
            if response.status_code == 429 and tentativa + 1 < retry:
                espera = _retry_after_seconds(response)
                if espera is None:
                    espera = backoff * (tentativa + 1)
                if espera > MAX_RETRY_AFTER_SECONDS:
                    return falha(
                        ConsultaIndisponivel(
                            "DJEN solicitou aguardar mais de 60 segundos via Retry-After; "
                            "a consulta foi encerrada sem repetir a chamada."
                        )
                    )
                if not esperar(espera):
                    return falha(ConsultaIndisponivel("DJEN atingiu o limite de tempo total."))
                continue
            if response.status_code == 403:
                return falha(
                    AcessoRestrito("DJEN retornou HTTP 403. Pode haver bloqueio geográfico.")
                )
            return falha(ConsultaIndisponivel(f"DJEN retornou HTTP {response.status_code}."))

        if response is None or response.status_code != 200:
            break

        try:
            data = response.json()
        except ValueError:
            return falha(ConsultaIndisponivel("DJEN retornou JSON inválido."))

        try:
            items = _extrair_items(data)
        except ConsultaIndisponivel as exc:
            return falha(exc)
        paginas += 1
        if not items:
            completo = True
            break

        novos = 0
        identidade_invalida = False
        for item in items:
            if _identidade_item(item) != numero:
                identidade_invalida = True
                continue
            item_id = str(item.get("id", ""))
            if item_id and item_id in ids_vistos:
                continue
            if item_id:
                ids_vistos.add(item_id)
            novos += 1
            resultados.append(_normalizar_item(item))

        if identidade_invalida:
            avisos.append(
                "DJEN retornou comunicação sem identidade verificável ou de outro processo; "
                "o item foi ignorado e o resultado permanece parcial."
            )
            break

        if novos == 0:
            avisos.append("DJEN repetiu uma página sem novas comunicações; o resultado é parcial.")
            break
        if len(items) < page_size:
            completo = True
            break
        if not esperar(0.2):
            return falha(ConsultaIndisponivel("DJEN atingiu o limite de tempo total."))
    else:
        avisos.append(
            f"DJEN atingiu o limite de {max_pages} páginas; o resultado pode estar incompleto."
        )

    return {
        "status": "ok" if completo else "partial",
        "completo": completo,
        "paginas": paginas,
        "comunicacoes": resultados,
        "avisos": avisos,
    }


def consultar_processo(
    numero: str,
    data_inicio: str = "",
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
    retry: int = RETRY,
    backoff: float = BACKOFF,
    total_timeout: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> list[dict[str, Any]]:
    """Consulta comunicações do DJEN; use a variante detalhada para completude."""
    return consultar_processo_detalhado(
        numero,
        data_inicio,
        session=session,
        timeout=timeout,
        page_size=page_size,
        max_pages=max_pages,
        retry=retry,
        backoff=backoff,
        total_timeout=total_timeout,
        sleep=sleep,
        monotonic=monotonic,
    )["comunicacoes"]
