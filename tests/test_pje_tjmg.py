from types import SimpleNamespace

import pytest
import requests
from bs4 import BeautifulSoup

from nanojud import extraction, pje_tjmg
from nanojud.exceptions import (
    AcessoRestrito,
    ConsultaIndisponivel,
    ProcessoNaoEncontrado,
    URLInvalida,
)
from nanojud.sources import normalizar_fonte, normalizar_fontes

CNJ = "5060583-19.2021.8.13.0024"
ORIGIN = "https://pje-consulta-publica.tjmg.jus.br"


def test_leitura_pje_limita_pdf_transferido_em_memoria(monkeypatch):
    chamadas = {}

    def gerar(url, *, session, timeout, max_bytes):
        chamadas.update(url=url, session=session, timeout=timeout, max_bytes=max_bytes)
        return b"%PDF-1.7 fixture"

    monkeypatch.setattr(pje_tjmg, "_gerar_pdf_publico", gerar)
    monkeypatch.setattr(
        pje_tjmg.esaj,
        "extrair_texto_pdf_bytes",
        lambda conteudo, *, max_chars: ("texto", "texto_extraido"),
    )

    resultado = pje_tjmg.ler_documento_publico(
        f"{ORIGIN}{pje_tjmg.PJE_DOCUMENT_PATH}?idProcessoDoc=123", timeout=7
    )

    assert resultado["status"] == "texto_extraido"
    assert chamadas["timeout"] == 7
    assert chamadas["max_bytes"] == pje_tjmg.MAX_EMBEDDED_DOCUMENT_BYTES


def test_prazo_total_zero_impede_primeira_requisicao_pje(monkeypatch):
    class SessionSemRede:
        def get(self, *args, **kwargs):
            pytest.fail("Prazo total zero não pode iniciar uma requisição HTTP")

    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)

    with pytest.raises(ConsultaIndisponivel, match="[Pp]razo total"):
        pje_tjmg.consultar_processo(CNJ, session=SessionSemRede(), prazo_total=0)


def test_request_reduz_timeout_ao_tempo_restante_do_prazo(monkeypatch):
    chamadas = []

    class Session:
        def get(self, url, *, timeout):
            chamadas.append(timeout)
            return SimpleNamespace(status_code=200)

    agora = pje_tjmg.time.monotonic()
    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pje_tjmg.time, "monotonic", lambda: agora)

    pje_tjmg._request(Session(), "GET", pje_tjmg.PJE_LOGIN_URL, timeout=30, deadline=agora + 2)

    assert chamadas == [2]


def test_parse_detail_preserva_andamentos_documentos_e_incompletude():
    doc_url = f"{ORIGIN}{pje_tjmg.PJE_DOCUMENT_PATH}?ca=fixture&idProcessoDoc=123"
    html = f"""
    <html><body>
      <table id="j_id145:processoEvento">
        <tr><th>Movimento</th><th>Documento</th></tr>
        <tr><td>05/10/2026 14:38:46 - Decisão</td><td></td></tr>
        <tr><td>21/10/2026 17:09:50 - Juntada de petição de ciência</td><td></td></tr>
      </table>
      <table id="j_id145:processoDocumentoGridTab">
        <tr><th>Documento</th><th>Certidão</th></tr>
        <tr><td><a title="Visualizar"
          onclick="openPopUp('doc', '{doc_url}')">
          Visualizar documentos 21/10/2026</a></td><td></td></tr>
      </table>
      <table><tr><td>Número Processo 5060583-19.2021.8.13.0024</td>
      <td>Classe Judicial Procedimento Comum</td><td>Assunto Direito Civil</td>
      <td>Órgão Julgador 4ª Vara Cível</td>
      <td>Unidade Judiciária Unidade Jurisdicional de Teste</td></tr></table>
      <div class="rich-slider" id="j_id145:j_id542:j_id543">
        <td class="rich-inslider-left-num">1</td>
        <td class="rich-inslider-right-num">22</td>
      </div>
      <div class="rich-slider" id="j_id145:j_id634:j_id635">
        <td class="rich-inslider-left-num">1</td>
        <td class="rich-inslider-right-num">2</td>
      </div>
    </body></html>
    """

    extrato = pje_tjmg.parse_detail_page(
        CNJ, html, f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
    )

    assert extrato["dados_basicos"]["numero"] == CNJ
    assert extrato["dados_basicos"]["classe"] == "Procedimento Comum"
    assert extrato["dados_basicos"]["orgao_julgador"] == "4ª Vara Cível"
    assert extrato["dados_basicos"]["foro"] == "4ª Vara Cível"
    assert extrato["dados_basicos"]["vara"] == "Unidade Jurisdicional de Teste"
    assert len(extrato["movimentacoes"]) == 2
    assert extrato["movimentacoes"][1]["data"] == "2026-10-21"
    assert extrato["movimentacoes"][1]["titulo"] == "Juntada de petição de ciência"
    documentos = extrato["documentos"]["publicos_candidatos_unicos"]
    assert len(documentos) == 1
    assert documentos[0]["titulo"] == "Visualizar documentos 21/10/2026"
    assert documentos[0]["href"].startswith(f"{ORIGIN}/pje/ConsultaPublica/")
    assert extrato["origem"]["movimentacoes_completas"] is False
    assert "22" in extrato["origem"]["aviso_movimentacoes"]
    assert extrato["origem"]["aviso_documentos"]
    assert "documentos;" not in extrato["origem"]["aviso_movimentacoes"]


def test_parse_detail_nao_declara_completude_quando_slider_nao_foi_observado():
    html = """
    <table id="j_id145:processoEvento">
      <tr><td>21/10/2026 - Juntada</td><td></td></tr>
    </table>
    <table id="j_id145:processoDocumentoGridTab"><tr><td>Documento A</td></tr></table>
    """

    extrato = pje_tjmg.parse_detail_page(
        CNJ,
        html,
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam",
    )

    assert extrato["status"] == "partial"
    assert extrato["origem"]["movimentacoes_completas"] is False
    assert extrato["origem"]["documentos_completos"] is False
    assert "não foi possível verificar" in extrato["origem"]["aviso_movimentacoes"]
    assert "não foi possível verificar" in extrato["origem"]["aviso_documentos"]


def test_parse_detail_confirma_tabela_documentos_sem_slider_por_contagem_explicita():
    documentos = "".join(
        f'<tr class="rich-table-row"><td>Documento {i}</td></tr>' for i in range(4)
    )
    html = f"""
    <table id="j_id145:processoEvento"><tr><td>21/10/2026 - Juntada</td></tr></table>
    <div class="rich-slider"><td class="rich-inslider-right-num">1</td></div>
    <div id="j_id145:processoDocumentoGridTabPanel_body" class="rich-panel-body">
      <table id="j_id145:processoDocumentoGridTab">{documentos}</table>
      <span class="pull-right text-muted">4 resultados encontrados</span>
    </div>
    """

    extrato = pje_tjmg.parse_detail_page(
        CNJ,
        html,
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam",
    )

    assert extrato["status"] == "ok"
    assert extrato["origem"]["movimentacoes_completas"] is True
    assert extrato["origem"]["documentos_completos"] is True
    assert extrato["origem"]["paginas_documentos_total"] == 1
    assert extrato["origem"]["paginas_documentos_lidas"] == 1
    assert "aviso_documentos" not in extrato["origem"]


def test_parse_detail_mantem_parcial_se_contagem_explicita_nao_bater():
    html = """
    <table id="j_id145:processoEvento"><tr><td>21/10/2026 - Juntada</td></tr></table>
    <div class="rich-slider"><td class="rich-inslider-right-num">1</td></div>
    <div id="j_id145:processoDocumentoGridTabPanel_body">
      <table id="j_id145:processoDocumentoGridTab">
        <tr class="rich-table-row"><td>Documento 1</td></tr>
      </table>
      <span class="pull-right text-muted">2 resultados encontrados</span>
    </div>
    """

    extrato = pje_tjmg.parse_detail_page(
        CNJ,
        html,
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam",
    )

    assert extrato["status"] == "partial"
    assert extrato["origem"]["documentos_completos"] is False
    assert "não foi possível verificar" in extrato["origem"]["aviso_documentos"]


def test_consultar_processo_usa_postback_observado_e_isola_dominios(monkeypatch):
    login = """
    <form id="fPP" action="/pje/ConsultaPublica/listView.seam">
      <input type="text"
        name="fPP:numProcesso-inputNumeroProcessoDecoration:numProcesso-inputNumeroProcesso">
      <input type="hidden" name="javax.faces.ViewState" value="state-1">
      <input type="radio" name="mascaraProcessoReferenciaRadio" value="on" checked>
      <input type="button" name="fPP:searchProcessos" value="Pesquisar">
    </form>
    <script>
      function executarReCaptcha(){
        if(false){grecaptcha.execute();return false;}
        executarPesquisa();
      }
    </script>
    <script id="fPP:j_id261" type="text/javascript">
      executarPesquisa=function(){A4J.AJAX.Submit('fPP',null,{'similarityGroupingId':'fPP:j_id261','actionUrl':'/pje/ConsultaPublica/listView.seam','parameters':{'fPP:j_id261':'fPP:j_id261'}})};
    </script>
    """
    result = f"""
    <table id="fPP:processosTable"><tr><th>Processo</th></tr><tr>
      <td>{CNJ}<a title="Ver Detalhes"
        onclick="openPopUp('Consulta pública',
          '/pje/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam?ca=fixture')">
        Ver detalhes do processo</a></td>
    </tr></table>
    """
    detail = f"""
    <table id="j_id145:processoEvento"><tr><th>Movimento</th><th>Documento</th></tr>
      <tr><td>21/10/2026 17:09:50 - Juntada de petição de ciência</td><td></td></tr>
    </table>
    <table id="j_id145:processoDocumentoGridTab"><tr><th>Documento</th></tr></table>
    <table><tr><td>Número Processo {CNJ}</td></tr></table>
    """

    class FakeSession:
        headers = {}
        timeout = 10

        def __init__(self):
            self.get_calls = []
            self.post_calls = []

        def get(self, url, **kwargs):
            self.get_calls.append(url)
            body = login if len(self.get_calls) == 1 else detail
            return SimpleNamespace(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/html; charset=UTF-8"},
                content=body.encode(),
                text=body,
            )

        def post(self, url, **kwargs):
            self.post_calls.append((url, kwargs["data"], kwargs.get("headers", {})))
            return SimpleNamespace(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/xml; charset=UTF-8"},
                content=result.encode(),
                text=result,
            )

    session = FakeSession()
    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)

    extrato = pje_tjmg.consultar_processo(CNJ, session=session)

    assert extrato["dados_basicos"]["numero"] == CNJ
    assert extrato["movimentacoes"][0]["titulo"] == "Juntada de petição de ciência"
    assert len(session.post_calls) == 1
    url, fields, headers = session.post_calls[0]
    assert url.startswith(f"{ORIGIN}/pje/ConsultaPublica/listView.seam")
    assert (
        fields["fPP:numProcesso-inputNumeroProcessoDecoration:numProcesso-inputNumeroProcesso"]
        == CNJ
    )
    assert fields["fPP:j_id261"] == "fPP:j_id261"
    assert fields["javax.faces.ViewState"] == "state-1"
    assert headers["Faces-Request"] == "partial/ajax"


def test_extrai_postback_de_busca_no_script_sem_id_do_painel():
    soup = BeautifulSoup(
        """
        <script>
          executarPesquisa=function(){A4J.AJAX.Submit('fPP',null,{
            'similarityGroupingId':'fPP:j_id261',
            'actionUrl':'/pje/ConsultaPublica/listView.seam;jsessionid=abc',
            'parameters':{'fPP:j_id261':'fPP:j_id261'}
          })};
        </script>
        <script id="fPP:j_id206:classeJudicial_script">
          A4J.AJAX.Submit('fPP',event,{
            'similarityGroupingId':'fPP:j_id206:suggest',
            'actionUrl':'/pje/ConsultaPublica/listView.seam',
            'parameters':{'fPP:j_id206:suggest':'fPP:j_id206:suggest','ajaxSingle':'fPP:j_id206'}
          });
        </script>
        """,
        "html.parser",
    )
    assert pje_tjmg._extrair_evento_busca(soup) == (
        "fPP",
        "fPP:j_id261",
        "/pje/ConsultaPublica/listView.seam;jsessionid=abc",
    )


def test_mescla_documentos_paginados_sem_repetir_ids_entre_paginas():
    documentos = [{"cd_documento": "101", "href": "https://pje.example/doc?id=101"}]

    pje_tjmg._adicionar_documentos_unicos(
        documentos,
        [
            {"cd_documento": "101", "href": "https://pje.example/doc?id=101"},
            {"cd_documento": "202", "href": "https://pje.example/doc?id=202"},
            {"cd_documento": "202", "href": "https://pje.example/doc?id=202"},
        ],
    )

    assert [documento["cd_documento"] for documento in documentos] == ["101", "202"]


@pytest.mark.parametrize("timeout", [None, 0, float("nan"), float("inf"), 86401])
def test_consultar_processo_rejeita_timeout_invalido_antes_do_request(monkeypatch, timeout):
    class SessionSemRede:
        def get(self, *args, **kwargs):
            pytest.fail("Timeout inválido não pode chegar ao transporte HTTP")

    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="timeout"):
        pje_tjmg.consultar_processo(CNJ, session=SessionSemRede(), timeout=timeout)


@pytest.mark.parametrize("prazo_total", [True, -1, float("nan"), float("inf"), 86401])
def test_consultar_processo_rejeita_prazo_total_invalido_antes_do_request(monkeypatch, prazo_total):
    class SessionSemRede:
        def get(self, *args, **kwargs):
            pytest.fail("Prazo total inválido não pode chegar ao transporte HTTP")

    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="prazo_total"):
        pje_tjmg.consultar_processo(CNJ, session=SessionSemRede(), prazo_total=prazo_total)


@pytest.mark.parametrize(
    "response_format",
    [
        "partial",
        "html",
        "wrong_page",
        "unavailable",
        "invalid_xml",
        "wrong_container",
        "no_table",
        "deadline",
    ],
)
def test_consultar_processo_percorre_paginas_publicas_de_movimentos_e_documentos(
    monkeypatch, response_format
):
    def slider_form(form_id, slider_id, field_id, event_id, container_id, page):
        action_url = "/pje/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
        onchange = (
            f"A4J.AJAX.Submit(\\'{form_id}\\',event,"
            f"{{\\'similarityGroupingId\\':\\'{event_id}\\',"
            f"\\'actionUrl\\':\\'{action_url}\\',"
            f"\\'containerId\\':\\'{container_id}\\',"
            f"\\'parameters\\':{{\\'{event_id}\\':\\'{event_id}\\'}}}} )"
        )
        return f"""
        <form id="{form_id}" action="javascript:A4J.AJAX.SubmitForm('{form_id}',{{
          'actionUrl':'{action_url}','containerId':'{container_id}'}})">
          <table class="rich-slider" id="{slider_id}"><tr>
            <td class="rich-inslider-left-num">1</td>
            <td class="rich-inslider-right-num">2</td>
            <td><input class="rich-inslider-field" type="text"
              id="{field_id}Input" name="{field_id}" value="{page}"></td>
          </tr></table>
          <input type="hidden" name="{form_id}" value="{form_id}">
          <input type="hidden" name="autoScroll" value="">
          <input type="hidden" name="javax.faces.ViewState" value="state-{page}">
          <script>new Richfaces.Slider("{slider_id}",{{'minValue':'1',
            'maxValue':'2','sliderValue':'{page}','onchange':'{onchange}'}})</script>
        </form>
        """

    def detail_page(movement_page, document_page):
        movement = (
            "05/10/2026 - Movimento da página um"
            if movement_page == 1
            else "06/10/2026 - Movimento da página dois"
        )
        document_id = "101" if document_page == 1 else "202"
        doc_url = f"{ORIGIN}{pje_tjmg.PJE_DOCUMENT_PATH}?ca=fixture&idProcessoDoc={document_id}"
        movement_form = slider_form(
            "movement-form",
            "movement-slider",
            "movement-field",
            "movement-event",
            "movement-container",
            movement_page,
        )
        document_form = slider_form(
            "document-form",
            "document-slider",
            "document-field",
            "document-event",
            "document-container",
            document_page,
        )
        return f"""
        <div id="movement-container">{movement_form}
          <table id="j_id145:processoEvento"><tr><th>Movimento</th></tr>
            <tr><td>{movement}</td></tr>
          </table>
        </div>
        <div id="document-container">{document_form}
          <table id="j_id145:processoDocumentoGridTab"><tr><th>Documento</th></tr>
            <tr><td><a title="Visualizar" onclick="openPopUp('doc','{doc_url}')">
              Peça {document_id}</a></td></tr>
          </table>
        </div>
        """

    campo_processo = "fPP:numProcesso-inputNumeroProcessoDecoration:numProcesso-inputNumeroProcesso"
    login = """
    <form id="fPP"><input name="{campo_processo}">
      <input name="javax.faces.ViewState" value="login-state"></form>
    <script>function executarReCaptcha(){if(false){grecaptcha.execute();return false;}
      executarPesquisa();}</script>
    <script id="fPP:j_id261">A4J.AJAX.Submit('fPP',null,{'similarityGroupingId':'fPP:j_id261',
      'actionUrl':'/pje/ConsultaPublica/listView.seam',
      'parameters':{'fPP:j_id261':'fPP:j_id261'}})</script>
    """.replace("{campo_processo}", campo_processo)
    result = f"""
    <table id="fPP:processosTable"><tr><td>{CNJ}<a title="Ver Detalhes"
      onclick="openPopUp('Consulta pública',
      '/pje/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam?ca=fixture')">
      Ver detalhes</a></td></tr></table>
    """

    class FakeSession:
        headers = {}
        timeout = 10

        def __init__(self):
            self.get_count = 0
            self.posts = []

        def get(self, url, **kwargs):
            self.get_count += 1
            if response_format == "deadline":
                clock[0] += 0.1
            body = login if self.get_count == 1 else detail_page(1, 1)
            return SimpleNamespace(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/html; charset=UTF-8"},
                content=body.encode(),
                text=body,
            )

        def post(self, url, **kwargs):
            fields = kwargs["data"]
            self.posts.append((url, fields, kwargs.get("headers", {})))
            if response_format == "deadline" and "movement-event" in fields:
                clock[0] += 0.3
            elif response_format == "deadline":
                clock[0] += 0.1
            if response_format == "unavailable" and "movement-event" in fields:
                return SimpleNamespace(
                    url=url,
                    status_code=503,
                    headers={"Content-Type": "text/html; charset=UTF-8"},
                    content=b"",
                    text="",
                )
            if response_format == "invalid_xml" and "movement-event" in fields:
                body = "<partial-response>"
            elif response_format == "wrong_container" and "movement-event" in fields:
                body = '<partial-response><update id="outro" /></partial-response>'
            elif response_format == "no_table" and "movement-event" in fields:
                body = '<input name="movement-field" value="2">'
            elif response_format == "wrong_page" and "movement-event" in fields:
                body = detail_page(1, 1)
            elif response_format == "html" and "movement-event" in fields:
                body = detail_page(2, 1)
            elif response_format == "html" and "document-event" in fields:
                body = detail_page(2, 2)
            elif "movement-event" in fields:
                body = """
                <partial-response><changes>
                  <update id="movement-container"><![CDATA[
                    <div id="movement-container">
                      <input name="movement-field" value="2">
                      <table id="j_id145:processoEvento"><tr><td>
                        06/10/2026 - Movimento da página dois</td></tr></table>
                    </div>
                  ]]></update>
                  <update id="javax.faces.ViewState"><![CDATA[state-2]]></update>
                </changes></partial-response>
                """
            elif "document-event" in fields:
                body = f"""
                <partial-response><changes>
                  <update id="document-container"><![CDATA[
                    <div id="document-container">
                      <input name="document-field" value="2">
                      <table id="j_id145:processoDocumentoGridTab"><tr><td>
                        <a title="Visualizar" onclick="openPopUp('doc',
                          '{ORIGIN}{pje_tjmg.PJE_DOCUMENT_PATH}?ca=fixture&idProcessoDoc=202')">
                          Peça 202</a></td></tr>
                    </table></div>
                  ]]></update>
                  <update id="javax.faces.ViewState"><![CDATA[state-2]]></update>
                </changes></partial-response>
                """
            else:
                body = result
            return SimpleNamespace(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/xml; charset=UTF-8"},
                content=body.encode(),
                text=body,
            )

    session = FakeSession()
    clock = [0.0]
    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)
    if response_format == "deadline":
        monkeypatch.setattr(pje_tjmg.time, "monotonic", lambda: clock[0])

    extrato = pje_tjmg.consultar_processo(
        CNJ,
        session=session,
        prazo_total=0.5 if response_format == "deadline" else pje_tjmg.PRAZO_TOTAL,
    )

    movimentos_completos = response_format in {"partial", "html"}
    expected_movements = ["Movimento da página um"]
    if movimentos_completos:
        expected_movements.append("Movimento da página dois")
    assert [item["titulo"] for item in extrato["movimentacoes"]] == expected_movements
    documentos = extrato["documentos"]["publicos_candidatos_unicos"]
    expected_documents = ["101"] if response_format == "deadline" else ["101", "202"]
    assert [item["cd_documento"] for item in documentos] == expected_documents
    assert extrato["origem"]["movimentacoes_completas"] is movimentos_completos
    assert extrato["origem"]["documentos_completos"] is (response_format != "deadline")
    assert extrato["origem"]["paginas_movimentacoes_total"] == 2
    assert extrato["origem"]["paginas_movimentacoes_lidas"] == (2 if movimentos_completos else 1)
    assert extrato["origem"]["paginas_documentos_total"] == 2
    assert extrato["origem"]["paginas_documentos_lidas"] == (
        1 if response_format == "deadline" else 2
    )
    assert extrato["status"] == ("ok" if movimentos_completos else "partial")
    assert len(session.posts) == (2 if response_format == "deadline" else 3)
    assert session.posts[1][1]["movement-field"] == "2"
    assert session.posts[1][1]["movement-event"] == "movement-event"
    assert session.posts[1][1]["AJAXREQUEST"] == "movement-container"
    assert list(session.posts[1][1]) == [
        "AJAXREQUEST",
        "movement-field",
        "movement-form",
        "autoScroll",
        "javax.faces.ViewState",
        "movement-event",
        "AJAX:EVENTS_COUNT",
    ]
    assert "Faces-Request" not in session.posts[1][2]
    assert "X-Requested-With" not in session.posts[1][2]
    if response_format != "deadline":
        assert session.posts[2][1]["document-field"] == "2"
        assert session.posts[2][1]["document-event"] == "document-event"
        assert session.posts[2][1]["AJAXREQUEST"] == "document-container"


def test_consultar_processo_para_se_o_recaptcha_estiver_ativo():
    class FakeSession:
        headers = {}
        timeout = 10

        def __init__(self):
            self.posts = 0

        def get(self, url, **kwargs):
            body = """
            <form id="fPP"></form>
            <script>function executarReCaptcha(){grecaptcha.execute();}</script>
            """
            return SimpleNamespace(
                url=url,
                status_code=200,
                headers={"Content-Type": "text/html"},
                content=body.encode(),
                text=body,
            )

        def post(self, url, **kwargs):
            self.posts += 1
            raise AssertionError("POST não deve contornar desafio do portal")

    session = FakeSession()

    with pytest.raises(AcessoRestrito, match="reCAPTCHA"):
        pje_tjmg.consultar_processo(CNJ, session=session)

    assert session.posts == 0


@pytest.mark.parametrize(
    ("status", "erro", "mensagem"),
    [
        (401, AcessoRestrito, "401"),
        (403, AcessoRestrito, "403"),
        (404, ProcessoNaoEncontrado, "não encontrada"),
        (429, ConsultaIndisponivel, "429"),
        (503, ConsultaIndisponivel, "503"),
        (400, ConsultaIndisponivel, "400"),
        (None, ConsultaIndisponivel, "Timeout"),
    ],
)
def test_consulta_pje_classifica_falha_antes_da_busca(monkeypatch, status, erro, mensagem):
    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)

    def get(url, **kwargs):
        if status is None:
            raise requests.Timeout("diagnóstico privado")
        return SimpleNamespace(status_code=status)

    with pytest.raises(erro, match=mensagem) as falha:
        pje_tjmg.consultar_processo(CNJ, session=SimpleNamespace(get=get))

    assert "diagnóstico privado" not in str(falha.value)


@pytest.mark.parametrize(
    ("html", "erro", "mensagem"),
    [
        ("", AcessoRestrito, "botão público"),
        ('<a id="j_id41:downloadPDF"></a>', ConsultaIndisponivel, "mudou de formato"),
        (
            """<a id="j_id41:downloadPDF"
              onclick="jsfcljs(document.getElementById('ausente'),{'doc':'1'},'');"></a>""",
            ConsultaIndisponivel,
            "formulário de geração",
        ),
        (
            """<form id="documento" action="/rota-inesperada">
              <a id="j_id41:downloadPDF"
              onclick="jsfcljs(document.getElementById('documento'),{'doc':'1'},'');"></a>
            </form>""",
            URLInvalida,
            "rota",
        ),
    ],
)
def test_obter_pdf_pje_exige_formulario_publico_reconhecido(monkeypatch, html, erro, mensagem):
    url = f"{ORIGIN}{pje_tjmg.PJE_DOCUMENT_PATH}?idProcessoDoc=123"
    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)
    sessao = SimpleNamespace(
        get=lambda *a, **k: SimpleNamespace(url=url, content=html.encode(), status_code=200)
    )

    with pytest.raises(erro, match=mensagem):
        pje_tjmg.obter_pdf_publico(url, session=sessao)


def test_captcha_guard_rejeita_funcao_com_chamada_ativa_apesar_do_ramo_inativo():
    html = """
    <script>
      function executarReCaptcha(){
        if (false) { grecaptcha.execute(); return false; }
        grecaptcha.execute();
        executarPesquisa();
      }
    </script>
    """

    assert pje_tjmg._captcha_desativado(html) is False


def test_ler_documento_público_usa_formulario_oficial_e_limita_saida(monkeypatch):
    url = (
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/"
        "documentoSemLoginHTML.seam?ca=fixture&idProcessoDoc=123"
    )
    html = """
    <form id="j_id41"
      action="/pje/ConsultaPublica/DetalheProcessoConsultaPublica/documentoSemLoginHTML.seam">
      <input type="hidden" name="j_id41" value="j_id41">
      <input type="hidden" name="javax.faces.ViewState" value="state-2">
      <a id="j_id41:downloadPDF"
        onclick="jsfcljs(document.getElementById('j_id41'),
          {'j_id41:downloadPDF':'j_id41:downloadPDF','ca':'fixture','idProcDocBin':'123'},'');">
        Gerar PDF</a>
    </form>
    """

    class FakeResponse:
        def __init__(self, url, content, content_type):
            self.url = url
            self.status_code = 200
            self.headers = {"Content-Type": content_type, "Content-Length": str(len(content))}
            self.content = content
            self._content = content
            self.closed = False

        def iter_content(self, chunk_size):
            yield self._content

        def close(self):
            self.closed = True

    class FakeSession:
        headers = {}
        timeout = 10

        def __init__(self):
            self.post_data = None
            self.pdf_response = None

        def get(self, request_url, **kwargs):
            return FakeResponse(request_url, html.encode(), "text/html")

        def post(self, request_url, **kwargs):
            self.post_data = kwargs["data"]
            self.pdf_response = FakeResponse(request_url, b"%PDF-1.7\nfixture", "application/pdf")
            return self.pdf_response

    session = FakeSession()
    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        pje_tjmg.esaj,
        "extrair_texto_pdf_bytes",
        lambda content, max_chars: ("texto da peça", "texto_extraido"),
    )

    resultado = pje_tjmg.ler_documento_publico(url, session=session, max_chars=40)

    assert resultado == {
        "status": "texto_extraido",
        "mime_type": "application/pdf",
        "bytes": len(b"%PDF-1.7\nfixture"),
        "texto": "texto da peça",
        "texto_chars": len("texto da peça"),
        "truncado": False,
    }
    assert session.post_data["j_id41:downloadPDF"] == "j_id41:downloadPDF"
    assert session.post_data["idProcDocBin"] == "123"
    assert session.pdf_response.closed


@pytest.mark.parametrize("content_length", ["20", ""])
def test_obter_pdf_publico_aplica_limite_ao_tamanho_recebido(monkeypatch, content_length):
    url = (
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/"
        "documentoSemLoginHTML.seam?ca=fixture&idProcessoDoc=123"
    )
    html = (
        b'<form id="j_id41" action="/pje/ConsultaPublica/DetalheProcessoConsultaPublica/'
        b'documentoSemLoginHTML.seam">'
        b'<input name="javax.faces.ViewState" value="state">'
        b'<a id="j_id41:downloadPDF" '
        b"onclick=\"jsfcljs(document.getElementById('j_id41'), "
        b"{'idProcDocBin':'123'},'');\">Gerar PDF</a></form>"
    )

    class FakeResponse:
        def __init__(self, response_url, body, response_length=""):
            self.url = response_url
            self.status_code = 200
            self.content = body
            self.headers = {"Content-Length": response_length} if response_length else {}
            self.closed = False

        def iter_content(self, chunk_size):
            yield b"%PDF-1.7\ncontent exceeds requested limit"

        def close(self):
            self.closed = True

    page = FakeResponse(url, html)
    pdf = FakeResponse(url, b"", content_length)
    responses = iter([page, pdf])
    monkeypatch.setattr(pje_tjmg, "_request", lambda *args, **kwargs: next(responses))

    with pytest.raises(ConsultaIndisponivel, match="limite de tamanho solicitado"):
        pje_tjmg.obter_pdf_publico(url, max_bytes=8)

    assert pdf.closed


def test_obter_pdf_publico_rejeita_limites_invalidos():
    url = f"{pje_tjmg.PJE_ORIGIN}{pje_tjmg.PJE_DOCUMENT_PATH}?id=teste"
    for limite in (0, 1.5, "32", None, True):
        with pytest.raises(ValueError, match="max_bytes"):
            pje_tjmg.obter_pdf_publico(url, max_bytes=limite)


@pytest.mark.parametrize(
    ("status", "fragmento"),
    [
        ("pdf_parser_indisponivel", "nanojud[pdf]"),
        ("pdf_sem_texto_extraido", "digitalizado como imagem"),
    ],
)
def test_leitura_pje_informa_pdf_sem_texto_utilizavel(monkeypatch, status, fragmento):
    monkeypatch.setattr(pje_tjmg, "_gerar_pdf_publico", lambda *args, **kwargs: b"%PDF-fixture")
    monkeypatch.setattr(
        pje_tjmg.esaj, "extrair_texto_pdf_bytes", lambda *args, **kwargs: ("", status)
    )

    resultado = pje_tjmg.ler_documento_publico("https://pje.test/doc")

    assert resultado["status"] == status
    assert fragmento in resultado["mensagem"]


@pytest.mark.parametrize("max_chars", [-1, 1.5, "100", None, True])
def test_ler_documento_publico_rejeita_max_chars_invalido_antes_de_rede(monkeypatch, max_chars):
    monkeypatch.setattr(
        pje_tjmg,
        "_gerar_pdf_publico",
        lambda *args, **kwargs: pytest.fail("max_chars inválido não deve iniciar request"),
    )

    with pytest.raises(ValueError, match="max_chars"):
        pje_tjmg.ler_documento_publico("https://pje.test/doc", max_chars=max_chars)


def test_baixar_documento_publico_grava_pdf_validado(tmp_path, monkeypatch):
    url = (
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/"
        "documentoSemLoginHTML.seam?ca=fixture&idProcessoDoc=123"
    )
    destino = tmp_path / "peca.pdf"
    monkeypatch.setattr(pje_tjmg, "_pausar", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(pje_tjmg, "_gerar_pdf_publico", lambda *args, **kwargs: b"%PDF-1.7")
    resultado = pje_tjmg.baixar_documento_publico(url, destino)

    assert resultado == {"status": "baixado", "arquivo": str(destino), "bytes": 8}
    assert destino.read_bytes() == b"%PDF-1.7"
    assert not destino.with_suffix(".pdf.part").exists()


def test_baixar_documento_publico_substitui_arquivo_existente_que_nao_e_pdf(tmp_path, monkeypatch):
    url = (
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/"
        "documentoSemLoginHTML.seam?ca=fixture&idProcessoDoc=123"
    )
    destino = tmp_path / "peca.pdf"
    destino.write_bytes(b"arquivo truncado")
    monkeypatch.setattr(pje_tjmg, "_gerar_pdf_publico", lambda *args, **kwargs: b"%PDF-1.7")

    resultado = pje_tjmg.baixar_documento_publico(url, destino)

    assert resultado == {"status": "baixado", "arquivo": str(destino), "bytes": 8}
    assert destino.read_bytes() == b"%PDF-1.7"


def test_downloads_concorrentes_no_mesmo_destino_sao_atomicos(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    url = (
        f"{ORIGIN}/pje/ConsultaPublica/DetalheProcessoConsultaPublica/"
        "documentoSemLoginHTML.seam?ca=fixture&idProcessoDoc=123"
    )
    destino = tmp_path / "peca.pdf"
    barreira = Barrier(2)
    link_original = pje_tjmg.os.link

    def publicar_juntos(origem, destino):
        barreira.wait(timeout=5)
        link_original(origem, destino)

    monkeypatch.setattr(pje_tjmg.os, "link", publicar_juntos)
    monkeypatch.setattr(pje_tjmg, "_gerar_pdf_publico", lambda *args, **kwargs: b"%PDF-1.7")

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(
            pool.map(
                lambda _: pje_tjmg.baixar_documento_publico(url, destino),
                range(2),
            )
        )

    assert sorted(item["status"] for item in resultados) == ["baixado", "existente"]
    assert destino.read_bytes() == b"%PDF-1.7"
    assert list(tmp_path.glob("*.part")) == []


def test_ler_documento_rejeita_url_de_outro_host():
    with pytest.raises(URLInvalida):
        pje_tjmg.ler_documento_publico(
            "https://example.com/pje/ConsultaPublica/DetalheProcessoConsultaPublica/"
            "documentoSemLoginHTML.seam?ca=fixture"
        )


def test_pje_tjmg_fonte_opcional_e_envelope_parcial(monkeypatch):
    assert normalizar_fonte(" PJE_TJMG ") == "pje_tjmg"
    assert normalizar_fontes() == ("esaj", "datajud", "djen")
    assert "pje_tjmg" not in normalizar_fontes()
    monkeypatch.setattr(
        extraction.pje_tjmg,
        "consultar_processo",
        lambda *args, **kwargs: {
            "status": "partial",
            "origem": {
                "aviso_movimentacoes": "Apenas a página inicial foi lida.",
                "aviso_documentos": "Há mais documentos.",
            },
            "dados_basicos": {"numero": CNJ},
            "movimentacoes": [{"data": "2026-10-21", "titulo": "Juntada", "teor": "Juntada"}],
        },
    )

    envelope = extraction.extract_process(CNJ, sources=["pje_tjmg"], prazo_total=5)

    assert envelope["status"] == "partial"
    assert envelope["source_status"]["pje_tjmg"]["status"] == "partial"
    assert envelope["timeline"][0]["fonte"] == "pje_tjmg"
    assert len(envelope["warnings"]) == 2
