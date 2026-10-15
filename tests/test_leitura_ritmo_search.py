import threading

import pytest

from nanojud import api, cli, client, datajud, esaj, normalization
from nanojud.exceptions import ProcessoNaoEncontrado

from .test_esaj_http import FakeResponse

TJSP = "1076539-20.2019.8.26.0100"
TJRJ = "0032991-06.2012.8.19.0066"
EXPIRADA = "<html><body>Atenção Sua sessão expirou. Efetue novamente a consulta.</body></html>"


# --- leitura de peças: sessão expirada ------------------------------------------------------


def _documento(**extra):
    doc = {
        "cd_documento": "1",
        "titulo": "Sentença",
        "href": "https://esaj.tjsp.jus.br/cpopg/x.do",
        "status_acesso": "publico_candidato",
    }
    doc.update(extra)
    return doc


def _pasta_ok():
    return {
        "status": "ok",
        "url_final": "https://esaj.tjsp.jus.br/pastadigital/abrir?ticket=SEGREDO",
        "paginas": [{"parametros_pdf": "a=1"}],
    }


class _SessaoPasta:
    def __init__(self, corpo):
        self.corpo = corpo

    def get(self, url, **kwargs):
        return FakeResponse(self.corpo, url)


def test_ler_pecas_nao_trata_tela_de_sessao_expirada_como_texto():
    movimentos = [{"documentos": [_documento(pasta_digital=_pasta_ok())]}]

    leitura = esaj.ler_pecas_publicas(_SessaoPasta(EXPIRADA), movimentos)

    assert leitura[0]["status"] == "sessao_expirada"
    assert "texto" not in leitura[0]
    assert "mesma" in leitura[0]["mensagem"] or "sessão" in leitura[0]["mensagem"]


def test_ler_pecas_nao_expoe_ticket_da_pasta_digital():
    movimentos = [{"documentos": [_documento(pasta_digital=_pasta_ok())]}]

    leitura = esaj.ler_pecas_publicas(_SessaoPasta("<p>Texto da sentença</p>"), movimentos)

    assert leitura[0]["status"] == "texto_html_extraido"
    assert leitura[0]["pasta_digital"] == {"status": "ok", "paginas": 1}
    assert "SEGREDO" not in str(leitura)


def test_baixar_pecas_marca_sessao_expirada(tmp_path):
    movimentos = [{"documentos": [_documento(pasta_digital=_pasta_ok())]}]

    esaj.baixar_pecas_publicas(_SessaoPasta(EXPIRADA), movimentos, tmp_path, limite=1)

    assert movimentos[0]["documentos"][0]["download_status"] == "sessao_expirada"


def test_preparar_documentos_reabre_o_processo_e_descarta_ticket_antigo():
    chamadas = []

    class Sessao:
        def get(self, url, **kwargs):
            chamadas.append(url)
            html = '<span id="numeroProcesso">1076539-20.2019.8.26.0100</span>'
            return FakeResponse(html if "search.do" in url else "", url)

    documento = _documento(pasta_digital=_pasta_ok())
    movimentos = [{"documentos": [documento]}]

    esaj.preparar_documentos(Sessao(), TJSP, movimentos)

    assert any("search.do" in url for url in chamadas)
    assert "pasta_digital" not in documento


def test_api_ler_pecas_usa_o_numero_do_extrato_para_preparar_a_sessao(monkeypatch):
    preparado = {}
    monkeypatch.setattr(api.esaj, "criar_session", lambda: "sessao")
    monkeypatch.setattr(
        api.esaj,
        "preparar_documentos",
        lambda sessao, numero, movimentos, limite: preparado.update(sessao=sessao, numero=numero),
    )
    monkeypatch.setattr(api.esaj, "ler_pecas_publicas", lambda *a, **k: [])
    extrato = {
        "dados_basicos": {"numero": TJSP},
        "documentos": {"publicos_candidatos_unicos": [_documento()]},
    }

    api.ler_pecas(extrato)

    assert preparado == {"sessao": "sessao", "numero": TJSP}


# --- ritmo mínimo e mensagem de não encontrado ----------------------------------------------


def test_ritmo_minimo_espera_entre_consultas(monkeypatch):
    agora = [100.0]
    esperas = []
    monkeypatch.setattr(esaj, "INTERVALO_CONSULTAS", 1.1)
    monkeypatch.setattr(esaj, "_ultima_consulta", 0.0)
    monkeypatch.setattr(esaj.time, "monotonic", lambda: agora[0])
    monkeypatch.setattr(
        esaj.time, "sleep", lambda s: (esperas.append(s), agora.__setitem__(0, agora[0] + s))
    )

    esaj._aguardar_ritmo()  # primeira consulta: sem espera
    agora[0] += 0.3
    esaj._aguardar_ritmo()  # 0,3 s depois: falta 0,8 s
    agora[0] += 5
    esaj._aguardar_ritmo()  # bem depois: sem espera

    assert esperas == [pytest.approx(0.8)]


def test_ritmo_minimo_vale_entre_threads(monkeypatch):
    monkeypatch.setattr(esaj, "INTERVALO_CONSULTAS", 0.05)
    monkeypatch.setattr(esaj, "_ultima_consulta", 0.0)
    instantes = []

    def consulta():
        esaj._aguardar_ritmo()
        instantes.append(esaj._ultima_consulta)

    threads = [threading.Thread(target=consulta) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    instantes.sort()
    assert all(b - a >= 0.045 for a, b in zip(instantes, instantes[1:], strict=False))


def test_carregar_pagina_aguarda_o_ritmo_antes_de_cada_consulta(monkeypatch):
    chamadas = []
    monkeypatch.setattr(esaj, "_aguardar_ritmo", lambda: chamadas.append("ritmo"))

    class Sessao:
        def get(self, url, **kwargs):
            chamadas.append("get")
            return FakeResponse('<span id="numeroProcesso">x</span>', url)

    esaj.carregar_pagina(Sessao(), TJSP)

    assert chamadas[0] == "ritmo"


def test_mensagem_de_nao_encontrado_menciona_sigilo_e_outro_sistema():
    soup = esaj.BeautifulSoup(
        "<p>Não existem informações disponíveis para os parâmetros informados.</p>", "html.parser"
    )

    with pytest.raises(ProcessoNaoEncontrado, match="sigiloso"):
        esaj.detectar_estado_pagina(soup, FakeResponse("", "https://x"))


# --- search: sem requisição duplicada e fallback DataJud ------------------------------------


def _extrato_basico():
    return {
        "dados_basicos": {"numero": TJSP, "classe": "Ação"},
        "movimentacoes": [{"data": "10/01/2026", "titulo": "Juntada"}],
        "origem": {"url_final": "https://x"},
        "status": "ok",
    }


def test_cliente_reaproveita_o_extrato_ja_buscado_no_search(monkeypatch):
    buscas = []

    def montar(numero, **kwargs):
        buscas.append(numero)
        return _extrato_basico()

    monkeypatch.setattr(client.esaj, "montar_extrato", montar)
    cliente = client.NanoJudClient(session=object())

    cliente.get_extrato(TJSP)
    resumo = cliente.search_processo(TJSP)

    assert buscas == [TJSP]  # o search não refez a consulta
    assert resumo["ultima_movimentacao"] == "Juntada"


def test_cliente_search_consulta_se_nao_ha_extrato_anterior(monkeypatch):
    buscas = []
    monkeypatch.setattr(
        client.esaj, "montar_extrato", lambda numero, **kw: buscas.append(kw) or _extrato_basico()
    )

    client.NanoJudClient(session=object()).search_processo(TJSP)

    assert buscas[0]["limite_movimentacoes"] == esaj.LIMITE_RESUMO


def _datajud_ok(**extra):
    base = {
        "status": "ok",
        "numero_cnj": TJRJ,
        "tribunal": "TJRJ",
        "classe": "Usucapião",
        "orgao_julgador": "1 VARA CIVEL",
        "assuntos": [{"nome": "Usucapião Extraordinária"}],
        "movimentos": [
            {"nome": "Distribuição", "data": "2012-09-10", "data_hora": "2012-09-10T10:00:00Z"},
            {
                "nome": "Sentença",
                "data": "2026-09-11",
                "data_hora": "2026-09-11T10:00:00Z",
                "complementos": "procedente",
            },
        ],
        "metadata": {"source_url": "https://api-publica.datajud.cnj.jus.br/x"},
    }
    base.update(extra)
    return base


def test_search_fora_do_tjsp_usa_o_datajud(monkeypatch):
    monkeypatch.setattr(api, "consultar_datajud", lambda numero, **kw: _datajud_ok())
    monkeypatch.setattr(api, "get_extrato", lambda *a, **k: pytest.fail("não deve ir ao eSAJ"))

    resumo = api.search_processo(TJRJ)

    assert resumo["fonte"] == "datajud"
    assert resumo["classe"] == "Usucapião"
    assert resumo["assunto"] == "Usucapião Extraordinária"
    assert resumo["vara"] == "1 VARA CIVEL"
    assert resumo["ultima_movimentacao"] == "Sentença - procedente"
    assert resumo["ultima_data"] == "11/09/2026"
    assert resumo["juiz"] == ""


def test_search_fora_do_tjsp_sem_registro_no_datajud_da_erro_claro():
    with pytest.raises(ProcessoNaoEncontrado, match="DataJud"):
        datajud.resumo_do_datajud({"status": "nao_encontrado"})


def test_cliente_search_fora_do_tjsp_usa_o_datajud(monkeypatch):
    cliente = client.NanoJudClient(session=object())
    monkeypatch.setattr(cliente, "consultar_datajud", lambda numero, **kw: _datajud_ok())

    assert cliente.search_processo(TJRJ)["fonte"] == "datajud"


# --- CLI e OAB ---------------------------------------------------------------------------------


def test_cli_djen_aceita_desde_como_data_inicio(monkeypatch, capsys):
    recebido = {}
    monkeypatch.setattr(
        cli.api,
        "consultar_djen",
        lambda numero, data_inicio="": recebido.update(data_inicio=data_inicio) or [],
    )

    cli.main(["djen", TJSP, "--desde", "2026-01-01"])

    assert recebido["data_inicio"] == "2026-01-01"


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("OAB: 123/sp", "123/SP"),
        ("OAB/SP 140.969", "140969/SP"),
        ("OAB-RJ 12345-A", "12345A/RJ"),
        ("SP269542", "269542/SP"),
        ("269542/SP", "269542/SP"),
        ("Dr. Fulano OAB 98765/MG", "98765/MG"),
        ("12345", "12345"),
    ],
)
def test_normalizar_oab_forma_canonica(entrada, esperado):
    assert normalization.normalizar_oab(entrada) == esperado


def test_normalizar_oab_sem_numero_devolve_texto_limpo():
    assert normalization.normalizar_oab("OAB:  sem número ") == "SEM NÚMERO"


def test_preparar_documentos_carrega_ate_a_pagina_do_documento_lido():
    from pathlib import Path

    lazy = (Path(__file__).parent / "fixtures" / "esaj_processo_lazy.html").read_text("utf-8")
    link = (
        '<a class="linkMovVincProc" href="/cpopg/abrirDocumentoVinculadoMovimentacao.do'
        '?processo.codigo=ABC123&cdDocumento=999&nmRecursoAcessado=X">Sentença</a>'
    )

    def linha(data, conteudo=""):
        return (
            f'<tr class="containerMovimentacao"><td class="dataMovimentacao">{data}</td>'
            f'<td class="descricaoMovimentacao">{conteudo} Movimento</td></tr>'
        )

    paginas = {
        "": linha("29/07/2026") + '<input id="cursorMovimentacoesPaginado" value="C2"/>',
        "C2": linha("27/07/2026", link) + '<tr id="trCursorMovimentacoes" data-cursor="C3"></tr>',
        "C3": linha("20/07/2026"),
    }
    pedidos = []

    class Sessao:
        def get(self, url, **kwargs):
            if "carregarMovimentacoesAjax" in url:
                cursor = kwargs["params"].get("cursor", "")
                pedidos.append(cursor)
                return FakeResponse(paginas[cursor], url)
            return FakeResponse(lazy if "search.do" in url else "", url)

    documento = _documento(cd_documento="999", pasta_digital=_pasta_ok())
    outro = _documento(cd_documento="111")
    movimentos = [{"documentos": [documento, outro]}]

    esaj.preparar_documentos(Sessao(), TJSP, movimentos, limite=1)

    assert pedidos == ["", "C2"]  # parou na página do documento 999, sem carregar a C3
    assert "pasta_digital" not in documento
