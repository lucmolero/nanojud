"""Consulta pública de segundo grau do e-SAJ/TJSP (CPoSG)."""

import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

from . import esaj
from .exceptions import (
    AcessoRestrito,
    ConsultaInconclusiva,
    ConsultaIndisponivel,
    DocumentoNaoEncontrado,
    DownloadIndisponivel,
    FormatoCNJInvalido,
    mensagem_erro_segura,
)
from .utils import limpar, validar_inteiro, validar_numero_cnj, validar_timeout

BASE = "https://esaj.tjsp.jus.br/cposg/"
MAX_PAGINAS = 10
MAX_RESULTADOS = 10


def _codigo_valido(codigo: str) -> bool:
    return len(codigo) <= 64 and codigo.isascii() and codigo.isalnum()


def _documento_valido(codigo: str) -> bool:
    return len(codigo) <= 32 and codigo.isascii() and codigo.isdecimal()


def _codigo_detalhe(href: str) -> str:
    url = urlsplit(urljoin(BASE, href))
    if (url.scheme, url.netloc, url.path) != ("https", "esaj.tjsp.jus.br", "/cposg/show.do"):
        return ""
    codigos = parse_qs(url.query).get("processo.codigo", [])
    return codigos[0] if len(codigos) == 1 and _codigo_valido(codigos[0]) else ""


def _url_detalhe(codigo: str) -> str:
    return f"{BASE}show.do?processo.codigo={codigo}"


def _requisitar(
    sessao: requests.Session, url: str, timeout: float, **kwargs: Any
) -> requests.Response:
    try:
        return sessao.get(url, timeout=timeout, allow_redirects=False, **kwargs)
    except requests.RequestException as exc:
        raise ConsultaIndisponivel("Falha ao consultar o e-SAJ de segundo grau.") from exc


def _exigir_sucesso(resposta: requests.Response) -> None:
    if resposta.status_code in {401, 403}:
        raise AcessoRestrito(f"CPoSG retornou HTTP {resposta.status_code}.")
    if resposta.status_code != 200:
        raise ConsultaIndisponivel(f"CPoSG retornou HTTP {resposta.status_code}.")


def _pagina(sessao: requests.Session, caminho: str, timeout: float, **kwargs: Any) -> BeautifulSoup:
    resposta = _requisitar(sessao, f"{BASE}{caminho}", timeout, **kwargs)
    try:
        if caminho == "search.do" and resposta.is_redirect:
            codigo = _codigo_detalhe(resposta.headers.get("Location", ""))
            if codigo:
                return _pagina(sessao, "show.do", timeout, params={"processo.codigo": codigo})
    except ValueError as exc:
        raise ConsultaIndisponivel("Falha ao consultar o e-SAJ de segundo grau.") from exc
    _exigir_sucesso(resposta)
    content_type = resposta.headers.get("Content-Type", "").lower()
    encoding = resposta.encoding if "charset=" in content_type else None
    soup = BeautifulSoup(resposta.content, "html.parser", from_encoding=encoding)
    if soup.select_one("#captcha") or "consultas simult" in soup.get_text(" ", strip=True).lower():
        raise ConsultaIndisponivel("CPoSG limitou a consulta pública.")
    # Mantém a identidade da resposta mesmo quando a busca redireciona ao detalhe.
    soup.attrs["url_coleta"] = resposta.url
    return soup


def _localizar(soup: BeautifulSoup, numero: str) -> tuple[list[tuple[str, str]], bool]:
    numero_capa = esaj.texto_id(soup, "numeroProcesso")
    if numero_capa:
        if numero_capa != numero:
            raise ConsultaIndisponivel("A capa retornada pelo CPoSG não confirma o CNJ consultado.")
        codigo = _codigo_detalhe(str(soup.attrs.get("url_coleta", "")))
        if not codigo:
            campos = soup.select('input[type="hidden"][name="cdProcesso"]')
            codigo = str(campos[0].get("value", "")) if len(campos) == 1 else ""
        if not _codigo_valido(codigo):
            raise ConsultaIndisponivel("A capa do CPoSG não informou um código de processo único.")
        return [(numero, codigo)], True
    links = soup.select("a.linkProcesso")
    registros: dict[str, str] = {}
    validos = True
    for link in links:
        try:
            codigo = _codigo_detalhe(str(link.get("href", "")))
            cnj = validar_numero_cnj(link.get_text(strip=True))
        except (FormatoCNJInvalido, ValueError):
            validos = False
            continue
        if not codigo or registros.get(codigo, cnj) != cnj:
            validos = False
            continue
        registros[codigo] = cnj
    if not registros:
        if not links and soup.select_one('form[action="/cposg/search.do"]'):
            raise ConsultaInconclusiva("O formulário CPoSG não exibiu resultado verificável.")
        raise ConsultaIndisponivel("O CPoSG não apresentou um resultado verificável para a busca.")
    return [(cnj, codigo) for codigo, cnj in registros.items()], validos


def _documentos(linha: Tag, descricao: Tag) -> list[dict[str, str]]:
    documentos: dict[str, dict[str, str]] = {}
    seletor = "a.linkMovVincProc[cddocumento]"
    for link in (*descricao.select(seletor), *linha.select(seletor)):
        codigo = str(link.get("cddocumento", ""))
        if _documento_valido(codigo) and codigo not in documentos:
            documentos[codigo] = {
                "cd_documento": codigo,
                "titulo": esaj.titulo_documento(link, ""),
                "status_acesso": "nao_verificado",
            }
    return list(documentos.values())


def _movimentos(
    sessao: requests.Session,
    codigo: str,
    timeout: float,
    max_paginas: int,
    *,
    ate_documento: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    movimentos: list[dict[str, Any]] = []
    cursores: set[str] = set()
    params = {"cdProcesso": codigo}
    for pagina in range(max_paginas):
        if pagina:
            time.sleep(esaj.PAUSA_PAGINAS)
        try:
            soup = _pagina(sessao, "carregarMovimentacoesAjax.do", timeout, params=params)
        except (AcessoRestrito, ConsultaIndisponivel) as exc:
            return movimentos, mensagem_erro_segura(exc)
        if pagina == 0 and soup.select_one("#tabelaMovimentacoesAjax") is None:
            return movimentos, "A primeira página de movimentações não foi reconhecida."
        for linha in soup.select("tr.movimentacaoProcesso"):
            data = linha.select_one(".dataMovimentacaoProcesso")
            descricao = linha.select_one(".descricaoMovimentacaoProcesso")
            if data is None or descricao is None:
                return movimentos, "O CPoSG retornou uma movimentação sem data ou descrição."
            titulo, teor, texto = esaj.extrair_titulo_teor_movimentacao(descricao)
            documentos = _documentos(linha, descricao)
            movimentos.append(
                {
                    "ordem": len(movimentos) + 1,
                    "data": limpar(data.get_text(" ", strip=True)),
                    "titulo": titulo,
                    "teor": teor,
                    "texto": texto,
                    "documentos": documentos,
                }
            )
            if ate_documento and any(doc["cd_documento"] == ate_documento for doc in documentos):
                return movimentos, "Coleta encerrada após localizar o documento solicitado."
        if pagina == 0:
            if not movimentos:
                return movimentos, "A primeira página de movimentações não foi reconhecida."
            marcador = soup.select_one("#linkMaisRecolherMovimentacoes")
            if marcador is None:
                return movimentos, ""
        else:
            marcador = soup.select_one("#metaPaginaMovimentacoes")
            estado = marcador.get("data-tem-mais-paginas") if marcador else None
            if estado == "false":
                return movimentos, ""
            if estado != "true":
                return movimentos, "O CPoSG não informou se existem mais movimentações."
        cursor = marcador.get("data-cursor") if marcador else None
        if not isinstance(cursor, str) or not cursor or cursor in cursores:
            return movimentos, "O CPoSG retornou um cursor ausente ou repetido."
        cursores.add(cursor)
        params = {"cdProcesso": codigo, "cursor": cursor}
    return movimentos, "Limite de páginas de movimentações atingido."


def _resultado(
    sessao: requests.Session,
    numero: str,
    codigo: str,
    timeout: float,
    max_paginas: int,
    capa: BeautifulSoup | None,
    *,
    ate_documento: str | None = None,
) -> dict[str, Any]:
    params = {"processo.codigo": codigo}
    url = _url_detalhe(codigo)
    resultado: dict[str, Any] = {"numero": numero, "url": url, "movimentacoes_completas": False}
    try:
        if capa is None:
            capa = _pagina(sessao, "show.do", timeout, params=params)
        if esaj.texto_id(capa, "numeroProcesso") != numero:
            raise ConsultaIndisponivel("A capa não confirma o CNJ do resultado.")
    except (AcessoRestrito, ConsultaIndisponivel) as exc:
        return {
            **resultado,
            "status": "erro",
            "erro": {"tipo": type(exc).__name__, "mensagem": mensagem_erro_segura(exc)},
        }
    dados = esaj.extrair_dados_basicos(capa, url)
    dados["orgao_julgador"] = esaj.texto_id(capa, "orgaoJulgadorProcesso")
    dados["relator"] = esaj.texto_id(capa, "relatorProcesso")
    dados["secao"] = esaj.texto_id(capa, "secaoProcesso")
    movimentos: list[dict[str, Any]] = []
    aviso = "O CPoSG não exibiu o controle de movimentações."
    if capa.select_one("#linkExibirMovimentacoes"):
        movimentos, aviso = _movimentos(
            sessao, codigo, timeout, max_paginas, ate_documento=ate_documento
        )
    return {
        **resultado,
        "status": "partial" if aviso else "ok",
        "dados_basicos": dados,
        "movimentacoes": movimentos,
        "movimentacoes_completas": not aviso,
        "aviso_movimentacoes": aviso,
    }


def _buscar(sessao: requests.Session, numero: str, timeout: float) -> BeautifulSoup:
    params = [
        ("conversationId", ""),
        ("paginaConsulta", "1"),
        ("cbPesquisa", "NUMPROC"),
        ("numeroDigitoAnoUnificado", numero[:15]),
        ("foroNumeroUnificado", numero[-4:]),
        ("dePesquisaNuUnificado", numero),
        ("dePesquisaNuUnificado", "UNIFICADO"),
        ("dePesquisa", ""),
        ("tipoNuProcesso", "UNIFICADO"),
    ]
    esaj._aguardar_ritmo()
    _pagina(sessao, "open.do", timeout)
    return _pagina(sessao, "search.do", timeout, params=params)


def consultar_processo(
    numero: str, *, timeout: float = 30.0, max_paginas: int = MAX_PAGINAS
) -> dict[str, Any]:
    """Consulta o CPoSG e preserva os processos encontrados sob o CNJ informado."""
    numero = validar_numero_cnj(numero)
    timeout = validar_timeout(timeout)
    max_paginas = validar_inteiro(max_paginas, nome="max_paginas", minimo=1, maximo=100)
    with esaj.criar_session(timeout=timeout) as sessao:
        return _consultar(sessao, numero, timeout, max_paginas)


def _consultar(
    sessao: requests.Session, numero: str, timeout: float, max_paginas: int = MAX_PAGINAS
) -> dict[str, Any]:
    busca = _buscar(sessao, numero, timeout)
    encontrados, links_validos = _localizar(busca, numero)
    capa = busca if esaj.texto_id(busca, "numeroProcesso") else None
    resultados = [
        _resultado(sessao, cnj, codigo, timeout, max_paginas, capa)
        for cnj, codigo in encontrados[:MAX_RESULTADOS]
    ]
    avisos = []
    if not links_validos:
        avisos.append("A lista do CPoSG continha um resultado inválido.")
    if len(encontrados) > MAX_RESULTADOS:
        avisos.append(f"Detalhes consultados para os primeiros {MAX_RESULTADOS} resultados.")
    estados = {r["status"] for r in resultados}
    status = "partial"
    if estados == {"erro"}:
        status = "erro"
    elif estados == {"ok"} and not avisos:
        status = "ok"
    return {
        "status": status,
        "numero_consultado": numero,
        "origem": {
            "sistema": "eSAJ",
            "tribunal": "TJSP",
            "grau": "2g",
            "consulta": "cposg",
            "data_coleta": datetime.now(UTC).isoformat(),
        },
        "quantidade_listada": len(encontrados),
        "resultados_listados": [
            {"numero": cnj, "url": _url_detalhe(codigo)} for cnj, codigo in encontrados
        ],
        "resultados": resultados,
        "avisos": avisos,
    }


def _parametros_pdf(
    sessao: requests.Session, numero: str, codigo: str, documento: str, timeout: float
) -> dict[str, list[str]]:
    verificacao = _requisitar(
        sessao,
        f"{BASE}verificarAcessoMovimentacao.do",
        timeout,
        params={"cdDocumento": documento, "cdProcesso": codigo, "origemRecurso": "M"},
    )
    _exigir_sucesso(verificacao)
    link = verificacao.text.strip()
    try:
        destino = urlsplit(link)
        query = parse_qs(destino.query)
    except ValueError as exc:
        raise DownloadIndisponivel("Resposta inválida da verificação de acesso.") from exc
    if (
        (destino.scheme, destino.netloc, destino.path)
        != ("https", "esaj.tjsp.jus.br", "/pastadigital/abrirDocumentoEdt.do")
        or query.get("cdProcesso") != [codigo]
        or query.get("nuProcesso") != [numero]
        or not query.get("ticket")
        or destino.fragment
        or any(caractere.isspace() for caractere in link)
    ):
        raise DownloadIndisponivel("O portal não forneceu um visualizador válido para o processo.")
    viewer = _requisitar(sessao, link, timeout)
    _exigir_sucesso(viewer)
    try:
        arvore = json.loads(esaj.extrair_request_scope(viewer.text) or "null")
        (raiz,) = arvore
        (pagina,) = raiz["children"]
        params = parse_qs(pagina["data"]["parametros"], keep_blank_values=True)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise DownloadIndisponivel("O visualizador não identificou um único arquivo PDF.") from exc
    if params.get("cdProcesso") != [codigo] or params.get("nuProcesso") != [numero]:
        raise DownloadIndisponivel("O arquivo do visualizador não corresponde ao processo.")
    return params


def _baixar_pdf_vinculado(
    sessao: requests.Session,
    numero: str,
    codigo: str,
    documento: str,
    timeout: float,
    max_bytes: int,
) -> bytes:
    """Baixa após autorização do portal, para um vínculo já conferido na sessão."""
    params = _parametros_pdf(sessao, numero, codigo, documento, timeout)
    resposta = _requisitar(
        sessao, f"{esaj.PASTA_BASE}getPDF.do", timeout, params=params, stream=True
    )
    try:
        _exigir_sucesso(resposta)
        dados = esaj._ler_resposta_limitada(resposta, max_bytes)
    except requests.RequestException as exc:
        raise DownloadIndisponivel("Falha na leitura do PDF do CPoSG.") from exc
    finally:
        resposta.close()
    if dados is None or not dados.startswith(b"%PDF-"):
        raise DownloadIndisponivel("O CPoSG não retornou um PDF válido dentro do limite.")
    return dados


def obter_pdf_publico(
    numero: str,
    cd_documento: str,
    *,
    timeout: float = 30.0,
    max_paginas: int = MAX_PAGINAS,
    max_bytes: int = esaj.MAX_IN_MEMORY_DOCUMENT_BYTES,
) -> bytes:
    """Abre o documento listado sob o CNJ próprio após a verificação oficial de acesso."""
    numero = validar_numero_cnj(numero)
    timeout = validar_timeout(timeout)
    max_paginas = validar_inteiro(max_paginas, nome="max_paginas", minimo=1, maximo=100)
    max_bytes = validar_inteiro(
        max_bytes, nome="max_bytes", minimo=1, maximo=esaj.MAX_IN_MEMORY_DOCUMENT_BYTES
    )
    if not isinstance(cd_documento, str) or not _documento_valido(cd_documento):
        raise ValueError("cd_documento deve conter de 1 a 32 algarismos.")
    with esaj.criar_session(timeout=timeout) as sessao:
        busca = _buscar(sessao, numero, timeout)
        encontrados, _ = _localizar(busca, numero)
        codigos = [codigo for cnj, codigo in encontrados if cnj == numero]
        if len(codigos) != 1:
            raise ConsultaIndisponivel("Informe o CNJ próprio do resultado de segundo grau.")
        codigo = codigos[0]
        capa = busca if esaj.texto_id(busca, "numeroProcesso") else None
        resultado = _resultado(
            sessao, numero, codigo, timeout, max_paginas, capa, ate_documento=cd_documento
        )
        if not any(
            doc["cd_documento"] == cd_documento
            for movimento in resultado.get("movimentacoes", [])
            for doc in movimento["documentos"]
        ):
            if not resultado["movimentacoes_completas"]:
                raise ConsultaIndisponivel("A coleta parcial não confirmou o vínculo do documento.")
            raise DocumentoNaoEncontrado("O CPoSG não listou esse documento nos movimentos.")
        return _baixar_pdf_vinculado(sessao, numero, codigo, cd_documento, timeout, max_bytes)
