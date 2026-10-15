import threading
import time

from bs4 import BeautifulSoup

from nanojud import api, cli, compactacao, esaj, extraction, mcp_server
from nanojud.timeline import limite_movimentacoes_para

from .test_esaj_movimentacoes_ajax import FakeSession

TJSP = "1076539-20.2019.8.26.0100"
TJRJ = "0032991-06.2012.8.19.0066"


# --- partes, situação e etiquetas -------------------------------------------------------


def _tabela_partes(*linhas):
    corpo = "".join(
        f'<tr><td class="label"><span class="tipoDeParticipacao">{tipo}</span></td>'
        f'<td class="nomeParteEAdvogado">{nome}<br/><span>Advogado: </span>{adv}</td></tr>'
        for tipo, nome, adv in linhas
    )
    return f'<table id="tablePartesPrincipais">{corpo}</table>'


def test_partes_todas_cai_para_principais_quando_nao_ha_tabela_completa():
    html = _tabela_partes(("Reqte", "Ana", "Dr. Bruno"), ("Reqdo", "Município", "Dra. Carla"))

    partes = esaj.extrair_partes(BeautifulSoup(html, "html.parser"))

    assert [p["nomes"] for p in partes["todas"]] == [["Ana"], ["Município"]]
    assert partes["todas"] == partes["principais"]
    assert partes["polo_ativo"][0]["advogados"] == ["Dr. Bruno"]


def test_dados_basicos_trazem_situacao_e_etiquetas():
    html = """
    <div id="containerDadosPrincipaisProcesso">
      <span id="numeroProcesso">1076539-20.2019.8.26.0100</span>
      <span class="unj-tag" id="labelSituacaoProcesso">Extinto</span>
      <span class="unj-tag">Segredo de justiça</span>
    </div>
    """

    dados = esaj.extrair_dados_basicos(BeautifulSoup(html, "html.parser"), "https://x")

    assert dados["situacao"] == "Extinto"
    assert dados["etiquetas"] == ["Extinto", "Segredo de justiça"]


# --- desde e limite reduzem a paginação -------------------------------------------------


def test_desde_interrompe_a_paginacao_ao_chegar_em_movimentos_antigos():
    session = FakeSession()

    movimentos, completo, aviso = esaj.carregar_movimentacoes_ajax(
        session, "ABC123", limite=None, sleep=lambda _: None, desde="2026-07-27"
    )

    assert [m["data"] for m in movimentos] == ["29/07/2026", "28/07/2026", "27/07/2026"]
    assert session.cursores == ["", "CURSOR2"]
    assert completo is True and aviso == ""


def test_extrato_com_desde_filtra_pagina_estatica():
    html = """
    <span id="numeroProcesso">1076539-20.2019.8.26.0100</span>
    <table id="tabelaTodasMovimentacoes">
      <tr class="containerMovimentacao">
        <td class="dataMovimentacao">10/01/2026</td>
        <td class="descricaoMovimentacao">Recente</td>
      </tr>
      <tr class="containerMovimentacao">
        <td class="dataMovimentacao">10/01/2020</td>
        <td class="descricaoMovimentacao">Antiga</td>
      </tr>
    </table>
    """

    class Sessao:
        def get(self, url, **kwargs):
            from .test_esaj_http import FakeResponse

            return FakeResponse(html if "search.do" in url else "", url)

    extrato = esaj.montar_extrato(TJSP, session=Sessao(), desde="2025-01-01")

    assert [m["titulo"] for m in extrato["movimentacoes"]] == ["Recente"]


def test_limite_do_eSAJ_para_timeline_dos_mais_recentes():
    assert limite_movimentacoes_para(20, True, 100) == 20
    assert limite_movimentacoes_para(2, True, 100) == 5
    assert limite_movimentacoes_para(20, False, 100) == 100
    assert limite_movimentacoes_para(0, True, 100) == 100


def test_search_busca_so_uma_pagina_de_movimentacoes(monkeypatch):
    chamadas = []

    def falso(numero, **kwargs):
        chamadas.append(kwargs)
        return {"dados_basicos": {"numero": numero}, "movimentacoes": []}

    monkeypatch.setattr(api, "get_extrato", falso)

    api.search_processo(TJSP)

    assert chamadas == [{"limite_movimentacoes": esaj.LIMITE_RESUMO}]


def test_cli_timeline_recentes_limita_a_busca_no_esaj(monkeypatch, capsys):
    recebido = {}

    def falso(numero, **kwargs):
        recebido.update(kwargs)
        return {"timeline": []}

    monkeypatch.setattr(cli.api, "extract_process", falso)

    cli.main(["timeline", TJSP, "--limit", "20", "--recent-first", "--desde", "2026-01-01"])

    assert recebido["limite_movimentacoes"] == 20
    assert recebido["desde"] == "2026-01-01"


def test_cli_limite_zero_busca_todas(monkeypatch, capsys):
    recebido = {}
    monkeypatch.setattr(
        cli.api, "extract_process", lambda numero, **kw: recebido.update(kw) or {"timeline": []}
    )

    cli.main(["extract", TJSP, "--limite-movimentacoes", "0"])

    assert recebido["limite_movimentacoes"] is None


# --- fontes em paralelo com prazo total -------------------------------------------------


def _fontes_falsas(monkeypatch, atraso_datajud=0.0):
    inicio = {}

    def falso_esaj(numero, **kwargs):
        inicio["esaj"] = time.monotonic()
        time.sleep(0.2)
        return {"dados_basicos": {"numero": numero}, "movimentacoes": [{"data": "01/01/2026"}]}

    def falso_datajud(numero, **kwargs):
        inicio["datajud"] = time.monotonic()
        time.sleep(atraso_datajud or 0.2)
        return {
            "status": "ok",
            "numero_cnj": numero,
            "movimentos": [
                {"codigo": "1", "nome": "Antigo", "data": "2019-01-01", "data_hora": "2019-01-01"},
                {"codigo": "2", "nome": "Novo", "data": "2026-02-01", "data_hora": "2026-02-01"},
            ],
        }

    def falso_djen(numero, data_inicio="", **kwargs):
        inicio["djen"] = time.monotonic()
        inicio["djen_data_inicio"] = data_inicio
        return []

    monkeypatch.setattr(extraction.esaj, "montar_extrato", falso_esaj)
    monkeypatch.setattr(extraction.datajud, "consultar_processo", falso_datajud)
    monkeypatch.setattr(extraction.djen, "consultar_processo", falso_djen)
    return inicio


def test_fontes_rodam_em_paralelo(monkeypatch):
    inicio = _fontes_falsas(monkeypatch)

    antes = time.monotonic()
    envelope = extraction.extract_process(TJSP)
    duracao = time.monotonic() - antes

    assert duracao < 0.35  # em sequência seriam 0,4 s só nas duas fontes lentas
    assert set(inicio) >= {"esaj", "datajud", "djen"}
    assert envelope["status"] == "ok"
    assert list(envelope["data"]) == ["esaj", "datajud", "djen"]  # ordem estável


def test_fonte_lenta_estoura_o_prazo_sem_perder_as_demais(monkeypatch):
    _fontes_falsas(monkeypatch, atraso_datajud=1.5)

    antes = time.monotonic()
    envelope = extraction.extract_process(TJSP, prazo_total=0.5)
    duracao = time.monotonic() - antes

    assert duracao < 1.0
    assert envelope["status"] == "partial"
    assert envelope["source_status"]["datajud"]["status"] == "error"
    assert envelope["errors"][0]["source"] == "datajud"
    assert "esaj" in envelope["data"] and "djen" in envelope["data"]


def test_esaj_nao_se_aplica_fora_do_tjsp(monkeypatch):
    _fontes_falsas(monkeypatch)

    envelope = extraction.extract_process(TJRJ)

    assert envelope["source_status"]["esaj"]["status"] == "nao_aplicavel"
    assert envelope["errors"] == []
    assert "esaj" not in envelope["data"]


def test_desde_filtra_datajud_timeline_e_vai_para_o_djen(monkeypatch):
    inicio = _fontes_falsas(monkeypatch)

    envelope = extraction.extract_process(TJSP, desde="2025-01-01")

    assert [m["nome"] for m in envelope["data"]["datajud"]["movimentos"]] == ["Novo"]
    assert all(r["data"] >= "2025-01-01" for r in envelope["timeline"])
    assert inicio["djen_data_inicio"] == "2025-01-01"


# --- compactação (só remove repetição) --------------------------------------------------


def test_compactar_envelope_mantem_a_timeline_e_tira_a_duplicidade():
    envelope = {
        "data": {
            "esaj": {"dados_basicos": {"classe": "X"}, "movimentacoes": [{"titulo": "a"}]},
            "datajud": {"classe": "X", "movimentos": [{"nome": "a"}], "graus": [{"grau": "G1"}]},
            "djen": [{"id": 1}],
        },
        "timeline": [{"id": "1"}],
        "source_status": {"djen": {"records": 1}},
    }

    compacto = compactacao.compactar_envelope(envelope)

    assert compacto["timeline"] == [{"id": "1"}]
    assert "movimentacoes" not in compacto["data"]["esaj"]
    assert compacto["data"]["esaj"]["dados_basicos"] == {"classe": "X"}
    assert "movimentos" not in compacto["data"]["datajud"]
    assert compacto["data"]["datajud"]["graus"] == [{"grau": "G1"}]
    assert "djen" not in compacto["data"]
    assert compacto["source_status"] == {"djen": {"records": 1}}
    assert "movimentacoes" in envelope["data"]["esaj"]  # original intacto


def test_compactar_extrato_remove_texto_repetido_e_documentos_por_movimento():
    extrato = {
        "movimentacoes": [
            {
                "ordem": 1,
                "data": "01/01/2026",
                "titulo": "Juntada",
                "teor": "Petição",
                "texto": "Juntada Petição",
                "metadados": {},
                "documentos": [{"cd_documento": "1"}],
            }
        ],
        "documentos": {"publicos_candidatos_unicos": [{"cd_documento": "1"}]},
    }

    compacto = compactacao.compactar_extrato(extrato)

    assert compacto["movimentacoes"] == [
        {"ordem": 1, "data": "01/01/2026", "titulo": "Juntada", "teor": "Petição"}
    ]
    assert compacto["documentos"] == extrato["documentos"]


# --- MCP ---------------------------------------------------------------------------------


class _FastMCP:
    def __init__(self, name, **kwargs):
        self.tools = {}

    def tool(self):
        def registrar(funcao):
            self.tools[funcao.__name__] = funcao
            return funcao

        return registrar


def test_mcp_gerar_timeline_recentes_limita_busca_e_repassa_desde(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", _FastMCP)
    recebido = {}

    def falso(numero, **kwargs):
        recebido.update(kwargs)
        return {"timeline": []}

    monkeypatch.setattr(mcp_server.api, "extract_process", falso)
    servidor = mcp_server.create_server()

    servidor.tools["gerar_timeline"](TJSP, limit=10, recent_first=True, desde="2026-01-01")

    assert recebido["limite_movimentacoes"] == 10
    assert recebido["desde"] == "2026-01-01"


def test_mcp_extrair_processo_e_consultar_esaj_sao_compactos_por_padrao(monkeypatch):
    monkeypatch.setattr(mcp_server, "FastMCP", _FastMCP)
    monkeypatch.setattr(
        mcp_server.api,
        "extract_process",
        lambda numero, **kw: {"data": {"djen": [{"id": 1}]}, "timeline": [{"id": "1"}]},
    )
    monkeypatch.setattr(
        mcp_server.api,
        "get_extrato",
        lambda numero, **kw: {"movimentacoes": [{"titulo": "a", "texto": "repetido"}]},
    )
    servidor = mcp_server.create_server()

    envelope = servidor.tools["extrair_processo"](TJSP)
    extrato = servidor.tools["consultar_esaj"](TJSP)
    completo = servidor.tools["consultar_esaj"](TJSP, compacto=False)

    assert envelope["compacto"] is True and "djen" not in envelope["data"]
    assert extrato["movimentacoes"] == [{"titulo": "a"}]
    assert completo["movimentacoes"][0]["texto"] == "repetido"


def test_prazo_total_nao_deixa_threads_presas_no_resultado(monkeypatch):
    # a fonte lenta continua rodando em segundo plano, mas o envelope já voltou
    liberar = threading.Event()
    monkeypatch.setattr(extraction.esaj, "montar_extrato", lambda *a, **k: liberar.wait(2) and {})
    monkeypatch.setattr(extraction.datajud, "consultar_processo", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(extraction.djen, "consultar_processo", lambda *a, **k: [])

    envelope = extraction.extract_process(TJSP, prazo_total=0.2)
    liberar.set()

    assert envelope["source_status"]["esaj"]["status"] == "error"
    assert "datajud" in envelope["data"]


# --- bloqueio por consultas simultâneas do eSAJ ----------------------------------------------

AVISO = "<p>Atenção Foram identificadas multiplas consultas simultâneas.</p>"


class _SessaoComBloqueio:
    """Devolve o aviso do eSAJ nas primeiras buscas e o processo depois."""

    def __init__(self, bloqueios):
        self.bloqueios = bloqueios
        self.buscas = 0

    def get(self, url, **kwargs):
        from .test_esaj_http import FakeResponse

        if "search.do" not in url:
            return FakeResponse("", url)
        self.buscas += 1
        if self.buscas <= self.bloqueios:
            return FakeResponse(AVISO, url)
        return FakeResponse('<span id="numeroProcesso">1076539-20.2019.8.26.0100</span>', url)


def test_bloqueio_temporario_do_esaj_e_tentado_de_novo():
    pausas = []
    sessao = _SessaoComBloqueio(bloqueios=1)

    resposta = esaj.carregar_pagina(sessao, TJSP, sleep=pausas.append)

    assert "numeroProcesso" in resposta.text
    assert pausas == [esaj.ESPERA_BLOQUEIO]


def test_bloqueio_persistente_nao_vira_processo_nao_encontrado():
    import pytest

    from nanojud.exceptions import ConsultaIndisponivel

    sessao = _SessaoComBloqueio(bloqueios=99)

    with pytest.raises(ConsultaIndisponivel, match="consultas simultâneas"):
        esaj.carregar_pagina(sessao, TJSP, sleep=lambda _: None)

    assert sessao.buscas == esaj.TENTATIVAS_BLOQUEIO
