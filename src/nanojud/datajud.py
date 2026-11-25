"""Cliente DataJud/CNJ para dados processuais estruturados."""

from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast

import requests

from .exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado
from .models import ResumoProcesso
from .normalization import normalizar_data, somente_digitos
from .schemas import DataJudExtraction, SourceMetadata
from .sources import DATAJUD
from .utils import validar_numero_cnj, validar_prazo_total, validar_timeout

API_TEMPLATE = "https://api-publica.datajud.cnj.jus.br/api_publica_{indice}/_search"
DATAJUD_WIKI_ACESSO_URL = "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
PUBLIC_DATAJUD_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
# O DataJud indexa um registro por grau (G1, TR, G2...) para o mesmo numero CNJ.
MAX_REGISTROS = 10
MAX_PAGINAS = 10
MAX_RETRY_AFTER_SECONDS = 60.0
ORDEM_GRAUS = ("G1", "JE", "TR", "G2", "SUP")
HTTP_STATUS_TRANSITORIOS = frozenset({408, 429, 500, 502, 503, 504})
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

INDICES_JUSTICA_MILITAR_ESTADUAL = {
    "13": "tjmmg",
    "21": "tjmrs",
    "26": "tjmsp",
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
    if segmento == "9":
        return INDICES_JUSTICA_MILITAR_ESTADUAL.get(tribunal, "")
    if segmento == "6":
        if tribunal == "00":
            return "tse"
        estadual = INDICES_JUSTICA_ESTADUAL.get(tribunal, "")
        return f"tre-{estadual[2:]}" if estadual else ""
    if segmento == "7" and tribunal == "00":
        return "stm"
    if segmento == "3" and tribunal == "00":
        return "stj"
    if segmento == "5" and tribunal == "00":
        return "tst"
    if segmento == "4" and 1 <= int(tribunal) <= 6:
        return f"trf{int(tribunal)}"
    if segmento == "5" and 1 <= int(tribunal) <= 24:
        return f"trt{int(tribunal)}"
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


def _retry_after_seconds(
    response: requests.Response,
    *,
    now: datetime | None = None,
) -> float | None:
    """Interpreta Retry-After em segundos ou data HTTP, sem aceitar valores inválidos."""
    raw = response.headers.get("Retry-After")
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
        instante = now or datetime.now(UTC)
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=UTC)
        return max(0.0, (data_retentativa - instante).total_seconds())
    if segundos < 0:
        return None
    return float(segundos)


def _post_com_retry(
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout: float,
    prazo_final: float | None,
    retry: int,
    backoff: float,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    """Executa uma página DataJud com a política de repetição comum."""
    response: requests.Response | None = None
    for tentativa in range(retry):
        restante_request = None if prazo_final is None else prazo_final - time.monotonic()
        if restante_request is not None and restante_request <= 0:
            raise ConsultaIndisponivel("DataJud excedeu o prazo total da consulta.")
        timeout_tentativa = timeout if restante_request is None else min(timeout, restante_request)
        try:
            response = session.post(
                url,
                json=cast(Any, payload),
                headers=headers,
                timeout=timeout_tentativa,
            )
        except requests.RequestException as exc:
            if tentativa + 1 >= retry:
                raise ConsultaIndisponivel(
                    f"Falha de comunicacao com DataJud ({type(exc).__name__})."
                ) from exc
            espera = backoff * (tentativa + 1)
            restante_retry = None if prazo_final is None else prazo_final - time.monotonic()
            if restante_retry is not None and (restante_retry <= 0 or espera >= restante_retry):
                raise ConsultaIndisponivel(
                    "DataJud excedeu o prazo total da consulta antes do próximo retry."
                ) from exc
            sleep(espera)
            continue

        if prazo_final is not None and time.monotonic() >= prazo_final:
            raise ConsultaIndisponivel("DataJud excedeu o prazo total da consulta.")

        if response.status_code == 200:
            break
        if response.status_code in HTTP_STATUS_TRANSITORIOS and tentativa + 1 < retry:
            espera_retry_after = _retry_after_seconds(response)
            if espera_retry_after is None:
                espera_retry_after = backoff * (tentativa + 1)
            if espera_retry_after > MAX_RETRY_AFTER_SECONDS:
                raise ConsultaIndisponivel(
                    "DataJud solicitou aguardar mais de 60 segundos via Retry-After; "
                    "a tentativa automática foi encerrada sem repetir a consulta."
                )
            restante_retry_after = None if prazo_final is None else prazo_final - time.monotonic()
            if restante_retry_after is not None and (
                restante_retry_after <= 0 or espera_retry_after >= restante_retry_after
            ):
                raise ConsultaIndisponivel(
                    "DataJud excedeu o prazo total da consulta antes do Retry-After."
                )
            sleep(espera_retry_after)
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
    if not isinstance(body, dict):
        raise ConsultaIndisponivel("DataJud retornou JSON com estrutura inesperada.")
    return body


def _agregar_raw_datajud(body: dict[str, Any], hits: list[Any]) -> dict[str, Any]:
    """Preserva o envelope bruto, agregando todas as páginas efetivamente recebidas."""
    raw = dict(body)
    resposta_hits = body.get("hits")
    if isinstance(resposta_hits, dict):
        raw_hits = dict(resposta_hits)
        raw_hits["hits"] = hits
        raw["hits"] = raw_hits
    return raw


def consultar_processo(
    numero: str,
    *,
    api_key: str | None = None,
    indice: str | None = None,
    include_raw: bool = False,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    prazo_total: float | None = 60.0,
    retry: int = 3,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> DataJudExtraction:
    """Consulta DataJud com teto total cooperativo para retry e paginação."""
    timeout = validar_timeout(timeout)
    validar_prazo_total(prazo_total)
    if isinstance(retry, bool) or not isinstance(retry, int) or retry < 1:
        raise ValueError("retry deve ser um inteiro positivo.")
    if (
        isinstance(backoff, bool)
        or not isinstance(backoff, (int, float))
        or not math.isfinite(backoff)
        or backoff < 0
    ):
        raise ValueError("backoff deve ser um número finito não negativo.")
    numero = validar_numero_cnj(numero, segmento=None, tribunal=None)
    indice_resolvido = indice or indice_datajud(numero)
    if not indice_resolvido:
        raise ConsultaIndisponivel("Nao ha indice DataJud mapeado para o numero CNJ informado.")

    url = API_TEMPLATE.format(indice=indice_resolvido)
    payload: dict[str, Any] = {
        "query": {"match": {"numeroProcesso": somente_digitos(numero)}},
        "size": MAX_REGISTROS,
        "sort": [{"@timestamp": {"order": "asc"}}],
        "_source": DEFAULT_SOURCE_FIELDS,
    }
    headers = {
        "Authorization": datajud_api_key(api_key),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    session = session or requests.Session()
    prazo_final = time.monotonic() + prazo_total if prazo_total is not None else None
    body = _post_com_retry(
        session,
        url,
        payload,
        headers,
        timeout=timeout,
        prazo_final=prazo_final,
        retry=retry,
        backoff=backoff,
        sleep=sleep,
    )

    resultado = body.get("hits")
    hits = resultado.get("hits") if isinstance(resultado, dict) else None
    if not isinstance(hits, list):
        raise ConsultaIndisponivel("DataJud retornou JSON com estrutura inesperada.")
    total_hits, total_relation = _ler_total_registros(resultado)
    if total_hits is not None and total_hits < len(hits):
        raise ConsultaIndisponivel("DataJud retornou total menor que a quantidade de registros.")

    hits_completos = list(hits)
    ids_primeira_pagina = [
        hit.get("_id") if isinstance(hit, dict) else None for hit in hits_completos
    ]
    ids_hits: set[str] = set()
    paginas_consultadas = 1
    aviso_paginacao = ""
    if total_relation == "eq" and total_hits is not None and total_hits > len(hits):
        if any(
            not isinstance(identificador, str) or not identificador
            for identificador in ids_primeira_pagina
        ) or len(set(ids_primeira_pagina)) != len(ids_primeira_pagina):
            aviso_paginacao = "DataJud não forneceu identificadores únicos na primeira página."
        else:
            ids_hits = set(cast(list[str], ids_primeira_pagina))
        cursor_hit = hits[-1] if hits else None
        cursor = cursor_hit.get("sort") if isinstance(cursor_hit, dict) else None
        seen_cursors: set[tuple[Any, ...]] = set()
        while (
            not aviso_paginacao
            and len(hits_completos) < total_hits
            and paginas_consultadas < MAX_PAGINAS
        ):
            if not isinstance(cursor, list) or not cursor:
                aviso_paginacao = "DataJud não forneceu cursor válido para continuar a paginação."
                break
            cursor_id = tuple(cursor)
            if cursor_id in seen_cursors:
                aviso_paginacao = "DataJud repetiu o cursor de paginação; coleta incompleta."
                break
            seen_cursors.add(cursor_id)
            payload_pagina = {**payload, "search_after": cursor}
            try:
                corpo_pagina = _post_com_retry(
                    session,
                    url,
                    payload_pagina,
                    headers,
                    timeout=timeout,
                    prazo_final=prazo_final,
                    retry=retry,
                    backoff=backoff,
                    sleep=sleep,
                )
            except (AcessoRestrito, ConsultaIndisponivel) as exc:
                aviso_paginacao = (
                    "DataJud não concluiu a paginação após a primeira página: "
                    f"{type(exc).__name__}."
                )
                break

            hits_resultado_pagina = corpo_pagina.get("hits")
            hits_pagina = (
                hits_resultado_pagina.get("hits")
                if isinstance(hits_resultado_pagina, dict)
                else None
            )
            total_pagina, relacao_pagina = _ler_total_registros(hits_resultado_pagina)
            if (
                not isinstance(hits_pagina, list)
                or total_pagina != total_hits
                or relacao_pagina != "eq"
            ):
                aviso_paginacao = (
                    "DataJud alterou o total ou a estrutura durante a paginação; "
                    "a coleta permanece parcial."
                )
                break
            if not hits_pagina:
                aviso_paginacao = "DataJud encerrou a paginação antes do total confirmado."
                break
            ids_pagina = [hit.get("_id") if isinstance(hit, dict) else None for hit in hits_pagina]
            if (
                any(
                    not isinstance(identificador, str) or not identificador
                    for identificador in ids_pagina
                )
                or len(set(ids_pagina)) != len(ids_pagina)
                or ids_hits.intersection(cast(list[str], ids_pagina))
            ):
                aviso_paginacao = (
                    "DataJud repetiu ou omitiu identificadores de registros na paginação."
                )
                break
            proximo_hit = hits_pagina[-1]
            proximo_cursor = proximo_hit.get("sort") if isinstance(proximo_hit, dict) else None
            if (
                not isinstance(proximo_cursor, list)
                or not proximo_cursor
                or proximo_cursor == cursor
            ):
                aviso_paginacao = "DataJud não avançou o cursor; coleta incompleta."
                break
            hits_completos.extend(hits_pagina)
            ids_hits.update(cast(list[str], ids_pagina))
            cursor = proximo_cursor
            paginas_consultadas += 1
        if not aviso_paginacao and len(hits_completos) < total_hits:
            aviso_paginacao = (
                f"DataJud atingiu o limite de {MAX_PAGINAS} páginas antes de completar a coleta; "
                "o resultado permanece parcial."
            )

    registros_completos = (
        total_hits == len(hits_completos) and total_relation == "eq" and not aviso_paginacao
    )
    metadados_registros: SourceMetadata = {
        "records_complete": registros_completos,
        "records_returned": len(hits_completos),
        "total_hits": total_hits,
        "total_relation": total_relation,
    }
    avisos_registros = _avisos_completude_datajud(
        registros_completos, len(hits_completos), total_hits, total_relation
    )
    if aviso_paginacao:
        avisos_registros.append(aviso_paginacao)

    sources: list[dict[str, Any]] = []
    tribunal_esperado = indice_datajud(numero).upper()
    for hit in hits_completos:
        source = hit.get("_source") if isinstance(hit, dict) else None
        if not isinstance(source, dict) or not source:
            raise ConsultaIndisponivel("DataJud retornou registro com estrutura inesperada.")
        numero_retornado = source.get("numeroProcesso")
        if not isinstance(numero_retornado, (str, int)) or not str(numero_retornado).strip():
            raise ConsultaIndisponivel("DataJud retornou registro com estrutura inválida: sem CNJ.")
        try:
            numero_retornado = validar_numero_cnj(
                str(numero_retornado), segmento=None, tribunal=None
            )
        except ValueError as exc:
            raise ConsultaIndisponivel(
                "DataJud retornou registro com estrutura inválida: CNJ inválido."
            ) from exc
        if numero_retornado != numero:
            raise ConsultaIndisponivel("DataJud retornou CNJ divergente do número consultado.")
        if tribunal_esperado:
            tribunal_retornado = str(source.get("tribunal") or "").strip().upper()
            if not tribunal_retornado:
                raise ConsultaIndisponivel(
                    "DataJud retornou registro com estrutura inválida: sem tribunal."
                )
            if tribunal_retornado != tribunal_esperado:
                raise ConsultaIndisponivel(
                    "DataJud retornou tribunal divergente do CNJ consultado."
                )
        sources.append(source)

    extracted_at = datetime.now(UTC).isoformat()
    if not hits and registros_completos:
        return {
            "status": "nao_encontrado",
            "numero_cnj": numero,
            "indice": indice_resolvido,
            "metadata": {
                "source": DATAJUD,
                "source_url": url,
                "extracted_at": extracted_at,
                "raw_available": include_raw,
                **metadados_registros,
                "records_pages": paginas_consultadas,
            },
            **({"raw": _agregar_raw_datajud(body, hits_completos)} if include_raw else {}),
        }

    if not hits:
        return {
            "status": "partial",
            "numero_cnj": numero,
            "indice": indice_resolvido,
            "warnings": avisos_registros,
            "metadata": {
                "source": DATAJUD,
                "source_url": url,
                "extracted_at": extracted_at,
                "raw_available": include_raw,
                **metadados_registros,
                "records_pages": paginas_consultadas,
            },
            **({"raw": _agregar_raw_datajud(body, hits_completos)} if include_raw else {}),
        }

    sources.sort(key=lambda item: _rank_grau(str(item.get("grau") or "")))
    return _normalizar_source(
        sources,
        numero=numero,
        indice=indice_resolvido,
        source_url=url,
        extracted_at=extracted_at,
        raw=_agregar_raw_datajud(body, hits_completos) if include_raw else None,
        registros_completos=registros_completos,
        total_hits=total_hits,
        total_relation=total_relation,
        avisos=avisos_registros,
        paginas_consultadas=paginas_consultadas,
    )


def _ler_total_registros(resultado: Any) -> tuple[int | None, str | None]:
    if not isinstance(resultado, dict):
        return None, None
    total = resultado.get("total")
    if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
        return total, "eq"
    if not isinstance(total, dict):
        return None, None
    valor = total.get("value")
    relacao = total.get("relation")
    if (
        isinstance(valor, bool)
        or not isinstance(valor, int)
        or valor < 0
        or not isinstance(relacao, str)
        or not relacao
    ):
        return None, None
    return valor, relacao


def _avisos_completude_datajud(
    completo: bool,
    registros_retornados: int,
    total: int | None,
    relacao: str | None,
) -> list[str]:
    if completo:
        return []
    if total is None:
        return ["DataJud não informou o total de registros; a completude não foi confirmada."]
    if relacao == "eq" and total > registros_retornados:
        return [
            f"DataJud retornou {registros_retornados} de {total} registros; "
            "o limite da consulta pode ter truncado o resultado."
        ]
    return [
        f"DataJud informou total {relacao or 'desconhecido'} de {total}; "
        "a completude do resultado não foi confirmada."
    ]


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
    registros_completos: bool,
    total_hits: int | None,
    total_relation: str | None,
    avisos: list[str],
    paginas_consultadas: int,
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
        "status": "ok" if registros_completos else "partial",
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
        "warnings": avisos,
        "metadata": {
            "source": DATAJUD,
            "source_url": source_url,
            "extracted_at": extracted_at,
            "raw_available": raw is not None,
            "records_complete": registros_completos,
            "records_returned": len(sources),
            "total_hits": total_hits,
            "total_relation": total_relation,
            "records_pages": paginas_consultadas,
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
    status_extracao = extracao.get("status")
    if status_extracao == "nao_encontrado":
        raise ProcessoNaoEncontrado("O DataJud não retornou este processo.")
    if status_extracao not in {"ok", "partial"}:
        raise ConsultaIndisponivel("O DataJud retornou um estado de consulta inválido.")
    movimentos = extracao.get("movimentos") or []
    ultima: dict[str, Any] = max(movimentos, key=lambda m: m.get("data_hora") or "", default={})
    data = normalizar_data(ultima.get("data"))["iso"]
    ano, mes, dia = (data.split("-") + ["", "", ""])[:3] if data else ("", "", "")
    complementos = ultima.get("complementos") or ""
    titulo = str(ultima.get("nome") or "")
    assuntos = extracao.get("assuntos") or []
    avisos = extracao.get("warnings") or []
    metadata = extracao.get("metadata") or {}
    mensagem = "Consulta via DataJud (processo fora do TJSP)"
    if status_extracao == "partial":
        mensagem = f"{mensagem}; retorno parcial"
    if avisos:
        mensagem = f"{mensagem}. {'; '.join(str(aviso) for aviso in avisos)}"
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
        "status": status_extracao,
        "mensagem": mensagem,
        "fonte": "datajud",
        "grau": str(ultima.get("grau") or extracao.get("grau") or ""),
        "data_coleta": str(metadata.get("extracted_at") or ""),
        "coleta_completa": metadata.get("records_complete"),
    }
