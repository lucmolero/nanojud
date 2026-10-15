"""Cliente DJEN para comunicacoes e publicacoes."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

import requests

from .exceptions import AcessoRestrito, ConsultaIndisponivel
from .utils import validar_numero_cnj

API_BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
PAGE_SIZE = 20
MAX_PAGES = 50
RETRY = 3
BACKOFF = 1.0


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
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "content", "comunicacoes", "resultado"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _incidente(texto: str) -> str:
    """Sufixo do incidente (ex.: /47) quando a comunicação é de um incidente do processo."""
    match = re.match(r"\s*Processo\s+\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}/(\d+)", texto)
    return match.group(1) if match else ""


def _normalizar_item(item: dict[str, Any]) -> dict[str, Any]:
    texto = str(item.get("texto", ""))
    return {
        "id": item.get("id", ""),
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
        "ativo": item.get("ativo", True),
        "data_cancelamento": item.get("data_cancelamento", ""),
        "motivo_cancelamento": item.get("motivo_cancelamento", ""),
        "advogados": item.get("destinatarioadvogados", []),
        "destinatarios": item.get("destinatarios", []),
        "link": item.get("link", ""),
        "meio": item.get("meio", ""),
    }


def consultar_processo(
    numero: str,
    data_inicio: str = "",
    *,
    session: requests.Session | None = None,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
    retry: int = RETRY,
    backoff: float = BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Consulta comunicações do DJEN para um processo CNJ."""
    numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
    session = session or requests.Session()
    resultados: list[dict[str, Any]] = []
    ids_vistos = set()
    params: dict[str, Any] = {"numeroProcesso": numero, "size": page_size, "page": 1}
    if data_inicio:
        params["dataInicio"] = data_inicio

    for page in range(1, max_pages + 1):
        params["page"] = page
        response = None
        for tentativa in range(retry):
            try:
                response = session.get(API_BASE, params=params, timeout=30)
            except requests.RequestException as exc:
                if tentativa + 1 >= retry:
                    raise ConsultaIndisponivel(f"Falha de comunicação com DJEN: {exc}") from exc
                sleep(backoff * (tentativa + 1))
                continue

            if response.status_code == 200:
                break
            if response.status_code == 429 and tentativa + 1 < retry:
                sleep(backoff * (tentativa + 1))
                continue
            if response.status_code == 403:
                raise AcessoRestrito("DJEN retornou HTTP 403. Pode haver bloqueio geográfico.")
            raise ConsultaIndisponivel(f"DJEN retornou HTTP {response.status_code}.")

        if response is None or response.status_code != 200:
            break

        try:
            data = response.json()
        except ValueError as exc:
            raise ConsultaIndisponivel("DJEN retornou JSON inválido.") from exc

        items = _extrair_items(data)
        if not items:
            break

        novos = 0
        for item in items:
            item_id = str(item.get("id", ""))
            if item_id and item_id in ids_vistos:
                continue
            if item_id:
                ids_vistos.add(item_id)
            novos += 1
            resultados.append(_normalizar_item(item))

        if novos == 0 or len(items) < page_size:
            break
        sleep(0.2)
    return resultados
