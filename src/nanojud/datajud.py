"""Cliente DataJud/CNJ para dados processuais estruturados."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast

import requests

from .exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado
from .models import ResumoProcesso
from .normalization import normalizar_data, somente_digitos
from .schemas import DataJudExtraction
from .sources import DATAJUD
from .utils import validar_numero_cnj

API_TEMPLATE = "https://api-publica.datajud.cnj.jus.br/api_publica_{indice}/_search"
DATAJUD_WIKI_ACESSO_URL = "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
PUBLIC_DATAJUD_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
# O DataJud indexa um registro por grau (G1, TR, G2...) para o mesmo numero CNJ.
MAX_REGISTROS = 10
ORDEM_GRAUS = ("G1", "JE", "TR", "G2", "SUP")
DEFAULT_SOURCE_FIELDS = [
    "numeroProcesso",
    "classe",
    "sistema",
    "formato",
    "tribunal",
    "grau",
    "dataAjuizamento",
    "orgaoJulgador",
    "assuntos",
    "movimentos",
    "partes",
]

INDICES_JUSTICA_ESTADUAL = {
    "01": "tjac",
    "02": "tjal",
    "03": "tjap",
    "04": "tjam",
    "05": "tjba",
    "06": "tjce",
    "07": "tjdft",
    "08": "tjes",
    "09": "tjgo",
    "10": "tjma",
    "11": "tjmt",
    "12": "tjms",
    "13": "tjmg",
    "14": "tjpa",
    "15": "tjpb",
    "16": "tjpr",
    "17": "tjpe",
    "18": "tjpi",
    "19": "tjrj",
    "20": "tjrn",
    "21": "tjrs",
    "22": "tjro",
    "23": "tjrr",
    "24": "tjsc",
    "25": "tjse",
    "26": "tjsp",
    "27": "tjto",
}


def indice_datajud(numero: str) -> str:
    """Retorna o indice DataJud inferido do numero CNJ, quando suportado."""
    numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
    match = re.match(r"^\d{7}-\d{2}\.\d{4}\.(\d)\.(\d{2})\.\d{4}$", numero)
    if not match:
        return ""
    segmento, tribunal = match.groups()
    if segmento == "8":
        return INDICES_JUSTICA_ESTADUAL.get(tribunal, "")
    if segmento == "4":
        return f"trf{int(tribunal)}"
    if segmento == "5":
        return f"trt{int(tribunal)}"
    if segmento == "2":
        return "stj"
    return ""


def datajud_api_key(api_key: str | None = None) -> str:
    """Resolve API key do DataJud.

    Ordem de precedencia:
    1. valor explicito;
    2. variaveis de ambiente;
    3. chave publica vigente documentada na Wiki oficial do DataJud/CNJ.

    A chave publica pode ser rotacionada pelo CNJ. Em caso de falha de autenticacao,
    informe uma chave atualizada por argumento ou variavel de ambiente.
    """
    chave = (
        api_key
        or os.getenv("NANOJUD_DATAJUD_API_KEY")
        or os.getenv("DATAJUD_API_KEY")
        or os.getenv("CNJ_DATAJUD_API_KEY")
        or PUBLIC_DATAJUD_API_KEY
    ).strip()
    return chave if chave.startswith("APIKey ") else f"APIKey {chave}"


def consultar_processo(
    numero: str,
    *,
    api_key: str | None = None,
    indice: str | None = None,
    include_raw: bool = False,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    retry: int = 3,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> DataJudExtraction:
    """Consulta um processo na API publica do DataJud/CNJ."""
    numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
    indice_resolvido = indice or indice_datajud(numero)
    if not indice_resolvido:
        raise ConsultaIndisponivel("Nao ha indice DataJud mapeado para o numero CNJ informado.")

    url = API_TEMPLATE.format(indice=indice_resolvido)
    payload: dict[str, Any] = {
        "query": {"match": {"numeroProcesso": somente_digitos(numero)}},
        "size": MAX_REGISTROS,
        "_source": DEFAULT_SOURCE_FIELDS,
    }
    headers = {
        "Authorization": datajud_api_key(api_key),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    session = session or requests.Session()

    response: requests.Response | None = None
    for tentativa in range(retry):
        try:
            response = session.post(url, json=cast(Any, payload), headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            if tentativa + 1 >= retry:
                raise ConsultaIndisponivel(f"Falha de comunicacao com DataJud: {exc}") from exc
            sleep(backoff * (tentativa + 1))
            continue

        if response.status_code == 200:
            break
        if response.status_code == 429 and tentativa + 1 < retry:
            sleep(backoff * (tentativa + 1))
            continue
        if response.status_code in {401, 403}:
            raise AcessoRestrito(f"DataJud retornou HTTP {response.status_code}.")
        raise ConsultaIndisponivel(f"DataJud retornou HTTP {response.status_code}.")

    if response is None or response.status_code != 200:
        raise ConsultaIndisponivel("DataJud nao retornou resposta valida.")

    try:
        body = response.json()
    except ValueError as exc:
        raise ConsultaIndisponivel("DataJud retornou JSON invalido.") from exc

    hits = ((body.get("hits") or {}).get("hits") or []) if isinstance(body, dict) else []
    extracted_at = datetime.now(timezone.utc).isoformat()
    if not hits:
        return {
            "status": "nao_encontrado",
            "numero_cnj": numero,
            "indice": indice_resolvido,
            "metadata": {
                "source": DATAJUD,
                "source_url": url,
                "extracted_at": extracted_at,
                "raw_available": include_raw,
            },
            **({"raw": body} if include_raw else {}),
        }

    sources = sorted(
        (hit.get("_source") or {} for hit in hits),
        key=lambda item: _rank_grau(str(item.get("grau") or "")),
    )
    return _normalizar_source(
        sources,
        numero=numero,
        indice=indice_resolvido,
        source_url=url,
        extracted_at=extracted_at,
        raw=body if include_raw else None,
    )


def _rank_grau(grau: str) -> int:
    return ORDEM_GRAUS.index(grau) if grau in ORDEM_GRAUS else len(ORDEM_GRAUS)


def _normalizar_source(
    sources: list[dict[str, Any]],
    *,
    numero: str,
    indice: str,
    source_url: str,
    extracted_at: str,
    raw: dict[str, Any] | None,
) -> DataJudExtraction:
    """Consolida os registros por grau; o primeiro (menor grau) define os dados principais."""
    source = sources[0]
    classe_raw = source.get("classe")
    orgao_raw = source.get("orgaoJulgador")
    classe = classe_raw if isinstance(classe_raw, dict) else {}
    orgao = orgao_raw if isinstance(orgao_raw, dict) else {}
    movimentos = [
        {**_normalizar_movimento(mov), "grau": str(item.get("grau") or "")}
        for item in sources
        for mov in item.get("movimentos") or []
    ]
    movimentos.sort(key=lambda mov: (not mov["data_hora"], mov["data_hora"]))
    partes = [_normalizar_parte(parte) for parte in source.get("partes") or []]
    saida: DataJudExtraction = {
        "status": "ok",
        "numero_cnj": numero,
        "tribunal": str(source.get("tribunal") or ""),
        "indice": indice,
        "grau": str(source.get("grau") or ""),
        "classe": str(classe.get("nome") or source.get("classe") or ""),
        "orgao_julgador": str(orgao.get("nome") or source.get("orgaoJulgador") or ""),
        "assuntos": list(source.get("assuntos") or []),
        "graus": [_resumir_grau(item) for item in sources],
        "movimentos": movimentos,
        "partes": partes,
        "metadata": {
            "source": DATAJUD,
            "source_url": source_url,
            "extracted_at": extracted_at,
            "raw_available": raw is not None,
        },
    }
    if raw is not None:
        saida["raw"] = raw
    return saida


def _resumir_grau(item: dict[str, Any]) -> dict[str, Any]:
    classe = item.get("classe")
    orgao = item.get("orgaoJulgador")
    return {
        "grau": str(item.get("grau") or ""),
        "classe": str((classe or {}).get("nome") or "") if isinstance(classe, dict) else "",
        "orgao_julgador": str((orgao or {}).get("nome") or "") if isinstance(orgao, dict) else "",
        "data_ajuizamento": str(item.get("dataAjuizamento") or ""),
        "total_movimentos": len(item.get("movimentos") or []),
    }


def _normalizar_movimento(movimento: dict[str, Any]) -> dict[str, Any]:
    complementos = movimento.get("complementosTabelados") or []
    nomes_complementos: list[str] = []
    for complemento in complementos:
        if isinstance(complemento, dict):
            valor = complemento.get("nome") or complemento.get("descricao") or ""
            if valor:
                nomes_complementos.append(str(valor))
    data_hora = str(movimento.get("dataHora") or "")
    return {
        "codigo": str(movimento.get("codigo") or ""),
        "nome": str(movimento.get("nome") or ""),
        "data_hora": data_hora,
        "data": data_hora[:10] if data_hora[:4].isdigit() else "",
        "complementos": "; ".join(nomes_complementos),
        "payload_origem": movimento,
    }


def _normalizar_parte(parte: dict[str, Any]) -> dict[str, Any]:
    advogados: list[dict[str, str]] = []
    for advogado in parte.get("advogados") or []:
        if not isinstance(advogado, dict):
            continue
        advogados.append(
            {
                "nome": str(advogado.get("nome") or ""),
                "oab": str(advogado.get("numeroOAB") or ""),
                "uf_oab": str(advogado.get("ufOAB") or ""),
            }
        )
    return {
        "nome": str(parte.get("nome") or ""),
        "tipo_parte": str(parte.get("tipoParte") or ""),
        "polo": str(parte.get("polo") or ""),
        "advogados": advogados,
        "payload_origem": parte,
    }


def resumo_do_datajud(extracao: dict[str, Any]) -> ResumoProcesso:
    """Resumo objetivo a partir do DataJud, para tribunais sem consulta eSAJ."""
    if extracao.get("status") != "ok":
        raise ProcessoNaoEncontrado("O DataJud não retornou este processo.")
    movimentos = extracao.get("movimentos") or []
    ultima: dict[str, Any] = max(movimentos, key=lambda m: m.get("data_hora") or "", default={})
    data = normalizar_data(ultima.get("data"))["iso"]
    ano, mes, dia = (data.split("-") + ["", "", ""])[:3] if data else ("", "", "")
    complementos = ultima.get("complementos") or ""
    titulo = str(ultima.get("nome") or "")
    assuntos = extracao.get("assuntos") or []
    return {
        "numero": extracao.get("numero_cnj", ""),
        "classe": extracao.get("classe", ""),
        "assunto": str((assuntos[0] or {}).get("nome", "")) if assuntos else "",
        "foro": extracao.get("tribunal", ""),
        "vara": extracao.get("orgao_julgador", ""),
        "juiz": "",
        "ultima_movimentacao": f"{titulo} - {complementos}" if complementos else titulo,
        "ultima_data": f"{dia}/{mes}/{ano}" if data else "",
        "url": (extracao.get("metadata") or {}).get("source_url", ""),
        "status": "ok",
        "mensagem": "Consulta via DataJud (processo fora do TJSP)",
        "fonte": "datajud",
    }
