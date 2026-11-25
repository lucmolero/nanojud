import tempfile
from types import SimpleNamespace

import pytest

from nanojud import mcp_server


class FakeFastMCP:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs
        self.tools = {}
        self.ran = False
        self.run_kwargs = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    def run(self, **kwargs):
        self.ran = True
        self.run_kwargs = kwargs


def test_create_server_exige_extra_mcp(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", None)

    with pytest.raises(RuntimeError, match="extra MCP"):
        mcp_server.create_server()


def test_create_server_registra_ferramentas(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    server = mcp_server.create_server()

    assert server.name == "nanojud"
    assert "extracao responsavel" in server.kwargs["instructions"]
    assert "Clientes MCP remotos nao podem abrir caminhos locais" in server.kwargs["instructions"]
    assert "MNI SOAP 3.0/2.2.2" in server.kwargs["instructions"]
    assert "filesystem do servidor MCP" in server.tools["consultar_autos_em_lote"].__doc__
    assert "autenticar_esaj" in server.tools
    assert set(server.tools) == {
        "server_info",
        "autenticar_esaj",
        "validar_cnj",
        "extrair_numeros_cnj_de_texto",
        "consultar_esaj",
        "consultar_esaj_tjsp_2g",
        "consultar_eproc_tjsp_1g",
        "consultar_eproc_tjsp_2g",
        "obter_documento_esaj_tjsp_2g",
        "obter_documento_esaj",
        "consultar_pje_tjmg",
        "consultar_tjrj_1g",
        "consultar_tjmg_2g_legado",
        "obter_documento_tjmg_2g_legado",
        "ler_documento_pje_tjmg",
        "baixar_documento_pje_tjmg",
        "obter_documento_pje_tjmg",
        "limpar_documentos_temporarios",
        "consultar_datajud",
        "consultar_djen",
        "extrair_processo",
        "extrair_processos",
        "consultar_autos_em_lote",
        "gerar_timeline",
        "gerar_tabela",
        "ler_documentos_publicos",
    }


def test_mcp_tjmg_2g_legado_repassa_cnj_e_id(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    chamadas = []

    class FakeClient:
        def consultar_tjmg_2g_legado(self, numero, identificador):
            chamadas.append((numero, identificador))
            return {"status": "partial"}

    server = mcp_server.create_server(client=FakeClient())
    resultado = server.tools["consultar_tjmg_2g_legado"](
        "2125575-44.2023.8.13.0000", "10000232125575004"
    )
    assert resultado == {"status": "partial"}
    assert chamadas == [("2125575-44.2023.8.13.0000", "10000232125575004")]


def test_mcp_obter_documento_tjmg_repassa_vinculo_e_limite(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    chamadas = []

    class FakeClient:
        def obter_documento_tjmg_2g_legado(self, *args, **kwargs):
            chamadas.append((args, kwargs))
            return b"doc-bytes", "application/msword"

    monkeypatch.setattr(mcp_server, "_documento_como_recurso_mcp", lambda *args: args)
    server = mcp_server.create_server(client=FakeClient())
    resultado = server.tools["obter_documento_tjmg_2g_legado"](
        "2125575-44.2023.8.13.0000", "10000232125575004", "12345", "2024", 2048
    )
    assert resultado == (b"doc-bytes", "application/msword", "tjmg-2g-legado")
    assert chamadas == [
        (("2125575-44.2023.8.13.0000", "10000232125575004", "12345", "2024"), {"max_bytes": 2048})
    ]


def test_documento_tjmg_vira_recurso_binario_com_mime_real(monkeypatch):
    monkeypatch.setattr(
        mcp_server.importlib,
        "import_module",
        lambda _name: SimpleNamespace(
            EmbeddedResource=lambda **kwargs: kwargs,
            BlobResourceContents=lambda **kwargs: kwargs,
        ),
    )
    ole = bytes.fromhex("d0cf11e0a1b11ae1") + b"conteudo"
    recurso = mcp_server._documento_como_recurso_mcp(ole, "application/msword", "tjmg-2g-legado")
    assert recurso["resource"]["mimeType"] == "application/msword"
    assert recurso["resource"]["uri"].endswith(".doc")
    with pytest.raises(ValueError, match="documento válido"):
        mcp_server._documento_como_recurso_mcp(ole, "application/pdf", "tjmg-2g-legado")


def test_mcp_gerar_tabela_preserva_proveniencia_e_limita_payload(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    server = mcp_server.create_server()

    resultado = server.tools["gerar_tabela"](
        [
            {
                "id": "evt-1",
                "numero_cnj": "1076539-20.2019.8.26.0100",
                "fonte": "djen",
                "status_fonte": "partial",
            }
        ],
        ["id", "numero_cnj", "fonte", "status_fonte"],
    )

    assert resultado["status"] == "ok"
    assert resultado["row_count"] == 1
    assert resultado["rows"][0]["fonte"] == "djen"
    assert "status_fonte" in resultado["columns"]
    assert "partial" in resultado["csv"]
    with pytest.raises(ValueError, match="limite de 250 registros"):
        server.tools["gerar_tabela"]([{"id": n} for n in range(251)])


def test_mcp_gerar_tabela_enriquece_estado_da_fonte(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    server = mcp_server.create_server()

    resultado = server.tools["gerar_tabela"](
        [{"id": "evt-1", "fonte": "djen"}],
        source_status={"djen": {"status": "partial"}},
    )

    assert resultado["rows"][0]["fonte"] == "djen"
    assert resultado["rows"][0]["status_fonte"] == "partial"
    assert "partial" in resultado["csv"]


def test_mcp_eproc_2g_repassa_numero_e_timeout(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    resposta = {"status": "partial", "origem": {"grau": "2G"}}
    chamadas = []

    class Cliente:
        def consultar_eproc_tjsp_2g(self, numero, *, timeout, aguardar_desafio_interativo):
            chamadas.append((numero, timeout, aguardar_desafio_interativo))
            return resposta

    server = mcp_server.create_server(client=Cliente())
    resultado = server.tools["consultar_eproc_tjsp_2g"](
        "1001194-30.2024.8.26.0114", timeout=45, aguardar_desafio_interativo=True
    )
    assert resultado == resposta
    assert chamadas == [("1001194-30.2024.8.26.0114", 45, True)]


def test_mcp_tjrj_repassa_limite_de_paginas_volumosas(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    chamadas = []

    class Cliente:
        def consultar_tjrj_1g(self, numero, *, max_paginas_movimentos):
            chamadas.append((numero, max_paginas_movimentos))
            return {"status": "partial"}

    server = mcp_server.create_server(client=Cliente())
    resultado = server.tools["consultar_tjrj_1g"](
        "0089454-81.2003.8.19.0001", max_paginas_movimentos=75
    )

    assert resultado == {"status": "partial"}
    assert chamadas == [("0089454-81.2003.8.19.0001", 75)]


@pytest.mark.parametrize("limite", [True, 0, 501, 1.5, "10"])
def test_mcp_tjrj_rejeita_limites_de_paginacao_invalidos(monkeypatch, limite):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    class Cliente:
        def consultar_tjrj_1g(self, *args, **kwargs):
            pytest.fail("limite inválido não deve iniciar consulta TJRJ")

    server = mcp_server.create_server(client=Cliente())
    with pytest.raises(ValueError, match="max_paginas_movimentos"):
        server.tools["consultar_tjrj_1g"](
            "0089454-81.2003.8.19.0001", max_paginas_movimentos=limite
        )


def test_mcp_cposg_preserva_resultado_e_limite(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    numero = "0040759-80.2012.8.26.0100"
    resposta = {"status": "partial", "numero_consultado": numero, "resultados": []}

    def consultar(numero_recebido, *, max_paginas):
        assert (numero_recebido, max_paginas) == (numero, 3)
        return resposta

    monkeypatch.setattr(mcp_server.api, "consultar_esaj_tjsp_2g", consultar)
    server = mcp_server.create_server()
    assert server.tools["consultar_esaj_tjsp_2g"](numero, max_paginas=3) == resposta


def test_mcp_lote_rejeita_texto_no_lugar_de_lista_de_cnj(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(
        mcp_server.api,
        "extract_processes",
        lambda *args, **kwargs: pytest.fail("lote não deve consumir string como iterável"),
    )
    server = mcp_server.create_server()

    with pytest.raises(ValueError, match="lista"):
        server.tools["extrair_processos"]("1076539-20.2019.8.26.0100")


@pytest.mark.parametrize("max_workers", [True, 1.5, "2", None, 0, 5])
def test_mcp_lote_rejeita_max_workers_invalidos_antes_de_consultar(monkeypatch, max_workers):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(
        mcp_server.api,
        "extract_processes",
        lambda *args, **kwargs: pytest.fail("workers inválidos não devem iniciar o lote"),
    )
    server = mcp_server.create_server()

    with pytest.raises(ValueError, match="max_workers"):
        server.tools["extrair_processos"](["1076539-20.2019.8.26.0100"], max_workers=max_workers)


def test_pje_tjmg_mcp_consulta_documento_e_capacidades(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    calls = []

    class ClientePje:
        session = object()

        def consultar_pje_tjmg(self, numero, *, prazo_total):
            calls.append(("consulta", numero, self.session, prazo_total))
            return {"status": "partial", "dados_basicos": {"numero": numero}}

        def ler_documento_pje_tjmg(self, url, *, max_chars):
            calls.append(("leitura", url, self.session, max_chars))
            return {"status": "texto_extraido", "texto": "trecho"}

    monkeypatch.setattr(mcp_server, "NanoJudClient", ClientePje)
    server = mcp_server.create_server()

    consulta = server.tools["consultar_pje_tjmg"]("5060583-19.2021.8.13.0024", prazo_total=17)
    leitura = server.tools["ler_documento_pje_tjmg"](
        "https://pje-consulta-publica.tjmg.jus.br/documento", max_chars=600
    )

    assert consulta["status"] == "partial"
    assert leitura["texto"] == "trecho"
    assert calls == [
        ("consulta", "5060583-19.2021.8.13.0024", ClientePje.session, 17),
        (
            "leitura",
            "https://pje-consulta-publica.tjmg.jus.br/documento",
            ClientePje.session,
            600,
        ),
    ]
    assert "pje_tjmg" in server.tools["server_info"]()["sources"]
    with pytest.raises(ValueError, match="max_chars"):
        server.tools["ler_documento_pje_tjmg"]("url", max_chars=0)


def test_mcp_entrega_pdf_pje_como_recurso_binario(monkeypatch):
    from base64 import b64decode

    from mcp.types import EmbeddedResource

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    pdf = b"%PDF-1.7\nconteudo de teste"
    chamadas = []

    class ClientePje:
        def obter_pdf_pje_tjmg(self, url, *, max_bytes):
            chamadas.append((url, max_bytes))
            return pdf

    monkeypatch.setattr(mcp_server, "NanoJudClient", ClientePje)
    server = mcp_server.create_server()

    resultado = server.tools["obter_documento_pje_tjmg"](
        "https://pje-consulta-publica.tjmg.jus.br/documento", max_bytes=1024
    )

    assert isinstance(resultado, EmbeddedResource)
    assert resultado.resource.mimeType == "application/pdf"
    assert b64decode(resultado.resource.blob) == pdf
    assert chamadas == [("https://pje-consulta-publica.tjmg.jus.br/documento", 1024)]
    with pytest.raises(ValueError, match="max_bytes"):
        server.tools["obter_documento_pje_tjmg"](
            "https://pje-consulta-publica.tjmg.jus.br/documento", max_bytes=0
        )
    for limite in (1.5, "1024", None, True):
        with pytest.raises(ValueError, match="max_bytes"):
            server.tools["obter_documento_pje_tjmg"](
                "https://pje-consulta-publica.tjmg.jus.br/documento", max_bytes=limite
            )


def test_mcp_entrega_pdf_esaj_como_recurso_binario(monkeypatch):
    from base64 import b64decode

    from mcp.types import EmbeddedResource

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    pdf = b"%PDF-1.7\npeca de teste"
    chamadas = []

    class ClienteESAJ:
        def obter_pdf_esaj(self, numero, cd_documento, *, max_bytes):
            chamadas.append((numero, cd_documento, max_bytes))
            return pdf

    server = mcp_server.create_server(client=ClienteESAJ())

    resultado = server.tools["obter_documento_esaj"](
        "1076539-20.2019.8.26.0100", "123456", max_bytes=2048
    )

    assert isinstance(resultado, EmbeddedResource)
    assert resultado.resource.mimeType == "application/pdf"
    assert b64decode(resultado.resource.blob) == pdf
    assert str(resultado.resource.uri).startswith("nanojud://esaj/")
    assert chamadas == [("1076539-20.2019.8.26.0100", "123456", 2048)]
    for limite in (1.5, "2048", None, True):
        with pytest.raises(ValueError, match="max_bytes"):
            server.tools["obter_documento_esaj"](
                "1076539-20.2019.8.26.0100", "123456", max_bytes=limite
            )


def test_mcp_reutiliza_cliente_entre_consulta_esaj_e_download(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    numero = "1076539-20.2019.8.26.0100"
    eventos = []

    class ClienteESAJ:
        def get_extrato(self, numero_arg, **kwargs):
            eventos.append(("consulta", numero_arg))
            return {
                "status": "partial",
                "origem": {"movimentacoes_completas": False},
                "documentos": {"publicos_candidatos_unicos": [{"cd_documento": "doc-1"}]},
            }

        def obter_pdf_esaj(self, numero_arg, documento_id, *, max_bytes):
            eventos.append(("download", numero_arg, documento_id))
            assert any(item[0] == "consulta" for item in eventos)
            return b"%PDF-1.7\npeca"

    cliente = ClienteESAJ()
    monkeypatch.setattr(mcp_server, "NanoJudClient", lambda: cliente)
    server = mcp_server.create_server()

    consulta = server.tools["consultar_esaj"](numero, compacto=False)
    documento = server.tools["obter_documento_esaj"](numero, "doc-1")

    assert consulta["status"] == "partial"
    assert consulta["documentos"]["publicos_candidatos_unicos"][0]["cd_documento"] == "doc-1"
    assert documento.resource.mimeType == "application/pdf"
    assert eventos == [("consulta", numero), ("download", numero, "doc-1")]


def test_fastmcp_serializa_pdf_como_embedded_resource(monkeypatch):
    import asyncio

    from mcp.types import EmbeddedResource

    if mcp_server.FastMCP is None:
        pytest.skip("SDK MCP nao instalado")
    pdf = b"%PDF-1.7\nconteudo de teste"

    class ClientePje:
        def obter_pdf_pje_tjmg(self, url, *, max_bytes):
            return pdf

        def obter_pdf_esaj(self, numero, cd_documento, *, max_bytes):
            return pdf

    server = mcp_server.create_server(client=ClientePje())

    conteudo = asyncio.run(
        server._tool_manager.call_tool(
            "obter_documento_pje_tjmg",
            {"url": "https://pje-consulta-publica.tjmg.jus.br/documento"},
            convert_result=True,
        )
    )
    conteudo_esaj = asyncio.run(
        server._tool_manager.call_tool(
            "obter_documento_esaj",
            {"numero": "1076539-20.2019.8.26.0100", "cd_documento": "123456"},
            convert_result=True,
        )
    )

    # FastMCP versions can return just content or (content, structured metadata)
    # from this private tool-manager method. The public stdio contract is tested
    # separately below; here only inspect the serialized content blocks.
    for resultado in (conteudo, conteudo_esaj):
        blocks = resultado[0] if isinstance(resultado, tuple) else resultado
        assert len(blocks) == 1
        assert isinstance(blocks[0], EmbeddedResource)
        assert blocks[0].resource.mimeType == "application/pdf"


def test_stdio_entrega_pdf_esaj_como_recurso_binario(tmp_path):
    import asyncio
    import sys
    from base64 import b64decode
    from pathlib import Path

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.types import EmbeddedResource

    if mcp_server.FastMCP is None:
        pytest.skip("SDK MCP nao instalado")

    script = tmp_path / "nanojud_mcp_fixture.py"
    script.write_text(
        """
from nanojud.mcp_server import create_server

class FakeClient:
    def obter_pdf_esaj(self, numero, cd_documento, *, max_bytes):
        return b"%PDF-1.7\\nfixture-stdio"

create_server(client=FakeClient()).run(transport="stdio")
""",
        encoding="utf-8",
    )
    src_path = str(Path(__file__).resolve().parents[1] / "src")

    async def consultar_recurso():
        parametros = StdioServerParameters(
            command=sys.executable,
            args=[str(script)],
            env={"PYTHONPATH": src_path},
            cwd=str(tmp_path),
        )
        async with stdio_client(parametros) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as sessao:
                await sessao.initialize()
                return await sessao.call_tool(
                    "obter_documento_esaj",
                    {"numero": "1076539-20.2019.8.26.0100", "cd_documento": "fixture"},
                )

    resultado = asyncio.run(consultar_recurso())

    assert resultado.isError is False
    assert len(resultado.content) == 1
    recurso = resultado.content[0]
    assert isinstance(recurso, EmbeddedResource)
    assert recurso.resource.mimeType == "application/pdf"
    assert b64decode(recurso.resource.blob) == b"%PDF-1.7\nfixture-stdio"


def test_mcp_reutiliza_sessao_entre_consulta_e_leitura_pje(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    sessao = object()
    chamadas = []

    class ClientePje:
        def __init__(self):
            self.session = sessao

        def consultar_pje_tjmg(self, numero, *, prazo_total):
            chamadas.append(("consulta", numero, self.session, prazo_total))
            return {"status": "partial"}

        def ler_documento_pje_tjmg(self, url, *, max_chars):
            chamadas.append(("leitura", url, self.session, max_chars))
            return {"status": "texto_extraido"}

    monkeypatch.setattr(mcp_server, "NanoJudClient", ClientePje)
    monkeypatch.setattr(
        mcp_server.api,
        "consultar_pje_tjmg",
        lambda *args, **kwargs: pytest.fail("consulta deve usar o cliente MCP persistente"),
    )
    monkeypatch.setattr(
        mcp_server.api,
        "ler_documento_pje_tjmg",
        lambda *args, **kwargs: pytest.fail("leitura deve usar o cliente MCP persistente"),
    )
    server = mcp_server.create_server()

    server.tools["consultar_pje_tjmg"]("5060583-19.2021.8.13.0024")
    server.tools["ler_documento_pje_tjmg"]("https://pje-consulta-publica.tjmg.jus.br/documento")

    assert chamadas == [
        ("consulta", "5060583-19.2021.8.13.0024", sessao, 60.0),
        ("leitura", "https://pje-consulta-publica.tjmg.jus.br/documento", sessao, 4000),
    ]


def test_mcp_baixa_pdf_pje_em_diretorio_temporario_controlado(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    diretorio = tmp_path / "nanojud_pje_documento_isolado"

    def criar_diretorio(*, prefix):
        diretorio.mkdir()
        return str(diretorio)

    monkeypatch.setattr(tempfile, "mkdtemp", criar_diretorio)
    chamadas = []

    class ClientePje:
        session = object()

        def baixar_documento_pje_tjmg(self, url, destino, *, sobrescrever=False):
            chamadas.append((url, destino, self.session, sobrescrever))
            return {"status": "baixado", "arquivo": str(destino), "bytes": 123}

    monkeypatch.setattr(mcp_server, "NanoJudClient", ClientePje)
    server = mcp_server.create_server()
    ferramenta = server.tools["baixar_documento_pje_tjmg"]

    resultado = ferramenta(
        "https://pje-consulta-publica.tjmg.jus.br/pje/ConsultaPublica/"
        "DetalheProcessoConsultaPublica/documentoSemLoginHTML.seam?ca=publico"
    )

    assert resultado == {
        "status": "baixado",
        "arquivo": str(diretorio / "documento.pdf"),
        "bytes": 123,
    }
    assert len(chamadas) == 1
    url, destino, sessao, sobrescrever = chamadas[0]
    assert url.endswith("?ca=publico")
    assert destino == diretorio / "documento.pdf"
    assert destino.name == "documento.pdf"
    assert sessao is ClientePje.session
    assert sobrescrever is False


def test_mcp_limpa_diretorio_pje_se_download_falhar(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    diretorio = tmp_path / "nanojud_pje_documento_falhou"

    def criar_diretorio(*, prefix):
        diretorio.mkdir()
        return str(diretorio)

    monkeypatch.setattr(tempfile, "mkdtemp", criar_diretorio)

    class ClientePje:
        def baixar_documento_pje_tjmg(self, url, destino, *, sobrescrever=False):
            raise ValueError("URL de documento inválida")

    monkeypatch.setattr(mcp_server, "NanoJudClient", ClientePje)
    server = mcp_server.create_server()

    with pytest.raises(ValueError, match="URL de documento inválida"):
        server.tools["baixar_documento_pje_tjmg"]("url-inválida")

    assert not diretorio.exists()


def test_mcp_limpa_apenas_diretorios_nanojud_antigos(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(mcp_server.tempfile, "gettempdir", lambda: str(tmp_path))
    antigos = tmp_path / "nanojud_autos_execucao_antiga"
    recente = tmp_path / "nanojud_pje_documento_recente"
    arquivo_recente = tmp_path / "nanojud_autos_arquivo_recente"
    prefixo_alheio = tmp_path / "nanojud_autos_criado_por_terceiro"
    alheio = tmp_path / "outro_aplicativo_documento"
    for diretorio in (antigos, recente, arquivo_recente, prefixo_alheio, alheio):
        diretorio.mkdir()
        (diretorio / "documento.pdf").write_bytes(b"%PDF")
    (antigos / ".nanojud-owned").write_text("nanojud-temporary-documents-v1", encoding="ascii")
    for diretorio in (recente, arquivo_recente):
        (diretorio / ".nanojud-owned").write_text(
            "nanojud-temporary-documents-v1", encoding="ascii"
        )
    instante_antigo = 1_700_000_000
    import os

    os.utime(antigos, (instante_antigo, instante_antigo))
    os.utime(antigos / "documento.pdf", (instante_antigo, instante_antigo))
    os.utime(antigos / ".nanojud-owned", (instante_antigo, instante_antigo))
    os.utime(arquivo_recente, (instante_antigo, instante_antigo))
    os.utime(prefixo_alheio, (instante_antigo, instante_antigo))
    os.utime(prefixo_alheio / "documento.pdf", (instante_antigo, instante_antigo))
    os.utime(alheio, (instante_antigo, instante_antigo))
    server = mcp_server.create_server()

    resultado = server.tools["limpar_documentos_temporarios"](min_age_hours=24)

    assert resultado["status"] == "ok"
    assert resultado["deleted_directories"] == 1
    assert resultado["skipped_recent"] == 2
    assert not antigos.exists()
    assert prefixo_alheio.exists()
    assert recente.exists()
    assert arquivo_recente.exists()
    assert alheio.exists()
    for idade_invalida in (0, 8761, True, 1.5, "24"):
        with pytest.raises(ValueError, match="min_age_hours"):
            server.tools["limpar_documentos_temporarios"](min_age_hours=idade_invalida)


def test_mcp_lote_pje_preserva_estado_parcial_da_fonte(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    chamadas = []
    numero = "5060583-19.2021.8.13.0024"

    def extrair_processos(numeros, **kwargs):
        chamadas.append((numeros, kwargs))
        return {
            "schema_version": "1.0",
            "total": 1,
            "succeeded": 0,
            "partial": 1,
            "failed": 0,
            "items": [
                {
                    "index": 0,
                    "input": numero,
                    "numero_cnj": numero,
                    "status": "partial",
                    "result": {
                        "schema_version": "1.0",
                        "package_version": "0.5.3",
                        "status": "partial",
                        "numero_cnj": numero,
                        "sources": ["pje_tjmg"],
                        "extracted_at": "2026-11-09T00:00:00Z",
                        "data": {
                            "pje_tjmg": {
                                "status": "partial",
                                "origem": {
                                    "movimentacoes_completas": False,
                                    "documentos_completos": False,
                                },
                            }
                        },
                        "timeline": [],
                        "warnings": ["paginação pendente"],
                        "errors": [],
                        "source_status": {"pje_tjmg": {"status": "partial"}},
                    },
                }
            ],
        }

    monkeypatch.setattr(mcp_server.api, "extract_processes", extrair_processos)
    server = mcp_server.create_server()

    resumo = server.tools["extrair_processos"](
        [numero], sources=["pje_tjmg"], max_workers=1, compacto=False
    )

    assert chamadas[0][0] == [numero]
    assert chamadas[0][1]["sources"] == ("pje_tjmg",)
    assert resumo["partial"] == 1
    assert resumo["items"][0]["status"] == "partial"
    assert resumo["items"][0]["result"]["source_status"]["pje_tjmg"]["status"] == "partial"


def test_mcp_autentica_esaj_no_navegador_e_substitui_cliente(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(
        mcp_server.api,
        "extract_processes",
        lambda *args, **kwargs: pytest.fail("lote autenticado não deve ignorar o cliente"),
    )
    monkeypatch.setattr(
        mcp_server.api,
        "extract_process",
        lambda *args, **kwargs: pytest.fail("extração autenticada não deve ignorar o cliente"),
    )
    sessao = object()
    chamadas = []

    class ClienteAutenticado:
        def __init__(self, config=None, *, logger=None, session=None, senha_processo_provider=None):
            from nanojud.config import NanoJudConfig

            self.config = config or NanoJudConfig()
            self.logger = logger
            self.session = session or sessao
            self.senha_processo_provider = senha_processo_provider

        def get_extrato(self, numero, **kwargs):
            chamadas.append((numero, kwargs, self.session))
            return {"dados_basicos": {"numero": numero}, "movimentacoes": []}

        def extract_processes(self, numeros, **kwargs):
            chamadas.append(("lote", numeros, kwargs, self.session))
            return {
                "schema_version": "1.0",
                "total": len(numeros),
                "succeeded": len(numeros),
                "partial": 0,
                "failed": 0,
                "items": [],
            }

        def extract_process(self, numero, **kwargs):
            chamadas.append(("unitario", numero, kwargs, self.session))
            return {"numero_cnj": numero, "status": "ok", "timeline": []}

    monkeypatch.setattr(mcp_server, "NanoJudClient", ClienteAutenticado)
    monkeypatch.setattr(
        mcp_server.autenticacao,
        "autenticar_esaj_no_navegador",
        lambda *, timeout_login: chamadas.append(timeout_login) or sessao,
    )
    server = mcp_server.create_server()

    resultado = server.tools["autenticar_esaj"](timeout_login=240)

    assert chamadas == [240]
    assert resultado == {
        "status": "ok",
        "esaj_session_configured": True,
        "esaj_session_authentication": "verified_by_official_login",
        "message": "Sessão autenticada mantida apenas na memória deste servidor MCP.",
    }
    assert server.tools["server_info"]()["esaj_session_configured"] is True
    assert (
        server.tools["server_info"]()["esaj_session_authentication"] == "verified_by_official_login"
    )

    numero = "1076539-20.2019.8.26.0100"
    extrato = server.tools["consultar_esaj"](numero, compacto=False)
    assert extrato["dados_basicos"]["numero"] == numero
    assert chamadas[-1][0] == numero
    assert chamadas[-1][2] is sessao

    lote = server.tools["extrair_processos"]([numero], max_workers=1, compacto=False)
    assert lote["succeeded"] == 1
    assert chamadas[-1][0] == "lote"
    assert chamadas[-1][1] == [numero]
    assert chamadas[-1][2]["max_workers"] == 1


def test_mcp_login_preserva_configuracao_e_callback_de_senha_do_cliente_host(monkeypatch):
    from nanojud import autenticacao, esaj, extraction
    from nanojud.client import NanoJudClient
    from nanojud.config import NanoJudConfig

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    sessao_autenticada = object()
    senha_provider = lambda numero, documentos: "segredo"  # noqa: E731
    cliente_host = NanoJudClient(
        config=NanoJudConfig(
            timeout=7.0,
            rate_limit_interval=2.5,
            pausa_paginas=0.1,
            datajud_api_key="api-key-host",
        ),
        senha_processo_provider=senha_provider,
    )
    chamadas: dict[str, object] = {}
    monkeypatch.setattr(
        autenticacao,
        "autenticar_esaj_no_navegador",
        lambda *, timeout_login: sessao_autenticada,
    )
    monkeypatch.setattr(
        esaj,
        "montar_extrato",
        lambda numero, **kwargs: (
            chamadas.update(kwargs) or {"dados_basicos": {"numero": numero}, "movimentacoes": []}
        ),
    )
    monkeypatch.setattr(
        extraction,
        "extract_process",
        lambda numero, **kwargs: chamadas.update(kwargs) or {"numero_cnj": numero, "status": "ok"},
    )
    server = mcp_server.create_server(client=cliente_host)

    server.tools["autenticar_esaj"]()
    server.tools["consultar_esaj"]("1076539-20.2019.8.26.0100", compacto=False)

    assert chamadas["session"] is sessao_autenticada
    assert chamadas["timeout"] == 7.0
    assert chamadas["pausa_paginas"] == 0.1
    assert chamadas["senha_processo_provider"] is senha_provider

    server.tools["extrair_processo"](
        "1076539-20.2019.8.26.0100", sources=["datajud"], compacto=False
    )
    assert chamadas["datajud_api_key"] == "api-key-host"


def test_ferramentas_datajud_e_djen_usam_cliente_configurado_quando_fornecido(monkeypatch):
    from nanojud.client import NanoJudClient

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(
        mcp_server.api,
        "consultar_datajud",
        lambda *args, **kwargs: pytest.fail("DataJud ignorou o cliente configurado"),
    )
    monkeypatch.setattr(
        mcp_server.api,
        "consultar_djen",
        lambda *args, **kwargs: pytest.fail("DJEN ignorou o cliente configurado"),
    )
    cliente = NanoJudClient()
    chamadas = []
    monkeypatch.setattr(
        cliente,
        "consultar_datajud",
        lambda numero, **kwargs: (
            chamadas.append(("datajud", numero, kwargs))
            or {
                "numero": numero,
                "include_raw": kwargs["include_raw"],
                "api_key": kwargs["api_key"],
            }
        ),
    )
    monkeypatch.setattr(
        cliente,
        "consultar_djen_detalhado",
        lambda numero, data_inicio="": (
            chamadas.append(("djen", numero, data_inicio))
            or {
                "status": "ok",
                "completo": True,
                "paginas": 1,
                "comunicacoes": [{"numero": numero, "data_inicio": data_inicio}],
                "avisos": [],
            }
        ),
    )
    server = mcp_server.create_server(client=cliente)

    datajud = server.tools["consultar_datajud"](
        "1076539-20.2019.8.26.0100",
        True,
        "segredo-api",
        compacto=False,
        prazo_total=23,
    )
    djen = server.tools["consultar_djen"]("1076539-20.2019.8.26.0100", "2026-01-01")

    assert datajud["api_key"] == "segredo-api"
    assert djen["comunicacoes"][0]["data_inicio"] == "2026-01-01"
    assert djen["completo"] is True
    assert djen["status"] == "ok"
    assert chamadas == [
        (
            "datajud",
            "1076539-20.2019.8.26.0100",
            {"include_raw": True, "api_key": "segredo-api", "prazo_total": 23},
        ),
        ("djen", "1076539-20.2019.8.26.0100", "2026-01-01"),
    ]


def test_gerar_timeline_usa_cliente_esaj_autenticado(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    numero = "1076539-20.2019.8.26.0100"
    chamadas = []

    class ClienteESAJ:
        def extract_process(self, numero_arg, **kwargs):
            chamadas.append((numero_arg, kwargs))
            return {
                "schema_version": "1.0",
                "package_version": "0.5.3",
                "status": "ok",
                "numero_cnj": numero_arg,
                "sources": ["esaj"],
                "source_status": {},
                "timeline": [{"data": "2026-11-01", "fonte": "esaj"}],
                "warnings": [],
                "errors": [],
            }

    monkeypatch.setattr(
        mcp_server.api,
        "extract_process",
        lambda *args, **kwargs: pytest.fail("timeline deve reutilizar o cliente e a sessão"),
    )
    server = mcp_server.create_server(client=ClienteESAJ())

    resultado = server.tools["gerar_timeline"](numero, sources=["esaj"])

    assert resultado["timeline"][0]["fonte"] == "esaj"
    assert chamadas[0][0] == numero
    assert chamadas[0][1]["sources"] == ("esaj",)


def test_mcp_autenticacao_valida_timeout_antes_de_abrir_navegador(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(
        mcp_server.autenticacao,
        "autenticar_esaj_no_navegador",
        lambda **kwargs: pytest.fail("não deve iniciar o navegador"),
    )
    server = mcp_server.create_server()

    with pytest.raises(ValueError, match="30 e 1800"):
        server.tools["autenticar_esaj"](timeout_login=29)
    for timeout in (30.5, "30", None, True, 1801, 10**1000):
        with pytest.raises(ValueError, match="30 e 1800"):
            server.tools["autenticar_esaj"](timeout_login=timeout)


def test_create_server_real_quando_sdk_mcp_instalado():
    if mcp_server.FastMCP is None:
        pytest.skip("SDK MCP nao instalado")

    server = mcp_server.create_server()

    assert type(server).__name__ == "FastMCP"


@pytest.mark.parametrize("valor", [0, -1, 1.5, "3", None, True])
def test_mcp_leitura_documental_rejeita_limite_invalido_antes_de_consultar(monkeypatch, valor):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    server = mcp_server.create_server(client=object())

    with pytest.raises(ValueError, match="limite"):
        server.tools["ler_documentos_publicos"]("1076539-20.2019.8.26.0100", limite=valor)


@pytest.mark.parametrize("valor", [0, -1, 1.5, "3000", None, True, 10001])
def test_mcp_leitura_documental_rejeita_max_chars_invalido_antes_de_consultar(monkeypatch, valor):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    server = mcp_server.create_server(client=object())

    with pytest.raises(ValueError, match="max_chars"):
        server.tools["ler_documentos_publicos"]("1076539-20.2019.8.26.0100", max_chars=valor)


@pytest.mark.parametrize("valor", [1.5, "3", None, True, 10001])
def test_mcp_leitura_pje_rejeita_tipo_ou_limite_invalido(monkeypatch, valor):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    server = mcp_server.create_server(client=object())

    with pytest.raises(ValueError, match="max_chars"):
        server.tools["ler_documento_pje_tjmg"]("https://pje.example/documento", max_chars=valor)


@pytest.mark.parametrize(
    ("kwargs", "campo"),
    [
        ({"max_documentos_por_processo": True}, "max_documentos_por_processo"),
        ({"max_documentos_por_processo": 1.5}, "max_documentos_por_processo"),
        ({"max_chars": True}, "max_chars"),
        ({"max_chars": 1.5}, "max_chars"),
        ({"ler_documentos": 1}, "ler_documentos"),
    ],
)
def test_mcp_autos_em_lote_rejeita_tipos_invalidos_antes_de_criar_pasta(monkeypatch, kwargs, campo):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(
        mcp_server.tempfile,
        "mkdtemp",
        lambda **opcoes: pytest.fail("Parâmetros inválidos não devem criar pasta"),
    )
    server = mcp_server.create_server(client=object())

    with pytest.raises(ValueError, match=campo):
        server.tools["consultar_autos_em_lote"](["1076539-20.2019.8.26.0100"], **kwargs)


def test_ferramentas_mcp_basicas(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    server = mcp_server.create_server()

    info = server.tools["server_info"]()
    validacao = server.tools["validar_cnj"]("1076539-20.2019.8.26.0100")
    numeros = server.tools["extrair_numeros_cnj_de_texto"]("Processo 1076539-20.2019.8.26.0100")

    assert info["transport"] == "stdio"
    assert info["scope"] == "local_extraction_scoped_output"
    assert info["esaj_session_authentication"] == "not_configured"
    assert validacao["digitos"] == "10765392020198260100"
    assert numeros["count"] == 1


def test_server_info_nao_confunde_cliente_fornecido_com_login_verificado(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    cliente_fornecido = object()

    server = mcp_server.create_server(client=cliente_fornecido)

    info = server.tools["server_info"]()
    assert info["esaj_session_configured"] is True
    assert info["esaj_session_authentication"] == "host_supplied_unverified"


def test_fontes_mcp_ausentes_usam_padrao_e_lista_vazia_e_rejeitada():
    assert mcp_server._normalizar_sources(None) == ("esaj", "datajud", "djen")
    assert mcp_server._normalizar_sources(["mni"]) == ("mni",)

    with pytest.raises(ValueError, match="Selecione ao menos uma fonte"):
        mcp_server._normalizar_sources([])


def test_ferramenta_mcp_rejeita_selecao_de_fontes_vazia(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    server = mcp_server.create_server()

    with pytest.raises(ValueError, match="Selecione ao menos uma fonte"):
        server.tools["extrair_processo"]("1076539-20.2019.8.26.0100", sources=[])


def test_ferramenta_mcp_repassa_selecao_mni_a_api(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    chamadas = {}

    def extrair(numero, **kwargs):
        chamadas.update(numero=numero, **kwargs)
        return {"status": "ok", "sources": ["mni"]}

    monkeypatch.setattr(mcp_server.api, "extract_process", extrair)
    server = mcp_server.create_server()

    resultado = server.tools["extrair_processo"](
        "1001194-30.2024.8.26.0114", sources=["mni"], compacto=False
    )

    assert resultado == {"status": "ok", "sources": ["mni"]}
    assert chamadas["sources"] == ("mni",)


def test_ferramentas_mcp_delegam_para_api(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    class ClienteDocumentos:
        def get_extrato(self, numero, salvar_html=False, **kwargs):
            return {
                "numero": numero,
                "salvar_html": salvar_html,
                "dados_basicos": {"numero": numero},
                "documentos": {"publicos_candidatos_unicos": [{"cd_documento": "1"}]},
            }

    monkeypatch.setattr(mcp_server, "NanoJudClient", ClienteDocumentos)
    monkeypatch.setattr(
        mcp_server.api,
        "get_extrato",
        lambda numero, salvar_html=False, **kwargs: {
            "numero": numero,
            "salvar_html": salvar_html,
            "dados_basicos": {"numero": numero},
            "documentos": {"publicos_candidatos_unicos": [{"cd_documento": "1"}]},
        },
    )
    monkeypatch.setattr(
        mcp_server.api,
        "consultar_datajud",
        lambda numero, include_raw=False, api_key=None, prazo_total=60.0: {
            "numero": numero,
            "include_raw": include_raw,
            "api_key": api_key,
            "prazo_total": prazo_total,
        },
    )
    monkeypatch.setattr(
        mcp_server.api,
        "consultar_djen",
        lambda numero, data_inicio="": [{"numero": numero, "data_inicio": data_inicio}],
    )
    monkeypatch.setattr(
        mcp_server.api,
        "consultar_djen_detalhado",
        lambda numero, data_inicio="": {
            "status": "ok",
            "completo": True,
            "paginas": 1,
            "comunicacoes": [{"numero": numero, "data_inicio": data_inicio}],
            "avisos": [],
        },
    )
    monkeypatch.setattr(
        mcp_server.api,
        "extract_process",
        lambda numero, **kwargs: {
            "schema_version": "1.0",
            "package_version": "0.5.0",
            "status": "ok",
            "numero_cnj": numero,
            "sources": list(kwargs["sources"]),
            "source_status": {"datajud": {"status": "ok", "records": 2}},
            "timeline": [
                {"data": "2020-01-01", "fonte": "datajud", "texto": "antigo"},
                {"data": "2026-07-31", "fonte": "datajud", "texto": "recente"},
            ],
            "warnings": [],
            "errors": [],
            "kwargs": kwargs,
        },
    )
    monkeypatch.setattr(
        mcp_server.api,
        "extract_processes",
        lambda numeros, **kwargs: {
            "schema_version": "1.0",
            "total": len(numeros),
            "succeeded": 1,
            "partial": 0,
            "failed": 0,
            "items": [
                {
                    "index": 0,
                    "input": numeros[0],
                    "status": "ok",
                    "result": {
                        "schema_version": "1.0",
                        "package_version": "0.5.0",
                        "status": "ok",
                        "numero_cnj": numeros[0],
                        "sources": ["datajud"],
                        "extracted_at": "2026-01-01T00:00:00Z",
                        "data": {"datajud": {"movimentos": [{"payload_origem": {"x": 1}}]}},
                        "timeline": [],
                        "warnings": [],
                        "errors": [],
                        "source_status": {},
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        mcp_server.api,
        "iter_extract_dockets",
        lambda numeros, **kwargs: iter(
            [{"index": 0, "input": numeros[0], "status": "no_documents", "document_candidates": 0}]
        ),
    )
    monkeypatch.setattr(
        mcp_server.api,
        "ler_pecas",
        lambda extrato, limite=3, max_chars=4000: [
            {"cd_documento": "1", "status": "texto_extraido", "max_chars": max_chars}
        ],
    )
    server = mcp_server.create_server()

    assert server.tools["consultar_esaj"]("1076539-20.2019.8.26.0100", True)["salvar_html"] is True
    datajud = server.tools["consultar_datajud"](
        "1076539-20.2019.8.26.0100", True, "abc", prazo_total=19
    )
    assert datajud["api_key"] == "abc"
    assert datajud["prazo_total"] == 19
    djen = server.tools["consultar_djen"]("1076539-20.2019.8.26.0100", "2026-01-01")
    assert djen["count"] == 1
    assert djen["comunicacoes"][0]["data_inicio"] == "2026-01-01"
    assert djen["completo"] is True

    envelope = server.tools["extrair_processo"](
        "1076539-20.2019.8.26.0100",
        sources=["datajud", "djen"],
        include_raw=True,
    )
    lote = server.tools["extrair_processos"](
        ["1076539-20.2019.8.26.0100"], sources=["datajud"], limite_movimentacoes=0
    )
    autos = server.tools["consultar_autos_em_lote"](
        ["1076539-20.2019.8.26.0100"], ler_documentos=True
    )
    linha = server.tools["gerar_timeline"](
        "1076539-20.2019.8.26.0100",
        sources=["datajud"],
        limit=1,
        recent_first=True,
        include_text=False,
    )
    documentos = server.tools["ler_documentos_publicos"](
        "1076539-20.2019.8.26.0100",
        limite=1,
        max_chars=700,
    )

    assert envelope["kwargs"]["sources"] == ("datajud", "djen")
    assert envelope["kwargs"]["include_raw"] is True
    assert lote["total"] == 1
    assert lote["items"][0]["result"]["timeline"] == []
    assert autos["total"] == 1
    assert autos["succeeded"] == 1
    assert linha["source_status"]["datajud"]["records"] == 2
    assert linha["timeline"] == [{"data": "2026-07-31", "fonte": "datajud"}]
    assert documentos["count"] == 1
    assert documentos["documentos"][0]["max_chars"] == 700


def test_mcp_leitura_documental_indica_incompletude_e_limites(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    def obter_extrato(numero, *, inspecionar_pecas, limite_inspecao_pecas):
        assert inspecionar_pecas is True
        assert limite_inspecao_pecas == 1
        return {
            "status": "ok",
            "dados_basicos": {"numero": numero},
            "origem": {
                "movimentacoes_completas": False,
                "aviso_movimentacoes": "Paginação interrompida antes do fim.",
            },
            "movimentacoes": [],
            "documentos": {
                "publicos_candidatos_unicos": [
                    {"cd_documento": "doc-1"},
                    {"cd_documento": "doc-2"},
                ],
                "restritos_por_senha_unicos": [{"cd_documento": "privado-1"}],
            },
        }

    monkeypatch.setattr(mcp_server.api, "get_extrato", obter_extrato)
    monkeypatch.setattr(
        mcp_server.api,
        "ler_pecas",
        lambda extrato, *, limite, max_chars: [
            {"cd_documento": "doc-1", "status": "texto_extraido", "texto": "trecho"}
        ],
    )
    server = mcp_server.create_server()

    resultado = server.tools["ler_documentos_publicos"]("1076539-20.2019.8.26.0100", limite=1)

    assert resultado["status"] == "partial"
    assert resultado["movimentacoes_completas"] is False
    assert resultado["total_public_candidates"] == 2
    assert resultado["restricted_documents"] == 1
    assert resultado["count"] == 1
    assert any("Paginação interrompida" in aviso for aviso in resultado["warnings"])
    assert any("limitados a 1 de 2" in aviso for aviso in resultado["warnings"])


def test_mcp_leitura_sem_documentos_so_com_listagem_completa(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    monkeypatch.setattr(
        mcp_server.api,
        "get_extrato",
        lambda numero, **kwargs: {
            "status": "ok",
            "dados_basicos": {"numero": numero},
            "origem": {"movimentacoes_completas": True},
            "documentos": {
                "publicos_candidatos_unicos": [],
                "restritos_por_senha_unicos": [],
            },
        },
    )
    monkeypatch.setattr(mcp_server.api, "ler_pecas", lambda *args, **kwargs: [])
    server = mcp_server.create_server()

    resultado = server.tools["ler_documentos_publicos"]("1076539-20.2019.8.26.0100")

    assert resultado["status"] == "no_documents"
    assert resultado["count"] == 0
    assert resultado["total_public_candidates"] == 0
    assert resultado["restricted_documents"] == 0
    assert resultado["movimentacoes_completas"] is True


def test_mcp_autos_pje_separa_arquivos_obtidos_de_falhas(monkeypatch, tmp_path):
    import tempfile

    from nanojud import pje_tjmg

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    def criar_diretorio(prefix):
        diretorio = tmp_path / prefix
        diretorio.mkdir()
        return str(diretorio)

    monkeypatch.setattr(tempfile, "mkdtemp", criar_diretorio)

    def consultar(numero, *, session, timeout, prazo_total):
        return {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True, "documentos_completos": True},
            "documentos": {
                "publicos_candidatos_unicos": [
                    {"cd_documento": "doc-1", "titulo": "Indisponível", "href": "https://pje/doc1"},
                    {"cd_documento": "doc-2", "titulo": "Obtido", "href": "https://pje/doc2"},
                ]
            },
        }

    def baixar(url, destino, **kwargs):
        if url.endswith("doc1"):
            return {"status": "error", "mensagem": "PDF indisponível"}
        return {"status": "baixado", "arquivo": str(destino), "bytes": 42}

    monkeypatch.setattr(pje_tjmg, "consultar_processo", consultar)
    monkeypatch.setattr(pje_tjmg, "baixar_documento_publico", baixar)
    server = mcp_server.create_server()

    result = server.tools["consultar_autos_em_lote"](
        ["5060583-19.2021.8.13.0024"], max_documentos_por_processo=2
    )

    item = result["items"][0]
    assert result["partial"] == 1
    assert result["failed"] == 0
    assert [documento["cd_documento"] for documento in item["downloaded"]] == ["doc-2"]
    assert [status["status"] for status in item["document_statuses"]] == ["error", "baixado"]


def test_mcp_autos_lote_remove_pasta_temporaria_se_iteracao_falhar(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    diretorio = tmp_path / "nanojud_autos_falha"

    def criar_diretorio(*, prefix):
        assert prefix == "nanojud_autos_"
        diretorio.mkdir()
        return str(diretorio)

    def falhar_lote(*args, **kwargs):
        raise RuntimeError("falha sintetica durante a extração")

    monkeypatch.setattr(mcp_server.tempfile, "mkdtemp", criar_diretorio)
    monkeypatch.setattr(mcp_server.api, "iter_extract_dockets", falhar_lote)
    server = mcp_server.create_server()

    with pytest.raises(RuntimeError, match="falha sintetica"):
        server.tools["consultar_autos_em_lote"](["1076539-20.2019.8.26.0100"])

    assert not diretorio.exists()


def test_mcp_autos_leitura_memoria_preserva_diretorio_temporario_compartilhado(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)
    sentinela = tmp_path / "arquivo-alheio.txt"
    sentinela.write_text("preservar", encoding="utf-8")

    def falhar_lote(*args, **kwargs):
        raise RuntimeError("falha sintetica durante a leitura")

    monkeypatch.setattr(mcp_server.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(mcp_server.api, "iter_extract_dockets", falhar_lote)
    server = mcp_server.create_server()

    with pytest.raises(RuntimeError, match="falha sintetica"):
        server.tools["consultar_autos_em_lote"](["1076539-20.2019.8.26.0100"], ler_documentos=True)

    assert tmp_path.is_dir()
    assert sentinela.read_text(encoding="utf-8") == "preservar"


def test_mcp_autos_lote_misto_preserva_contadores_e_estados(monkeypatch, tmp_path):
    from nanojud import api, pje_tjmg

    monkeypatch.setattr(mcp_server, "FastMCP", FakeFastMCP)

    def criar_diretorio(prefix):
        diretorio = tmp_path / prefix
        diretorio.mkdir()
        return str(diretorio)

    monkeypatch.setattr(tempfile, "mkdtemp", criar_diretorio)

    def obter_extrato(numero, **kwargs):
        restrito = numero == "0015020-23.2010.8.26.0053"
        return {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True},
            "documentos": {
                "publicos_candidatos_unicos": []
                if restrito
                else [{"cd_documento": "publico-1", "download_status": "baixado"}],
                "restritos_por_senha_unicos": [{"cd_documento": "restrito-1"}] if restrito else [],
                "baixados": []
                if restrito
                else [{"cd_documento": "publico-1", "status": "baixado"}],
            },
        }

    def pje_indisponivel(*args, **kwargs):
        from nanojud.exceptions import ConsultaIndisponivel

        raise ConsultaIndisponivel("PJe temporariamente indisponível")

    monkeypatch.setattr(api, "get_extrato", obter_extrato)
    monkeypatch.setattr(pje_tjmg, "consultar_processo", pje_indisponivel)
    server = mcp_server.create_server()

    result = server.tools["consultar_autos_em_lote"](
        [
            "1076539-20.2019.8.26.0100",
            "0015020-23.2010.8.26.0053",
            "5060583-19.2021.8.13.0024",
        ],
        max_documentos_por_processo=1,
    )

    assert (result["total"], result["succeeded"], result["partial"], result["failed"]) == (
        3,
        1,
        1,
        1,
    )
    assert [item["status"] for item in result["items"]] == ["ok", "partial", "error"]
    assert result["items"][0]["downloaded"][0]["cd_documento"] == "publico-1"
    assert result["items"][1]["restricted_documents"] == 1
    assert result["items"][2]["error"]["type"] == "ConsultaIndisponivel"


def test_main_executa_servidor(monkeypatch):
    server = FakeFastMCP("nanojud")
    monkeypatch.setattr(mcp_server, "create_server", lambda: server)

    mcp_server.main()

    assert server.ran is True
    assert server.run_kwargs == {"transport": "stdio"}
