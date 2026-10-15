"""Servidor MCP local para expor extracao juridica por stdio."""

from __future__ import annotations

import importlib
from typing import Any, cast

from . import api, normalization
from .sources import ALL_SOURCES, SourceName, normalizar_fonte
from .timeline import compactar_timeline
from .utils import validar_numero_cnj
from .version import __version__

FastMCP: Any = None
try:  # pragma: no cover - exercitado quando o extra mcp esta instalado
    _fastmcp_module = importlib.import_module("mcp.server.fastmcp")
    FastMCP = _fastmcp_module.FastMCP
except ImportError:  # pragma: no cover
    pass


SERVER_NAME = "nanojud"
SERVER_TRANSPORT = "stdio"
SERVER_SCOPE = "local_read_only_extraction"
SERVER_INSTRUCTIONS = (
    "Servidor MCP local para extracao responsavel de dados publicos judiciais. "
    "As ferramentas apenas consultam, normalizam e retornam dados estruturados. "
    "Nao fornece aconselhamento juridico, nao burla autenticacao e nao acessa segredo de justica."
)


def create_server() -> Any:
    """Cria o servidor MCP local usando FastMCP."""
    if FastMCP is None:
        raise RuntimeError(
            'O extra MCP nao esta instalado. Instale com: python -m pip install -e ".[mcp]"'
        )

    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def server_info() -> dict[str, Any]:
        """Retorna metadados do servidor MCP local."""
        return {
            "name": SERVER_NAME,
            "package": "nanojud",
            "version": __version__,
            "transport": SERVER_TRANSPORT,
            "scope": SERVER_SCOPE,
            "sources": list(ALL_SOURCES),
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
        numero: str, salvar_html: bool = False, limite_movimentacoes: int = 100
    ) -> dict[str, Any]:
        """Consulta extrato publico do eSAJ/TJSP (limite_movimentacoes=0 busca todas)."""
        return dict(
            api.get_extrato(
                numero,
                salvar_html=salvar_html,
                limite_movimentacoes=limite_movimentacoes or None,
            )
        )

    @server.tool()
    def consultar_datajud(
        numero: str,
        include_raw: bool = False,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Consulta dados processuais estruturados na API publica DataJud/CNJ."""
        return api.consultar_datajud(numero, include_raw=include_raw, api_key=api_key)

    @server.tool()
    def consultar_djen(numero: str, data_inicio: str = "") -> dict[str, Any]:
        """Consulta comunicacoes do DJEN para um processo."""
        comunicacoes = api.consultar_djen(numero, data_inicio=data_inicio)
        return {"count": len(comunicacoes), "comunicacoes": comunicacoes}

    @server.tool()
    def extrair_processo(
        numero: str,
        sources: list[str] | None = None,
        include_raw: bool = False,
        datajud_api_key: str | None = None,
        djen_data_inicio: str = "",
    ) -> dict[str, Any]:
        """Extrai dados das fontes solicitadas em envelope versionado."""
        return api.extract_process(
            numero,
            sources=_normalizar_sources(sources),
            include_raw=include_raw,
            datajud_api_key=datajud_api_key,
            djen_data_inicio=djen_data_inicio,
        )

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
    ) -> dict[str, Any]:
        """Gera timeline cronologica de registros extraidos, sem interpretacao juridica."""
        envelope = api.extract_process(
            numero,
            sources=_normalizar_sources(sources),
            include_raw=False,
            datajud_api_key=datajud_api_key,
            djen_data_inicio=djen_data_inicio,
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
    def ler_documentos_publicos(
        numero: str,
        limite: int = 3,
        max_chars: int = 4000,
    ) -> dict[str, Any]:
        """Le documentos publicos candidatos em memoria, sem salvar PDF em disco."""
        extrato = api.get_extrato(numero, inspecionar_pecas=True, limite_inspecao_pecas=limite)
        documentos = api.ler_pecas(
            cast(dict[str, Any], extrato),
            limite=limite,
            max_chars=max_chars,
        )
        return {
            "numero_cnj": (extrato.get("dados_basicos") or {}).get("numero", numero),
            "count": len(documentos),
            "documentos": documentos,
            "warnings": [
                "A leitura nao salva PDFs em disco; conteudo remoto e processado em memoria.",
                "Documentos restritos por senha, captcha ou sigilo nao sao acessados.",
            ],
        }

    return server


def main() -> None:
    """Executa o servidor MCP local por stdio."""
    create_server().run(transport=SERVER_TRANSPORT)


def _normalizar_sources(sources: list[str] | None) -> tuple[SourceName, ...]:
    if not sources:
        return ALL_SOURCES
    return tuple(normalizar_fonte(source) for source in sources)


if __name__ == "__main__":  # pragma: no cover
    main()
