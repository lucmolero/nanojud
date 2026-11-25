"""Consulta pública da SPA processual do TJRJ (1º grau)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests

from .exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado, URLInvalida
from .normalization import normalizar_data
from .utils import validar_numero_cnj, validar_timeout
from .version import __version__

ORIGIN = "https://www3.tjrj.jus.br/consultaprocessual"
SITE_ORIGIN = "https://www3.tjrj.jus.br"
SEARCH_ENDPOINT = f"{ORIGIN}/api/processos/por-numeracao-unica"
DETAIL_ENDPOINT = f"{ORIGIN}/api/processos/por-numero/publica"
MOVEMENTS_ENDPOINT = f"{ORIGIN}/api/processos/por-numero/movimentos"
HOST = "www3.tjrj.jus.br"
MAX_PAGINAS_MOVIMENTOS = 150
MAX_PAGINAS_MOVIMENTOS_LIMITE = 500


def _validar_endpoint(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.path
        not in {
            "/consultaprocessual/api/processos/por-numeracao-unica",
            "/consultaprocessual/api/processos/por-numero/publica",
            "/consultaprocessual/api/processos/por-numero/movimentos",
        }
    ):
        raise URLInvalida("A URL não pertence à API oficial de consulta pública do TJRJ.")


def _sessao(session: requests.Session | None) -> requests.Session:
    if session is not None:
        return session
    criada = requests.Session()
    criada.headers.update(
        {
            "User-Agent": f"Mozilla/5.0 (compatible; nanojud/{__version__}; +https://github.com/lucmolero/nanojud)",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": SITE_ORIGIN,
            "Referer": f"{ORIGIN}/",
        }
    )
    return criada


def _post(
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
) -> Any:
    _validar_endpoint(url)
    try:
        response = session.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(
            f"Falha de comunicação com o TJRJ: {type(exc).__name__}."
        ) from exc
    if response.status_code in (401, 403):
        raise AcessoRestrito(f"TJRJ retornou HTTP {response.status_code}.")
    if response.status_code == 404:
        raise ProcessoNaoEncontrado("O TJRJ não localizou o processo na consulta pública.")
    if response.status_code == 429 or response.status_code >= 500:
        raise ConsultaIndisponivel(f"TJRJ retornou HTTP {response.status_code}.")
    if response.status_code >= 400:
        raise ConsultaIndisponivel(f"TJRJ retornou HTTP {response.status_code}.")
    try:
        body = response.json()
    except (ValueError, requests.JSONDecodeError) as exc:
        raise ConsultaIndisponivel("O TJRJ retornou uma resposta que não é JSON válido.") from exc
    return body


def _iniciar_sessao(session: requests.Session, *, timeout: float) -> None:
    """Carrega a SPA oficial e mantém a sessão/cookies que ela própria emitir."""
    try:
        response = session.get(f"{ORIGIN}/", timeout=timeout)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel(
            f"Falha ao abrir a consulta pública TJRJ: {type(exc).__name__}."
        ) from exc
    if response.status_code in (401, 403, 412):
        raise AcessoRestrito(f"A consulta pública TJRJ retornou HTTP {response.status_code}.")
    if response.status_code >= 400:
        raise ConsultaIndisponivel(f"A consulta pública TJRJ retornou HTTP {response.status_code}.")


def _data(valor: Any) -> str:
    if not valor:
        return ""
    texto = str(valor).strip()
    try:
        return normalizar_data(texto)["iso"] or texto
    except (TypeError, ValueError):
        return texto


def _normalizar_movimentos(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expande os grupos do contrato da SPA em eventos visíveis individualmente."""
    movimentos: list[dict[str, Any]] = []
    for grupo in rows:
        itens = grupo.get("movimentosExibicao")
        if itens is None:
            # Compatibilidade com respostas/fixtures antigas sem o agrupamento da SPA.
            itens = [grupo]
        if not isinstance(itens, list):
            raise ConsultaIndisponivel("O TJRJ retornou submovimentos em formato inesperado.")
        for item in itens:
            if not isinstance(item, dict):
                raise ConsultaIndisponivel("O TJRJ retornou um submovimento em formato inesperado.")
            resumo = item.get("resumoOuIntegra")
            if resumo is not None and not isinstance(resumo, dict):
                raise ConsultaIndisponivel(
                    "O TJRJ retornou um resumo de movimento em formato inesperado."
                )
            detalhes = item.get("detalhesMovimento")
            if detalhes is not None and (
                not isinstance(detalhes, list)
                or any(not isinstance(detalhe, dict) for detalhe in detalhes)
            ):
                raise ConsultaIndisponivel(
                    "O TJRJ retornou detalhes de movimento em formato inesperado."
                )
            detalhes_texto = [
                str(detalhe.get("descricao") or "").strip()
                for detalhe in detalhes or []
                if detalhe.get("descricao")
            ]
            resumo_texto = str((resumo or {}).get("descResumida") or "").strip()
            titulo = str(
                grupo.get("descrMov")
                or item.get("descrTipAto")
                or item.get("tipoMovimento")
                or (resumo or {}).get("descTipoAto")
                or ""
            ).strip()
            teor = str(grupo.get("descricao") or resumo_texto or "\n".join(detalhes_texto)).strip()
            metadados: dict[str, Any] = {"codigo_tipo_andamento": grupo.get("codTipAnd")}
            if item.get("tipoMovimento"):
                metadados["tipo_movimento"] = str(item["tipoMovimento"]).strip()
            if item.get("descrTipAto"):
                metadados["descricao_tipo_ato"] = str(item["descrTipAto"]).strip()
            if detalhes_texto:
                metadados["detalhes_movimento"] = detalhes_texto
            movimentos.append(
                {
                    "ordem": grupo.get("ordem"),
                    "data": _data(
                        grupo.get("dtMovimento")
                        or grupo.get("dtJuntada")
                        or grupo.get("dtAlt")
                        or grupo.get("dt")
                    ),
                    "titulo": titulo,
                    "teor": teor,
                    "metadados": metadados,
                }
            )
    return movimentos


def _validar_max_paginas_movimentos(valor: int) -> int:
    if (
        isinstance(valor, bool)
        or not isinstance(valor, int)
        or not 1 <= valor <= MAX_PAGINAS_MOVIMENTOS_LIMITE
    ):
        raise ValueError(
            f"max_paginas_movimentos deve estar entre 1 e {MAX_PAGINAS_MOVIMENTOS_LIMITE}."
        )
    return valor


def consultar_processo(
    numero: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    max_paginas_movimentos: int = MAX_PAGINAS_MOVIMENTOS,
) -> dict[str, Any]:
    """Consulta capa pública e movimentos disponíveis do TJRJ para CNJ estadual RJ.

    O adaptador cobre o contrato público de primeiro grau observado na SPA do TJRJ.
    Não acessa documentos nem transforma resultados de segundo grau/eJUD em cobertura.
    """
    timeout = validar_timeout(timeout)
    max_paginas_movimentos = _validar_max_paginas_movimentos(max_paginas_movimentos)
    numero_cnj = validar_numero_cnj(numero, segmento="8", tribunal="19")
    cliente = _sessao(session)
    _iniciar_sessao(cliente, timeout=timeout)
    resultados = _post(
        cliente,
        SEARCH_ENDPOINT,
        {
            "codigoProcesso": numero_cnj,
            "tipoProcesso": "1",
            "numeroProcVep": "",
            "rg": "",
        },
        timeout=timeout,
    )
    if not isinstance(resultados, list) or any(not isinstance(item, dict) for item in resultados):
        raise ConsultaIndisponivel("O TJRJ retornou um formato inesperado na busca pública.")
    origem = next(
        (
            item
            for item in resultados
            if str(item.get("codigoCnj") or "") == numero_cnj
            and str(item.get("tipoProcesso") or "") == "1"
        ),
        None,
    )
    if origem is None:
        raise ProcessoNaoEncontrado("A busca pública do TJRJ não retornou origem de primeiro grau.")
    codigo_processo = str(origem.get("numProcesso") or "").strip()
    if not codigo_processo:
        raise ConsultaIndisponivel(
            "O TJRJ não informou o número de origem necessário para abrir o detalhe."
        )
    detalhe = _post(
        cliente,
        DETAIL_ENDPOINT,
        {
            "codigoProcesso": codigo_processo,
            "tipoProcesso": "1",
            "numeroProcVep": "",
            "rg": "",
        },
        timeout=timeout,
    )
    if not isinstance(detalhe, dict):
        raise ConsultaIndisponivel("O TJRJ retornou um formato inesperado para o detalhe público.")
    if str(detalhe.get("codCnj") or "") != numero_cnj:
        raise ConsultaIndisponivel("O TJRJ não confirmou o CNJ consultado no detalhe público.")
    if str(detalhe.get("indSigilo") or "").upper() not in ("N", "0", "NAO", "NÃO"):
        raise AcessoRestrito("O TJRJ identificou sigilo ou não confirmou que o processo é público.")

    movimentos_body = _post(
        cliente,
        MOVEMENTS_ENDPOINT,
        {
            "codigoProcesso": codigo_processo,
            "tipoProcesso": "1",
            "indProcVolumoso": "S" if detalhe.get("processoVolumoso") else "N",
        },
        timeout=timeout,
    )
    if not isinstance(movimentos_body, dict):
        raise ConsultaIndisponivel("O TJRJ retornou um formato inesperado para os movimentos.")
    if str(movimentos_body.get("codCnj") or "") != numero_cnj:
        raise ConsultaIndisponivel(
            "A resposta de movimentos do TJRJ não confirmou o CNJ consultado."
        )
    rows = movimentos_body.get("movimentosProc")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ConsultaIndisponivel("O TJRJ retornou uma lista de movimentos em formato inesperado.")

    volumoso = movimentos_body.get("processoVolumoso") is True
    pagina_volumosa = movimentos_body.get("exibePaginacaoProcessoVolumoso") is True
    movimentos_paginas = 0
    movimentos: list[dict[str, Any]] = []
    completo = False
    aviso = ""
    cursor: Any = None

    for pagina in range(max_paginas_movimentos):
        if pagina == 0:
            body = movimentos_body
        else:
            try:
                body = _post(
                    cliente,
                    MOVEMENTS_ENDPOINT,
                    {
                        "codigoProcesso": codigo_processo,
                        "tipoProcesso": "1",
                        "indProcVolumoso": "S",
                        "ultimaOrdemExibida": cursor,
                    },
                    timeout=timeout,
                )
            except (AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado) as exc:
                aviso = f"A paginação TJRJ foi interrompida: {type(exc).__name__}."
                break
        movimentos_paginas += 1
        if not isinstance(body, dict) or str(body.get("codCnj") or "") != numero_cnj:
            aviso = "A paginação TJRJ retornou resposta sem confirmação do CNJ."
            break
        pagina_rows = body.get("movimentosProc")
        if not isinstance(pagina_rows, list) or any(
            not isinstance(row, dict) for row in pagina_rows
        ):
            aviso = "A paginação TJRJ retornou movimentos em formato inesperado."
            break
        try:
            movimentos_pagina = _normalizar_movimentos(pagina_rows)
        except ConsultaIndisponivel as exc:
            aviso = str(exc)
            break

        if not volumoso or not pagina_volumosa:
            movimentos.extend(movimentos_pagina)
            completo = (
                body.get("todosMovimentos") is True
                and body.get("processoVolumoso") is False
                and body.get("exibePaginacaoProcessoVolumoso") is False
            )
            if not completo and not aviso:
                aviso = "O TJRJ não confirmou que todos os movimentos foram retornados."
            break

        if (
            body.get("todosMovimentos") is not True
            or body.get("processoVolumoso") is not True
            or body.get("exibePaginacaoProcessoVolumoso") is not True
        ):
            movimentos.extend(movimentos_pagina)
            aviso = "O TJRJ alterou os indicadores de paginação durante a consulta."
            break
        if not pagina_rows:
            completo = True
            break
        proximo_cursor = pagina_rows[-1].get("ordem")
        if proximo_cursor is None:
            # A SPA pública usa a ausência de ordem no último grupo como fim do cursor.
            movimentos.extend(movimentos_pagina)
            completo = True
            break
        if isinstance(proximo_cursor, bool) or not isinstance(proximo_cursor, (int, str)):
            movimentos.extend(movimentos_pagina)
            aviso = "O TJRJ retornou um cursor de paginação inválido."
            break
        if proximo_cursor in ("", 0, "0"):
            # A SPA pública usa a ordem zero como marcador final do cursor.
            movimentos.extend(movimentos_pagina)
            completo = True
            break
        if proximo_cursor == cursor:
            aviso = "O TJRJ repetiu o cursor da paginação; o histórico permanece parcial."
            break
        movimentos.extend(movimentos_pagina)
        cursor = proximo_cursor
    else:
        aviso = f"O limite de {max_paginas_movimentos} páginas de movimentos foi atingido."

    if not completo and not aviso:
        aviso = "O TJRJ não confirmou que todos os movimentos foram retornados."
    dados_basicos = {
        "numero": numero_cnj,
        "classe": str(detalhe.get("txtAcao") or "").strip(),
        "assunto": str(detalhe.get("txtAssunto") or "").strip(),
        "foro": str(detalhe.get("descServ") or "").strip(),
        "vara": str(detalhe.get("descVara") or "").strip(),
        "distribuicao": _data(detalhe.get("dataDis")),
        "situacao": str(detalhe.get("sitProc") or "").strip(),
        "url": (
            f"{ORIGIN}/#/consultapublicap?codigoProcesso={codigo_processo}&tipoProcesso=1&siteKey="
        ),
    }
    return {
        "status": "ok" if completo else "partial",
        "origem": {
            "sistema": "TJRJ Consulta Pública",
            "tribunal": "TJRJ",
            "grau": "1G",
            "consulta": "publica",
            "entrada": "SPA/API oficial do TJRJ",
            "url_final": dados_basicos["url"],
            "endpoint_host": HOST,
            "data_coleta": datetime.now(UTC).isoformat(),
            "movimentacoes_completas": completo,
            "movimentacoes_paginas": movimentos_paginas,
            "movimentacoes_registros": len(movimentos),
            **({"aviso_movimentacoes": aviso} if aviso else {}),
        },
        "dados_basicos": dados_basicos,
        "movimentacoes": movimentos,
    }
