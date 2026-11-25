import json
from pathlib import Path
from typing import Any

import pytest
import requests

from nanojud import api, cli, compactacao, esaj_tjsp_2g
from nanojud.exceptions import (
    AcessoRestrito,
    ConsultaIndisponivel,
    DocumentoNaoEncontrado,
    DownloadIndisponivel,
)

ORIGEM = "0040759-80.2012.8.26.0100"
RECURSOS = ("2049567-73.2017.8.26.0000", "2141890-05.2014.8.26.0000")


def capa(numero: str) -> str:
    return f"""
    <span id="numeroProcesso">{numero}</span>
    <div id="classeProcesso">Agravo</div>
    <div id="orgaoJulgadorProcesso">Câmara</div>
    <div id="relatorProcesso">Relator</div>
    <a id="linkExibirMovimentacoes">Exibir movimentações</a>
    """


def linha(titulo: str) -> str:
    return f"""
    <tr class="movimentacaoProcesso">
      <td class="dataMovimentacaoProcesso">01/04/2025</td>
      <td class="descricaoMovimentacaoProcesso">{titulo}</td>
    </tr>
    """


class Portal:
    def __init__(self) -> None:
        self.links = "".join(
            f'<a class="linkProcesso" href="/cposg/show.do?processo.codigo={codigo}">{numero}</a>'
            for codigo, numero in zip(("A", "B"), RECURSOS, strict=True)
        )
        self.detalhes = {"A": capa(RECURSOS[0]), "B": capa(RECURSOS[1])}
        self.final = (
            linha("Distribuído")
            + """
        <tr id="metaPaginaMovimentacoes" data-tem-mais-paginas="false"></tr>"""
        )
        self.chamadas: list[tuple[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        params = kwargs.get("params")
        self.chamadas.append((url, params))
        assert kwargs["allow_redirects"] is False
        endpoint = url.rsplit("/", 1)[-1]
        if endpoint == "open.do":
            html = ""
        elif endpoint == "search.do":
            html = self.links
        elif endpoint == "show.do":
            html = self.detalhes[params["processo.codigo"]]
        elif params.get("cursor"):
            html = self.final
        else:
            html = f'<table id="tabelaMovimentacoesAjax">{linha("Conclusos")}</table>'
            if params["cdProcesso"] == "A":
                html += '<a id="linkMaisRecolherMovimentacoes" data-cursor="cursor-A">Mais</a>'
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response.headers["Content-Type"] = "text/html; charset=UTF-8"
        response.encoding = "utf-8"
        response._content = html.encode()
        return response

    def __enter__(self) -> "Portal":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


@pytest.fixture
def portal(monkeypatch: pytest.MonkeyPatch) -> Portal:
    portal = Portal()
    monkeypatch.setattr(esaj_tjsp_2g.esaj, "criar_session", lambda timeout: portal)
    monkeypatch.setattr(esaj_tjsp_2g.esaj, "_aguardar_ritmo", lambda: None)
    monkeypatch.setattr(esaj_tjsp_2g.esaj, "PAUSA_PAGINAS", 0)
    return portal


def test_consulta_preserva_recursos_distintos_e_cursor_por_processo(portal: Portal) -> None:
    resultado = api.consultar_esaj_tjsp_2g(ORIGEM)

    assert resultado["status"] == "ok"
    assert resultado["origem"]["grau"] == "2g"
    assert resultado["numero_consultado"] == ORIGEM
    primeiro, segundo = resultado["resultados"]
    assert [item["dados_basicos"]["numero"] for item in (primeiro, segundo)] == list(RECURSOS)
    assert [mov["titulo"] for mov in primeiro["movimentacoes"]] == ["Conclusos", "Distribuído"]
    assert segundo["movimentacoes_completas"] is True
    busca = next(params for url, params in portal.chamadas if url.endswith("/search.do"))
    assert [valor for chave, valor in busca if chave == "dePesquisaNuUnificado"] == [
        ORIGEM,
        "UNIFICADO",
    ]
    cursores = [p for _, p in portal.chamadas if isinstance(p, dict) and "cursor" in p]
    assert cursores == [{"cdProcesso": "A", "cursor": "cursor-A"}]


def test_lote_cposg_preserva_cnj_dos_recursos_na_timeline(portal: Portal) -> None:
    resumo = api.extract_processes([ORIGEM], sources=["esaj_tjsp_2g"])
    (item,) = resumo["items"]
    resultado = item["result"]
    assert item["status"] == "ok"
    assert resultado["source_status"]["esaj_tjsp_2g"]["records"] == 3
    timeline = resultado["timeline"]
    assert {r["numero_cnj"] for r in timeline} == set(RECURSOS)
    assert {r["grau"] for r in timeline} == {"2g"}
    assert len({r["id"] for r in timeline}) == 3
    assert len({r["url_origem"] for r in timeline}) == 2
    compacto = compactacao.compactar_envelope(dict(resultado))
    assert compacto["timeline"] == timeline
    assert all(
        "movimentacoes" not in recurso for recurso in compacto["data"]["esaj_tjsp_2g"]["resultados"]
    )
    assert "movimentacoes" in resultado["data"]["esaj_tjsp_2g"]["resultados"][0]


def test_lote_busca_inconclusiva_nao_abre_circuito(portal: Portal) -> None:
    originais = portal.links
    portal.links = '<form action="/cposg/search.do"></form>'

    def entradas():
        yield ORIGEM
        portal.links = originais
        yield ORIGEM

    resumo = api.extract_processes(entradas(), sources=["esaj_tjsp_2g"])
    primeiro, segundo = resumo["items"]
    assert primeiro["status"] == "error"
    assert primeiro["result"]["errors"][0]["type"] == "ConsultaInconclusiva"
    assert segundo["status"] == "ok"


def test_extracao_cposg_sem_capas_confirmadas_expoe_erro(portal: Portal) -> None:
    portal.detalhes = {"A": "", "B": ""}
    resultado = api.extract_process(ORIGEM, sources=["esaj_tjsp_2g"])
    assert resultado["status"] == "error"
    assert resultado["source_status"]["esaj_tjsp_2g"]["status"] == "error"
    assert len(resultado["data"]["esaj_tjsp_2g"]["resultados"]) == 2


def test_autos_cposg_identifica_cada_recurso_e_isola_restricao(
    portal: Portal, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get = portal.get

    def resposta(url, **kwargs):
        r = get(url, **kwargs)
        if url.endswith("carregarMovimentacoesAjax.do"):
            r._content = r.content.replace(
                b"Conclusos", b'<a class="linkMovVincProc" cddocumento="25">Acordao</a>'
            )
        return r

    def baixar(sessao, numero, codigo, documento, timeout, max_bytes):
        assert sessao is portal and documento == "25"
        assert (numero, codigo) in zip(RECURSOS, ("A", "B"), strict=True)
        if codigo == "A":
            raise AcessoRestrito("Documento restrito.")
        return b"%PDF-1.7\n%%EOF"

    monkeypatch.setattr(portal, "get", resposta)
    monkeypatch.setattr(esaj_tjsp_2g, "_baixar_pdf_vinculado", baixar, raising=False)
    (item,) = api.iter_extract_dockets([ORIGEM], destination=str(tmp_path), source="esaj_tjsp_2g")
    assert item["status"] == "partial"
    assert item["summary"]["autos_completos"] is False
    assert item["document_candidates"] == 2 and item["restricted_documents"] == 1
    assert [doc["numero_cnj"] for doc in item["document_statuses"]] == list(RECURSOS)
    (arquivo,) = item["downloaded"]
    assert arquivo["numero_cnj"] == RECURSOS[1]
    assert Path(arquivo["arquivo"]).read_bytes().startswith(b"%PDF-")


def test_capa_de_outro_numero_falha_sem_perder_demais_recursos(portal: Portal) -> None:
    portal.detalhes["A"] = capa(RECURSOS[1])
    resultado = api.consultar_esaj_tjsp_2g(ORIGEM)
    assert resultado["status"] == "partial"
    primeiro, segundo = resultado["resultados"]
    assert primeiro["status"] == "erro"
    assert "dados_basicos" not in primeiro
    assert segundo["dados_basicos"]["numero"] == RECURSOS[1]


@pytest.mark.parametrize("limite", [1, 5])
def test_paginacao_inconclusiva_preserva_movimentos(portal: Portal, limite: int) -> None:
    portal.final = (
        linha("Distribuído")
        + """
    <tr id="metaPaginaMovimentacoes" data-tem-mais-paginas="true" data-cursor="cursor-A"></tr>"""
    )
    resultado = api.consultar_esaj_tjsp_2g(ORIGEM, max_paginas=limite)
    primeiro = resultado["resultados"][0]
    assert resultado["status"] == "partial"
    assert primeiro["movimentacoes_completas"] is False
    assert [m["titulo"] for m in primeiro["movimentacoes"]] == (
        ["Conclusos"] if limite == 1 else ["Conclusos", "Distribuído"]
    )


def test_formulario_sem_resultado_ou_aviso_e_inconclusivo(portal: Portal) -> None:
    portal.links = '<form action="/cposg/search.do"></form>'
    with pytest.raises(ConsultaIndisponivel):
        api.consultar_esaj_tjsp_2g(ORIGEM)


def test_indexa_peca_vinculada_sem_repetir_icone_ou_expor_script(portal: Portal) -> None:
    portal.final = """
    <tr class="movimentacaoProcesso">
      <td class="dataMovimentacaoProcesso">01/04/2025</td>
      <td><a class="linkMovVincProc" href="#" cdDocumento="42"
             title="Visualizar documento em inteiro teor">Ícone</a></td>
      <td class="descricaoMovimentacaoProcesso">
        <a class="linkMovVincProc" href="#" cdDocumento="42" onclick="abrir()">Acórdão</a>
        <a class="linkMovVincProc" href="#" cdDocumento="inválido">Outro</a>
      </td>
    </tr>
    <tr id="metaPaginaMovimentacoes" data-tem-mais-paginas="false"></tr>
    """
    resultado = api.consultar_esaj_tjsp_2g(ORIGEM)["resultados"][0]
    assert resultado["movimentacoes"][0]["documentos"] == []
    assert resultado["movimentacoes"][1]["documentos"] == [
        {
            "cd_documento": "42",
            "titulo": "Acórdão",
            "status_acesso": "nao_verificado",
        }
    ]


def test_cli_expoe_a_consulta_com_o_mesmo_contrato(portal: Portal, capsys) -> None:
    assert cli.main(["esaj-2g", ORIGEM]) == 0
    resposta = json.loads(capsys.readouterr().out)
    assert resposta["origem"]["grau"] == "2g"
    assert [item["numero"] for item in resposta["resultados"]] == list(RECURSOS)


@pytest.mark.parametrize("restrito", [False, True])
def test_cli_pdf_grava_so_depois_do_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restrito: bool
) -> None:
    destino = tmp_path / "peca.pdf"
    destino.write_bytes(b"arquivo anterior")
    pdf = b"%PDF-1.7\n%%EOF"

    def obter(numero, cd_documento, **kwargs):
        assert (numero, cd_documento) == (RECURSOS[0], "25")
        assert kwargs == {"timeout": 30.0, "max_paginas": 3}
        if restrito:
            raise AcessoRestrito("Peça restrita no portal.")
        return pdf

    monkeypatch.setattr(api, "obter_pdf_esaj_tjsp_2g", obter)
    retorno = cli.main(
        ["esaj-2g-pdf", RECURSOS[0], "25", "--out", str(destino), "--max-paginas", "3"]
    )
    assert retorno == (2 if restrito else 0)
    assert destino.read_bytes() == (b"arquivo anterior" if restrito else pdf)
    assert list(tmp_path.iterdir()) == [destino]


def test_sem_capas_confirmadas_expoe_erro(portal: Portal) -> None:
    portal.detalhes = {"A": "", "B": ""}
    resposta = api.consultar_esaj_tjsp_2g(ORIGEM)
    assert resposta["status"] == "erro"
    assert [item["status"] for item in resposta["resultados"]] == ["erro", "erro"]


def test_limite_de_detalhes_preserva_lista(portal: Portal, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(esaj_tjsp_2g, "MAX_RESULTADOS", 1)
    resposta = api.consultar_esaj_tjsp_2g(ORIGEM)
    assert resposta["status"] == "partial"
    assert [item["numero"] for item in resposta["resultados_listados"]] == list(RECURSOS)
    assert len(resposta["resultados"]) == 1


def test_link_fora_do_cposg_nao_consulta_outro_destino(portal: Portal) -> None:
    portal.links = portal.links.replace(
        "/cposg/show.do?processo.codigo=A", "https://example.test/cposg/show.do?processo.codigo=A"
    )
    resposta = api.consultar_esaj_tjsp_2g(ORIGEM)
    assert resposta["status"] == "partial"
    assert [item["numero"] for item in resposta["resultados"]] == [RECURSOS[1]]
    assert all(url.startswith(esaj_tjsp_2g.BASE) for url, _ in portal.chamadas)


def test_busca_por_cnj_proprio_retorna_capa_no_proprio_search(portal: Portal) -> None:
    portal.links = capa(RECURSOS[0]) + '<input type="hidden" name="cdProcesso" value="A">'

    resposta = api.consultar_esaj_tjsp_2g(RECURSOS[0])

    assert resposta["status"] == "ok"
    (resultado,) = resposta["resultados"]
    assert resultado["dados_basicos"]["numero"] == RECURSOS[0]
    assert resultado["url"].endswith("/cposg/show.do?processo.codigo=A")
    assert not any(url.endswith("/show.do") for url, _ in portal.chamadas)


@pytest.mark.parametrize(
    "numero,campos",
    [
        (RECURSOS[1], '<input type="hidden" name="cdProcesso" value="A">'),
        (
            RECURSOS[0],
            '<input type="hidden" name="cdProcesso" value="A">'
            '<input type="hidden" name="cdProcesso" value="B">',
        ),
    ],
)
def test_capa_direta_inconclusiva_nao_consulta_movimentos(
    portal: Portal, numero: str, campos: str
) -> None:
    portal.links = capa(numero) + campos
    with pytest.raises(ConsultaIndisponivel):
        api.consultar_esaj_tjsp_2g(RECURSOS[0])
    assert len(portal.chamadas) == 2


@pytest.mark.parametrize(
    "cenario", ["ok", "primeira_pagina", "restrito", "outro_processo", "ausente", "limite"]
)
def test_pdf_exige_verificacao_de_acesso_ao_documento_listado(
    portal: Portal, monkeypatch: pytest.MonkeyPatch, cenario: str
) -> None:
    portal.links = capa(RECURSOS[0]) + '<input type="hidden" name="cdProcesso" value="A">'
    portal.final = linha('<a class="linkMovVincProc" cddocumento="25">Acórdão</a>') + (
        '<tr id="metaPaginaMovimentacoes" data-tem-mais-paginas="false"></tr>'
    )
    get = portal.get
    chamadas = []
    pdf = b"%PDF-1.4\n%%EOF"

    def responder(url, **kwargs):
        endpoint = url.split("?")[0].rsplit("/", 1)[-1]
        if endpoint not in {"verificarAcessoMovimentacao.do", "abrirDocumentoEdt.do", "getPDF.do"}:
            resposta = get(url, **kwargs)
            if cenario == "primeira_pagina" and endpoint == "carregarMovimentacoesAjax.do":
                assert "cursor" not in kwargs["params"]
                resposta._content = resposta.content.replace(
                    b"Conclusos", b'<a class="linkMovVincProc" cddocumento="25">Acordao</a>'
                )
            return resposta
        assert kwargs["allow_redirects"] is False
        chamadas.append(endpoint)
        resposta = requests.Response()
        resposta.status_code = 200
        if endpoint == "verificarAcessoMovimentacao.do":
            assert kwargs["params"] == {
                "cdDocumento": "25",
                "cdProcesso": "A",
                "origemRecurso": "M",
            }
            if cenario == "restrito":
                resposta.status_code = 403
            resposta._content = (
                f"https://esaj.tjsp.jus.br/pastadigital/abrirDocumentoEdt.do?"
                f"cdProcesso=A&nuProcesso={RECURSOS[0]}&ticket=teste"
            ).encode()
        elif endpoint == "abrirDocumentoEdt.do":
            resposta._content = b"viewer"
        else:
            resposta.headers["Content-Type"] = "application/pdf"
            resposta._content = pdf
            resposta._content_consumed = True
        return resposta

    monkeypatch.setattr(portal, "get", responder)
    numero_pdf = RECURSOS[1] if cenario == "outro_processo" else RECURSOS[0]
    scope = [{"children": [{"data": {"parametros": f"cdProcesso=A&nuProcesso={numero_pdf}"}}]}]
    monkeypatch.setattr(esaj_tjsp_2g.esaj, "extrair_request_scope", lambda _: json.dumps(scope))
    if cenario == "restrito":
        with pytest.raises(AcessoRestrito):
            api.obter_pdf_esaj_tjsp_2g(RECURSOS[0], "25")
        assert chamadas == ["verificarAcessoMovimentacao.do"]
    elif cenario == "ausente":
        with pytest.raises(DocumentoNaoEncontrado):
            api.obter_pdf_esaj_tjsp_2g(RECURSOS[0], "99")
        assert not chamadas
    elif cenario == "outro_processo":
        with pytest.raises(DownloadIndisponivel):
            api.obter_pdf_esaj_tjsp_2g(RECURSOS[0], "25")
        assert chamadas == ["verificarAcessoMovimentacao.do", "abrirDocumentoEdt.do"]
    elif cenario == "limite":
        with pytest.raises(DownloadIndisponivel):
            api.obter_pdf_esaj_tjsp_2g(RECURSOS[0], "25", max_bytes=5)
        assert chamadas[-1] == "getPDF.do"
    else:
        assert api.obter_pdf_esaj_tjsp_2g(RECURSOS[0], "25") == pdf
        assert chamadas == [
            "verificarAcessoMovimentacao.do",
            "abrirDocumentoEdt.do",
            "getPDF.do",
        ]
