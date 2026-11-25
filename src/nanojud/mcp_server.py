"""Servidor MCP local para expor extracao juridica por stdio."""

from __future__ import annotations

import importlib
import os
import shutil
import stat
import tempfile
import threading
import time
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from . import (
    api,
    autenticacao,
    compactacao,
    esaj_tjsp_2g,
    exports,
    normalization,
    pje_tjmg,
    tjmg_legado,
)
from .client import NanoJudClient
from .sources import AVAILABLE_SOURCES, ESAJ_TJSP_2G, SourceName, normalizar_fontes
from .timeline import compactar_timeline, limite_movimentacoes_para
from .utils import validar_inteiro, validar_numero_cnj
from .version import __version__

FastMCP: Any = None
try:  # pragma: no cover - exercitado quando o extra mcp esta instalado
    _fastmcp_module = importlib.import_module("mcp.server.fastmcp")
    FastMCP = _fastmcp_module.FastMCP
except ImportError:  # pragma: no cover
    pass


SERVER_NAME = "nanojud"
SERVER_TRANSPORT = "stdio"
PJE_TJMG_PRAZO_TOTAL = pje_tjmg.PRAZO_TOTAL
SERVER_SCOPE = "local_extraction_scoped_output"
MAX_MCP_DOCUMENT_BYTES = pje_tjmg.MAX_EMBEDDED_DOCUMENT_BYTES
MAX_MCP_TABLE_ROWS = 250
MAX_MCP_TABLE_CHARS = 200_000
MCP_TEMP_DOCUMENT_PREFIXES = ("nanojud_autos_", "nanojud_pje_documento_")
MCP_TEMP_OWNERSHIP_MARKER = ".nanojud-owned"
MCP_TEMP_OWNERSHIP_CONTENT = "nanojud-temporary-documents-v1"
SERVER_INSTRUCTIONS = (
    "Servidor MCP local para extracao responsavel e consulta de informacoes judiciais "
    "acessiveis pela sessao configurada. "
    "Para obter PDFs PJe ou e-SAJ no proprio resultado MCP, use obter_documento_esaj "
    "ou obter_documento_pje_tjmg "
    "(limite de 8 MiB); para PDF/DOC/DOCX individual do TJMG 2G legado, use "
    "obter_documento_tjmg_2g_legado. Os downloads em arquivo retornam caminho acessivel "
    "no host do servidor. "
    "A ferramenta consultar_autos_em_lote pode gravar PDFs numa pasta temporaria "
    "criada pelo servidor. "
    "A ferramenta gerar_tabela converte registros fornecidos pelo agente em tabela e CSV, "
    "sem consultar fontes ou gravar arquivos. "
    "Clientes MCP remotos nao podem abrir caminhos locais desse servidor; use ler_documentos=True "
    "para texto ou as ferramentas obter_documento_* para retornar PDFs como recursos. "
    "A fonte MNI SOAP 3.0/2.2.2 e opt-in e requer endpoint, versao e credencial "
    "no ambiente do servidor. "
    "Nenhuma ferramenta aceita caminho de escrita arbitrário. "
    "Nao fornece aconselhamento juridico nem contorna autenticacao ou restricoes da fonte."
)


def _pdf_como_recurso_mcp(pdf: bytes, fonte: str) -> Any:
    if not pdf.startswith(b"%PDF") or len(pdf) > MAX_MCP_DOCUMENT_BYTES:
        raise ValueError("A fonte não retornou um PDF válido dentro do limite do MCP.")
    resource_types = importlib.import_module("mcp.types")
    digest = sha256(pdf).hexdigest()
    return resource_types.EmbeddedResource(
        type="resource",
        resource=resource_types.BlobResourceContents(
            uri=f"nanojud://{fonte}/documentos/{digest}.pdf",
            mimeType="application/pdf",
            blob=b64encode(pdf).decode("ascii"),
        ),
    )


def _documento_como_recurso_mcp(conteudo: bytes, mimetype: str, fonte: str) -> Any:
    extensoes = {
        "application/pdf": ("pdf", b"%PDF"),
        "application/msword": ("doc", bytes.fromhex("d0cf11e0a1b11ae1")),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            "docx",
            b"PK\x03\x04",
        ),
    }
    tipo = extensoes.get(mimetype)
    if tipo is None or len(conteudo) > MAX_MCP_DOCUMENT_BYTES or not conteudo.startswith(tipo[1]):
        raise ValueError("A fonte não retornou documento válido dentro do limite do MCP.")
    extensao = tipo[0]
    resource_types = importlib.import_module("mcp.types")
    digest = sha256(conteudo).hexdigest()
    return resource_types.EmbeddedResource(
        type="resource",
        resource=resource_types.BlobResourceContents(
            uri=f"nanojud://{fonte}/documentos/{digest}.{extensao}",
            mimeType=mimetype,
            blob=b64encode(conteudo).decode("ascii"),
        ),
    )


def _mtime_mais_recente(diretorio: Path) -> float:
    """Retorna a alteração mais recente sem seguir links simbólicos internos."""
    mais_recente = os.lstat(diretorio).st_mtime

    def falha_da_varredura(erro: OSError) -> None:
        raise erro

    for raiz_atual, subdiretorios, arquivos in os.walk(
        diretorio, topdown=True, onerror=falha_da_varredura, followlinks=False
    ):
        for nome in (*subdiretorios, *arquivos):
            caminho = Path(raiz_atual) / nome
            mais_recente = max(mais_recente, os.lstat(caminho).st_mtime)
    return mais_recente


def _criar_diretorio_temporario(prefixo: str) -> Path:
    """Cria uma pasta exclusiva e a identifica para a limpeza posterior."""
    diretorio = Path(tempfile.mkdtemp(prefix=prefixo))
    marcador = diretorio / MCP_TEMP_OWNERSHIP_MARKER
    try:
        with marcador.open("x", encoding="ascii") as arquivo:
            arquivo.write(MCP_TEMP_OWNERSHIP_CONTENT)
    except OSError:
        shutil.rmtree(diretorio, ignore_errors=True)
        raise
    return diretorio


def _marcador_nanojud_valido(diretorio: Path) -> bool:
    marcador = diretorio / MCP_TEMP_OWNERSHIP_MARKER
    try:
        if not stat.S_ISREG(os.lstat(marcador).st_mode):
            return False
        return marcador.read_text(encoding="ascii") == MCP_TEMP_OWNERSHIP_CONTENT
    except (OSError, UnicodeError):
        return False


def _limpar_documentos_temporarios(min_age_hours: int) -> dict[str, Any]:
    raiz = Path(tempfile.gettempdir()).resolve()
    corte = time.time() - min_age_hours * 60 * 60
    removidos = 0
    recentes = 0
    falhas = 0
    try:
        candidatos = list(raiz.iterdir())
    except OSError:
        return {"status": "error", "deleted_directories": 0, "skipped_recent": 0, "failed": 1}

    for candidato in candidatos:
        if not candidato.name.startswith(MCP_TEMP_DOCUMENT_PREFIXES):
            continue
        if candidato.is_symlink() or not candidato.is_dir():
            continue
        try:
            if candidato.resolve().parent != raiz:
                continue
            if not _marcador_nanojud_valido(candidato):
                continue
            if _mtime_mais_recente(candidato) > corte:
                recentes += 1
                continue
            shutil.rmtree(candidato)
            removidos += 1
        except OSError:
            falhas += 1

    return {
        "status": "partial" if falhas else "ok",
        "deleted_directories": removidos,
        "skipped_recent": recentes,
        "failed": falhas,
    }


def create_server(client: NanoJudClient | None = None) -> Any:
    """Cria o servidor MCP local, opcionalmente com cliente/sessao autenticada.

    A sessão deve ter sido obtida pelo fluxo oficial da fonte e possuir autorização
    para os processos consultados. Ela permanece no processo e não é serializada
    como argumento MCP.
    """
    if FastMCP is None:
        raise RuntimeError(
            'O extra MCP nao esta instalado. Instale com: python -m pip install -e ".[mcp]"'
        )

    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    esaj_client = client
    document_client = client if client is not None else NanoJudClient()
    esaj_session_authentication = (
        "host_supplied_unverified" if client is not None else "not_configured"
    )
    pje_client = client if client is not None else NanoJudClient()
    # PJe links podem depender dos cookies emitidos durante a busca; serialize o
    # fluxo de duas etapas para não intercalar ViewState/cookies na mesma sessão.
    pje_lock = threading.RLock()
    esaj_lock = threading.RLock()
    tjrj_lock = threading.RLock()
    tjmg_legacy_lock = threading.RLock()

    @server.tool()
    def autenticar_esaj(timeout_login: int = 600) -> dict[str, Any]:
        """Abre o login oficial do e-SAJ no navegador local e configura a sessão em memória.

        O advogado informa os dados diretamente no portal. Nenhuma credencial ou cookie
        é recebido pelo MCP ou persistido. Disponível para consultas e autos do e-SAJ.
        """
        nonlocal esaj_client, esaj_session_authentication
        timeout_login = validar_inteiro(timeout_login, nome="timeout_login", minimo=30, maximo=1800)
        sessao = autenticacao.autenticar_esaj_no_navegador(timeout_login=timeout_login)
        cliente_base = esaj_client or document_client
        with esaj_lock:
            esaj_client = NanoJudClient(
                config=cliente_base.config,
                logger=cliente_base.logger,
                session=sessao,
                senha_processo_provider=cliente_base.senha_processo_provider,
            )
            esaj_session_authentication = "verified_by_official_login"
        return {
            "status": "ok",
            "esaj_session_configured": True,
            "esaj_session_authentication": esaj_session_authentication,
            "message": "Sessão autenticada mantida apenas na memória deste servidor MCP.",
        }

    @server.tool()
    def server_info() -> dict[str, Any]:
        """Retorna metadados do servidor MCP local."""
        return {
            "name": SERVER_NAME,
            "package": "nanojud",
            "version": __version__,
            "transport": SERVER_TRANSPORT,
            "scope": SERVER_SCOPE,
            "sources": list(AVAILABLE_SOURCES),
            "esaj_session_configured": esaj_client is not None,
            "esaj_session_authentication": esaj_session_authentication,
        }

    @server.tool()
    def validar_cnj(numero: str) -> dict[str, str]:
        """Valida e normaliza um numero CNJ."""
        numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
        return {
            "numero_cnj": numero_cnj,
            "digitos": normalization.somente_digitos(numero_cnj),
            "status": "ok",
        }

    @server.tool()
    def extrair_numeros_cnj_de_texto(texto: str) -> dict[str, Any]:
        """Extrai numeros CNJ encontrados em um texto livre."""
        numeros = normalization.extrair_numeros_cnj(texto)
        return {"count": len(numeros), "numeros": numeros}

    @server.tool()
    def consultar_esaj(
        numero: str,
        salvar_html: bool = False,
        limite_movimentacoes: int = 100,
        desde: str = "",
        compacto: bool = True,
    ) -> dict[str, Any]:
        """Extrato eSAJ/TJSP acessível pela sessão configurada.

        limite_movimentacoes=0 busca todas; desde=YYYY-MM-DD traz só movimentos a partir
        da data; compacto=True omite texto repetido e documentos por movimentação.
        """
        with esaj_lock:
            extrato = dict(
                (esaj_client or document_client).get_extrato(
                    numero,
                    salvar_html=salvar_html,
                    limite_movimentacoes=limite_movimentacoes or None,
                    desde=desde,
                )
            )
        return compactacao.compactar_extrato(extrato) if compacto else extrato

    @server.tool()
    def consultar_esaj_tjsp_2g(
        numero: str, max_paginas: int = esaj_tjsp_2g.MAX_PAGINAS
    ) -> dict[str, Any]:
        """Consulta o CPoSG público. A busca pode retornar vários recursos para um CNJ.

        max_paginas limita a coleta de movimentos por resultado. Confira status e
        movimentacoes_completas antes de interpretar a ausência de andamentos.
        """
        return api.consultar_esaj_tjsp_2g(numero, max_paginas=max_paginas)

    @server.tool()
    def consultar_eproc_tjsp_1g(
        numero: str, timeout: int = 60, aguardar_desafio_interativo: bool = False
    ) -> dict[str, Any]:
        """Consulta eproc/TJSP 1G; opcionalmente aguarda ação humana no navegador visível."""
        timeout = validar_inteiro(timeout, nome="timeout", minimo=5, maximo=300)
        return (client or document_client).consultar_eproc_tjsp_1g(
            numero,
            timeout=timeout,
            aguardar_desafio_interativo=aguardar_desafio_interativo,
        )

    @server.tool()
    def consultar_eproc_tjsp_2g(
        numero: str, timeout: int = 60, aguardar_desafio_interativo: bool = False
    ) -> dict[str, Any]:
        """Consulta eproc/TJSP 2G; opcionalmente aguarda ação humana no navegador visível."""
        timeout = validar_inteiro(timeout, nome="timeout", minimo=5, maximo=300)
        return (client or document_client).consultar_eproc_tjsp_2g(
            numero,
            timeout=timeout,
            aguardar_desafio_interativo=aguardar_desafio_interativo,
        )

    @server.tool()
    def obter_documento_esaj_tjsp_2g(
        numero: str,
        cd_documento: str,
        max_paginas: int = esaj_tjsp_2g.MAX_PAGINAS,
        max_bytes: int = MAX_MCP_DOCUMENT_BYTES,
    ) -> Any:
        """Entrega PDF público do CPoSG. Use o CNJ próprio e o cd_documento listado."""
        pdf = api.obter_pdf_esaj_tjsp_2g(
            numero, cd_documento, max_paginas=max_paginas, max_bytes=max_bytes
        )
        return _pdf_como_recurso_mcp(pdf, "esaj_tjsp_2g")

    @server.tool()
    def obter_documento_esaj(
        numero: str,
        cd_documento: str,
        max_bytes: int = MAX_MCP_DOCUMENT_BYTES,
    ) -> Any:
        """Entrega uma peça e-SAJ acessível como recurso PDF MCP, até 8 MiB."""
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or not 1 <= max_bytes <= MAX_MCP_DOCUMENT_BYTES
        ):
            raise ValueError("max_bytes deve estar entre 1 e 8388608 para entrega MCP.")
        cliente = esaj_client or document_client
        with esaj_lock:
            pdf = cliente.obter_pdf_esaj(numero, cd_documento, max_bytes=max_bytes)
        return _pdf_como_recurso_mcp(pdf, "esaj")

    @server.tool()
    def consultar_pje_tjmg(
        numero: str, prazo_total: float | None = PJE_TJMG_PRAZO_TOTAL
    ) -> dict[str, Any]:
        """Consulta detalhe público PJe/TJMG e devolve movimentos e documentos observados.

        Percorre até 100 páginas por tabela. A resposta fica parcial quando uma
        página falha, a paginação não pode ser verificada ou o limite é excedido.
        prazo_total limita a espera total em segundos; None desativa esse teto.
        O provedor ainda não faz parte das fontes padrão de extrair_processo.
        """
        with pje_lock:
            return pje_client.consultar_pje_tjmg(numero, prazo_total=prazo_total)

    @server.tool()
    def consultar_tjrj_1g(
        numero: str,
        max_paginas_movimentos: int = api.tjrj.MAX_PAGINAS_MOVIMENTOS,
    ) -> dict[str, Any]:
        """Consulta movimentos públicos do TJRJ 1G, paginando históricos volumosos.

        A página final usa o cursor definido pela SPA pública. O limite padrão é 150;
        se for atingido, o resultado preserva os movimentos recebidos e fica parcial.
        Documentos não estão incluídos.
        """
        max_paginas_movimentos = validar_inteiro(
            max_paginas_movimentos,
            nome="max_paginas_movimentos",
            minimo=1,
            maximo=api.tjrj.MAX_PAGINAS_MOVIMENTOS_LIMITE,
        )
        with tjrj_lock:
            return (client or document_client).consultar_tjrj_1g(
                numero,
                max_paginas_movimentos=max_paginas_movimentos,
            )

    @server.tool()
    def consultar_tjmg_2g_legado(numero: str, identificador_tjmg: str) -> dict[str, Any]:
        """Consulta detalhe legado público TJMG 2G com CNJ e identificador interno.

        O identificador interno não é derivado do CNJ. O retorno é sempre parcial
        porque a paginação e a completude do histórico não foram comprovadas.
        """
        with tjmg_legacy_lock:
            return (client or document_client).consultar_tjmg_2g_legado(numero, identificador_tjmg)

    @server.tool()
    def obter_documento_tjmg_2g_legado(
        numero: str,
        identificador_tjmg: str,
        cd_documento: str,
        ano_criacao_doc: str,
        max_bytes: int = tjmg_legado.MAX_DOCUMENT_BYTES,
    ) -> Any:
        """Retorna como recurso MCP uma peça ligada à consulta pública TJMG 2G legado."""
        max_bytes = validar_inteiro(
            max_bytes, nome="max_bytes", minimo=1, maximo=tjmg_legado.MAX_DOCUMENT_BYTES
        )
        with tjmg_legacy_lock:
            conteudo, mimetype = (client or document_client).obter_documento_tjmg_2g_legado(
                numero,
                identificador_tjmg,
                cd_documento,
                ano_criacao_doc,
                max_bytes=max_bytes,
            )
        return _documento_como_recurso_mcp(conteudo, mimetype, "tjmg-2g-legado")

    @server.tool()
    def ler_documento_pje_tjmg(url: str, max_chars: int = 4000) -> dict[str, Any]:
        """Lê em memória o PDF oferecido como público pelo PJe/TJMG, sem contornar restrições."""
        max_chars = validar_inteiro(max_chars, nome="max_chars", minimo=1, maximo=10000)
        with pje_lock:
            return pje_client.ler_documento_pje_tjmg(url, max_chars=max_chars)

    @server.tool()
    def baixar_documento_pje_tjmg(url: str) -> dict[str, Any]:
        """Baixa PDF público PJe/TJMG numa pasta temporária exclusiva criada pelo servidor."""
        diretorio = _criar_diretorio_temporario("nanojud_pje_documento_")
        destino = diretorio / "documento.pdf"
        try:
            with pje_lock:
                resultado = pje_client.baixar_documento_pje_tjmg(url, destino)
        except Exception:
            shutil.rmtree(diretorio, ignore_errors=True)
            raise
        return resultado

    @server.tool()
    def limpar_documentos_temporarios(min_age_hours: int = 24) -> dict[str, Any]:
        """Remove somente pastas temporárias NanoJud com pelo menos a idade indicada.

        A limpeza limita-se a pastas NanoJud de autos e documentos PJe criadas
        diretamente na pasta temporária do sistema. O padrão preserva resultados
        recentes por 24 horas; a idade mínima aceita é de 1 hora a 1 ano.
        """
        min_age_hours = validar_inteiro(min_age_hours, nome="min_age_hours", minimo=1, maximo=8760)
        with esaj_lock, pje_lock:
            return _limpar_documentos_temporarios(min_age_hours)

    @server.tool()
    def obter_documento_pje_tjmg(
        url: str, max_bytes: int = pje_tjmg.MAX_EMBEDDED_DOCUMENT_BYTES
    ) -> Any:
        """Entrega PDF público PJe/TJMG como recurso MCP binário, até 8 MiB."""
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or not 1 <= max_bytes <= pje_tjmg.MAX_EMBEDDED_DOCUMENT_BYTES
        ):
            raise ValueError("max_bytes deve estar entre 1 e 8388608 para entrega MCP.")
        with pje_lock:
            pdf = pje_client.obter_pdf_pje_tjmg(url, max_bytes=max_bytes)
        return _pdf_como_recurso_mcp(pdf, "pje-tjmg")

    @server.tool()
    def consultar_datajud(
        numero: str,
        include_raw: bool = False,
        api_key: str | None = None,
        compacto: bool = True,
        prazo_total: float | None = 60.0,
    ) -> dict[str, Any]:
        """Consulta DataJud/CNJ, pagina até 100 registros e sinaliza retorno parcial.
        status=partial indica total não confirmado, falha/corte de paginação ou limite atingido.
        prazo_total limita retries, esperas e paginação em segundos; None desativa o teto.
        compacto=True
        omite o payload original repetido de cada movimento (processos grandes passam de
        150 KB); compacto=False devolve tudo."""
        if client is not None:
            resultado = document_client.consultar_datajud(
                numero,
                include_raw=include_raw,
                api_key=api_key,
                prazo_total=prazo_total,
            )
        else:
            resultado = api.consultar_datajud(
                numero,
                include_raw=include_raw,
                api_key=api_key,
                prazo_total=prazo_total,
            )
        return compactacao.compactar_datajud(resultado) if compacto else resultado

    @server.tool()
    def consultar_djen(numero: str, data_inicio: str = "") -> dict[str, Any]:
        """Consulta comunicacoes do DJEN para um processo."""
        detalhado = (
            document_client.consultar_djen_detalhado(numero, data_inicio=data_inicio)
            if client is not None
            else api.consultar_djen_detalhado(numero, data_inicio=data_inicio)
        )
        return {
            "count": len(detalhado["comunicacoes"]),
            "comunicacoes": detalhado["comunicacoes"],
            "status": detalhado["status"],
            "completo": detalhado["completo"],
            "paginas": detalhado["paginas"],
            "avisos": detalhado["avisos"],
        }

    @server.tool()
    def extrair_processo(
        numero: str,
        sources: list[str] | None = None,
        include_raw: bool = False,
        datajud_api_key: str | None = None,
        djen_data_inicio: str = "",
        desde: str = "",
        compacto: bool = True,
    ) -> dict[str, Any]:
        """Envelope versionado por fonte. Usa a sessão configurada para o e-SAJ.

        compacto=True mantém só a timeline unificada; desde=YYYY-MM-DD restringe a data.
        """
        extrair = esaj_client.extract_process if esaj_client else api.extract_process
        with esaj_lock:
            envelope = extrair(
                numero,
                sources=_normalizar_sources(sources),
                include_raw=include_raw,
                datajud_api_key=datajud_api_key,
                djen_data_inicio=djen_data_inicio,
                desde=desde,
            )
        return compactacao.compactar_envelope(envelope) if compacto else envelope

    @server.tool()
    def extrair_processos(
        numeros: list[str],
        sources: list[str] | None = None,
        include_raw: bool = False,
        datajud_api_key: str | None = None,
        djen_data_inicio: str = "",
        desde: str = "",
        max_workers: int = 1,
        limite_movimentacoes: int = 100,
        compacto: bool = True,
    ) -> dict[str, Any]:
        """Consulta até 50 processos em lote, preservando ordem e falhas por processo.

        Usa a sessão configurada para o e-SAJ. Lotes autenticados são sequenciais
        (max_workers=1); para lotes maiores, use Python ou o comando CLI batch.
        """
        if (
            not isinstance(numeros, list)
            or not numeros
            or len(numeros) > 50
            or any(not isinstance(numero, str) for numero in numeros)
        ):
            raise ValueError("numeros deve ser uma lista de 1 a 50 números CNJ em texto.")
        max_workers = validar_inteiro(max_workers, nome="max_workers", minimo=1, maximo=4)
        if esaj_client and max_workers != 1:
            raise ValueError("Lotes autenticados usam max_workers=1 para isolar a sessão HTTP.")
        extrair_lote = esaj_client.extract_processes if esaj_client else api.extract_processes
        with esaj_lock:
            resumo = extrair_lote(
                numeros,
                sources=_normalizar_sources(sources),
                include_raw=include_raw,
                datajud_api_key=datajud_api_key,
                djen_data_inicio=djen_data_inicio,
                desde=desde,
                max_workers=max_workers,
                limite_movimentacoes=limite_movimentacoes or None,
            )
        if compacto:
            for item in resumo["items"]:
                if "result" in item:
                    compactado = compactacao.compactar_envelope(
                        cast(dict[str, Any], item["result"])
                    )
                    cast(Any, item)["result"] = compactado
        return cast(dict[str, Any], resumo)

    @server.tool()
    def consultar_autos_em_lote(
        numeros: list[str],
        ler_documentos: bool = False,
        max_documentos_por_processo: int = 3,
        max_chars: int = 3000,
        desde: str = "",
        source: str | None = None,
    ) -> dict[str, Any]:
        """Consulta até 10 processos do TJSP/eSAJ ou TJMG/PJe e obtém peças públicas.

        PDFs baixados ficam em pasta local por processo; `ler_documentos=True` tenta ler
        texto em memória. O PJe percorre até 100 páginas por tabela e preserva `partial`
        se houver falha, páginas pendentes ou limite excedido.

        Com `ler_documentos=False`, o caminho pertence ao filesystem do servidor MCP e pode
        não estar acessível ao cliente remoto. Use `ler_documentos=True` para texto, ou
        a ferramenta obter_documento do provedor para um PDF individual no resultado.
        source="esaj_tjsp_2g" consulta os vínculos públicos do CPoSG.
        """
        if source not in (None, ESAJ_TJSP_2G):
            raise ValueError("source deve ser esaj_tjsp_2g ou omitido para roteamento padrão.")
        if (
            not isinstance(numeros, list)
            or not numeros
            or len(numeros) > 10
            or any(not isinstance(numero, str) for numero in numeros)
        ):
            raise ValueError("Informe de 1 a 10 números CNJ por chamada MCP.")
        if not isinstance(ler_documentos, bool):
            raise ValueError("ler_documentos deve ser booleano.")
        max_documentos_por_processo = validar_inteiro(
            max_documentos_por_processo,
            nome="max_documentos_por_processo",
            minimo=1,
            maximo=10,
        )
        max_chars = validar_inteiro(max_chars, nome="max_chars", minimo=1, maximo=10000)
        from tempfile import gettempdir

        destino = gettempdir() if ler_documentos else _criar_diretorio_temporario("nanojud_autos_")
        try:
            with esaj_lock:
                itens = list(
                    (esaj_client.iter_extract_dockets if esaj_client else api.iter_extract_dockets)(
                        numeros,
                        destination=destino,
                        max_documents_per_process=max_documentos_por_processo,
                        read_documents=ler_documentos,
                        document_max_chars=max_chars,
                        desde=desde,
                        source=source,
                    )
                )
        except Exception:
            if not ler_documentos:
                shutil.rmtree(destino, ignore_errors=True)
            raise
        return {
            "total": len(itens),
            "succeeded": sum(item.get("status") in {"ok", "no_documents"} for item in itens),
            "partial": sum(item.get("status") == "partial" for item in itens),
            "failed": sum(item.get("status") in {"error", "unsupported"} for item in itens),
            "items": itens,
            "warnings": [
                "Autos em lote cobrem eSAJ/TJSP e PJe/TJMG nesta versão. "
                "O PJe percorre até 100 páginas por tabela e mantém estado parcial se "
                "restarem páginas ou ocorrer falha. "
                "PDFs são salvos localmente quando ler_documentos=false."
            ],
        }

    @server.tool()
    def gerar_timeline(
        numero: str,
        sources: list[str] | None = None,
        datajud_api_key: str | None = None,
        djen_data_inicio: str = "",
        limit: int = 0,
        recent_first: bool = False,
        include_text: bool = True,
        max_text_chars: int = 0,
        desde: str = "",
    ) -> dict[str, Any]:
        """Timeline cronologica sem interpretacao juridica. Com recent_first=True e limit,
        busca so o necessario no eSAJ; desde=YYYY-MM-DD restringe a data."""
        extrair = esaj_client.extract_process if esaj_client else api.extract_process
        with esaj_lock:
            envelope = extrair(
                numero,
                sources=_normalizar_sources(sources),
                include_raw=False,
                datajud_api_key=datajud_api_key,
                djen_data_inicio=djen_data_inicio,
                desde=desde,
                limite_movimentacoes=limite_movimentacoes_para(limit, recent_first, 100),
            )
        timeline = compactar_timeline(
            envelope.get("timeline", []),
            limit=limit,
            recent_first=recent_first,
            include_text=include_text,
            max_text_chars=max_text_chars,
        )
        return {
            "schema_version": envelope.get("schema_version"),
            "package_version": envelope.get("package_version"),
            "status": envelope.get("status"),
            "numero_cnj": envelope.get("numero_cnj"),
            "sources": envelope.get("sources", []),
            "source_status": envelope.get("source_status", {}),
            "timeline": timeline,
            "warnings": envelope.get("warnings", []),
            "errors": envelope.get("errors", []),
        }

    @server.tool()
    def gerar_tabela(
        registros: list[dict[str, Any]],
        colunas: list[str] | None = None,
        source_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Monta tabela determinística e CSV de até 250 registros recebidos do agente.

        Para registros com textos extensos, selecione colunas concisas para respeitar o limite
        de 200.000 caracteres. Preserva proveniência e pode propagar status_fonte de
        gerar_timeline. Não consulta
        fontes nem grava arquivos. Fórmulas são neutralizadas somente na versão CSV.
        """
        if source_status is not None and not isinstance(source_status, dict):
            raise ValueError("source_status deve ser um objeto por fonte.")
        linhas = []
        for registro in registros:
            linha = dict(registro)
            fonte = linha.get("fonte")
            estado = source_status.get(fonte) if source_status and isinstance(fonte, str) else None
            if "status_fonte" not in linha and isinstance(estado, dict):
                status = estado.get("status")
                if isinstance(status, str):
                    linha["status_fonte"] = status
            linhas.append(linha)
        return exports.to_table(
            linhas,
            columns=colunas,
            max_rows=MAX_MCP_TABLE_ROWS,
            max_chars=MAX_MCP_TABLE_CHARS,
        )

    @server.tool()
    def ler_documentos_publicos(
        numero: str,
        limite: int = 3,
        max_chars: int = 4000,
    ) -> dict[str, Any]:
        """Le documentos acessíveis pela sessão em memória, sem salvar PDF em disco."""
        limite = validar_inteiro(limite, nome="limite", minimo=1, maximo=10)
        max_chars = validar_inteiro(max_chars, nome="max_chars", minimo=1, maximo=10000)
        get_extrato = esaj_client.get_extrato if esaj_client else api.get_extrato
        with esaj_lock:
            extrato = get_extrato(numero, inspecionar_pecas=True, limite_inspecao_pecas=limite)
            if esaj_client:
                documentos = esaj_client.ler_pecas(
                    cast(dict[str, Any], extrato), limite=limite, max_chars=max_chars
                )
            else:
                documentos = api.ler_pecas(
                    cast(dict[str, Any], extrato), limite=limite, max_chars=max_chars
                )
        origem = extrato.get("origem") or {}
        indice_documentos = extrato.get("documentos") or {}
        candidatos = indice_documentos.get("publicos_candidatos_unicos") or []
        restritos = indice_documentos.get("restritos_por_senha_unicos") or []
        movimentacoes_completas = origem.get("movimentacoes_completas") is True
        avisos = [
            "A leitura nao salva PDFs em disco; conteudo remoto e processado em memoria.",
            "A fonte valida autenticação e autorização; CAPTCHA, senha ou sigilo não são "
            "contornados.",
        ]
        if not movimentacoes_completas:
            avisos.append(
                origem.get("aviso_movimentacoes")
                or "A listagem de movimentações e documentos não foi confirmada como completa."
            )
        if restritos:
            avisos.append(f"{len(restritos)} documento(s) restrito(s) não foram lidos.")
        if len(candidatos) > limite:
            avisos.append(
                f"Documentos limitados a {limite} de {len(candidatos)} candidatos públicos."
            )
        estados_sucesso = {"texto_extraido", "texto_html_extraido"}
        falhas = [
            documento for documento in documentos if documento.get("status") not in estados_sucesso
        ]
        if falhas:
            avisos.append(
                f"{len(falhas)} documento(s) selecionado(s) não teve(ram) texto extraído."
            )
        if not candidatos and not restritos and movimentacoes_completas:
            status = "no_documents"
        elif not movimentacoes_completas or restritos or len(candidatos) > limite or falhas:
            status = "partial"
        else:
            status = "ok"
        return {
            "status": status,
            "numero_cnj": (extrato.get("dados_basicos") or {}).get("numero", numero),
            "count": len(documentos),
            "total_public_candidates": len(candidatos),
            "restricted_documents": len(restritos),
            "movimentacoes_completas": movimentacoes_completas,
            "documentos": documentos,
            "warnings": avisos,
        }

    return server


def main() -> None:
    """Executa o servidor MCP local por stdio."""
    create_server().run(transport=SERVER_TRANSPORT)


def _normalizar_sources(sources: list[str] | None) -> tuple[SourceName, ...]:
    return normalizar_fontes(sources)


if __name__ == "__main__":  # pragma: no cover
    main()
