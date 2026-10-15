from pathlib import Path

from bs4 import BeautifulSoup

from nanojud import esaj
from nanojud.exceptions import AcessoRestrito, ProcessoNaoEncontrado

FIXTURE = Path(__file__).parent / "fixtures" / "esaj_processo_basico.html"


def _soup() -> BeautifulSoup:
    return BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")


def test_montar_url_busca_valida_numero_cnj():
    url = esaj.montar_url_busca("1076539-20.2019.8.26.0100")

    assert "numeroDigitoAnoUnificado=1076539-20.2019" in url
    assert "foroNumeroUnificado=0100" in url


def test_montar_url_busca_rejeita_numero_invalido():
    try:
        esaj.montar_url_busca("numero-invalido")
    except ValueError as exc:
        assert "CNJ" in str(exc)
    else:
        raise AssertionError("Número CNJ inválido deveria gerar ValueError")


def test_extrair_dados_basicos_da_fixture():
    dados = esaj.extrair_dados_basicos(_soup(), "https://example.test/processo")

    assert dados["numero"] == "1076539-20.2019.8.26.0100"
    assert dados["classe"] == "Ação Civil Pública"
    assert dados["assunto"] == "Meio Ambiente"
    assert dados["foro"] == "Foro Central Cível"
    assert dados["vara"] == "2ª Vara Cível"
    assert dados["juiz"] == "Dr. Juiz Exemplo"


def test_extrair_partes_classifica_polos():
    partes = esaj.extrair_partes(_soup())

    assert partes["polo_ativo"][0]["nomes"] == ["Empresa Autora S/A"]
    assert partes["polo_passivo"][0]["nomes"] == ["Empresa Ré Ltda"]
    assert "OAB/SP 123456" in partes["polo_ativo"][0]["advogados"][0]


def test_extrair_movimentacoes_preserva_ordem_e_texto():
    movimentacoes = esaj.extrair_movimentacoes(_soup())

    assert len(movimentacoes) == 2
    assert movimentacoes[0]["ordem"] == 1
    assert movimentacoes[0]["data"] == "29/07/2026"
    assert movimentacoes[0]["titulo"] == "Publicação de intimação"
    assert movimentacoes[1]["texto"] == "Conclusos para decisão"


def test_extrair_movimentacoes_com_documentos_e_metadados():
    movimentacao = esaj.extrair_movimentacoes(_soup())[0]

    assert movimentacao["metadados"]["data_disponibilizacao"] == "29/07/2026"
    assert movimentacao["metadados"]["teor_do_ato"] == "Texto complementar da movimentação."
    assert movimentacao["documentos"][0]["cd_documento"] == "123456"
    assert movimentacao["documentos"][0]["status_acesso"] == "publico_candidato"
    assert movimentacao["documentos"][0]["titulo"] == "Decisão"
    assert movimentacao["documentos"][1]["status_acesso"] == "restrito_por_senha"


def test_extrair_tabelas_complementares():
    soup = _soup()

    assert esaj.extrair_audiencias(soup)[0]["situacao"] == "Designada"
    assert esaj.extrair_peticoes_diversas(soup)[0]["descricao"] == "Manifestação"
    relacionados = esaj.extrair_relacionados(soup)
    assert relacionados["incidentes"][0]["classe"] == "Cumprimento de Sentença"
    assert relacionados["apensos"][0]["motivo"] == "Dependência"


def test_detectar_estado_pagina_rejeita_resposta_sem_processo():
    soup = BeautifulSoup("<html><body>Processo não encontrado</body></html>", "html.parser")
    response = type("Response", (), {"url": "https://example.test"})()

    try:
        esaj.detectar_estado_pagina(soup, response)
    except ProcessoNaoEncontrado:
        pass
    else:
        raise AssertionError("Página sem processo deveria gerar ProcessoNaoEncontrado")


def test_detectar_estado_pagina_aceita_processo_com_popup_senha_oculto():
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <span id="numeroProcesso">1076539-20.2019.8.26.0100</span>
            <form id="popupSenha" style="display: none">
              Se for uma parte ou interessado, digite a senha do processo
            </form>
          </body>
        </html>
        """,
        "html.parser",
    )
    response = type("Response", (), {"url": "https://example.test"})()

    esaj.detectar_estado_pagina(soup, response)


class FakeResponse:
    status_code = 200
    url = "https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=ABC"

    def __init__(self, text: str):
        self.text = text
        self.content = text.encode("utf-8")


class FakeSession:
    headers = {}

    def get(self, url, **kwargs):
        return FakeResponse(FIXTURE.read_text(encoding="utf-8"))


def test_montar_extrato_orquestra_parser_com_session_fake():
    extrato = esaj.montar_extrato("1076539-20.2019.8.26.0100", session=FakeSession())

    assert extrato["status"] == "ok"
    assert extrato["dados_basicos"]["classe"] == "Ação Civil Pública"
    assert len(extrato["movimentacoes"]) == 2
    assert len(extrato["documentos"]["publicos_candidatos_unicos"]) == 1
    assert len(extrato["documentos"]["restritos_por_senha_unicos"]) == 1


def test_extrair_request_scope():
    texto = 'antes var requestScope = [{"data": {"title": "Doc"}, "children": []}]; depois'

    assert esaj.extrair_request_scope(texto) == '[{"data": {"title": "Doc"}, "children": []}]'


def test_helpers_retornam_vazio_quando_elementos_ausentes():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")

    assert esaj.texto_id(soup, "ausente") == ""
    assert esaj.processo_codigo("https://example.test") == ""
    assert esaj.extrair_campos_rotulados(None) == {}
    assert esaj.linhas_dados_tabela(None) == []
    assert esaj.extrair_movimentacoes(soup) == []


def test_detectar_estado_pagina_rejeita_captcha_e_senha():
    response = type("Response", (), {"url": "https://example.test"})()

    for html in [
        '<html><body><div id="captcha"></div></body></html>',
        "<html><body>Senha do processo obrigatória</body></html>",
    ]:
        try:
            esaj.detectar_estado_pagina(BeautifulSoup(html, "html.parser"), response)
        except AcessoRestrito:
            pass
        else:
            raise AssertionError("Página restrita deveria gerar AcessoRestrito")


def test_extrair_partes_usa_tabela_todas_partes_por_classe():
    soup = BeautifulSoup(
        """
        <table class="todasPartes">
          <tr><td class="tipoDeParticipacao">Requerente</td>
          <td class="nomeParteEAdvogado">Pessoa Autora</td></tr>
        </table>
        """,
        "html.parser",
    )

    partes = esaj.extrair_partes(soup)

    assert partes["polo_ativo"][0]["nomes"] == ["Pessoa Autora"]


def test_extrair_titulo_teor_movimentacao_sem_link():
    tag = BeautifulSoup(
        '<td class="descricaoMovimentacao">Despacho<br/>Texto do despacho</td>',
        "html.parser",
    ).td

    titulo, teor, texto = esaj.extrair_titulo_teor_movimentacao(tag)

    assert titulo == "Despacho"
    assert teor == "Texto do despacho"
    assert texto == "Despacho Texto do despacho"


def test_extrair_request_scope_retorna_none_para_entradas_invalidas():
    assert esaj.extrair_request_scope("sem marcador") is None
    assert esaj.extrair_request_scope("var requestScope = sem lista") is None
    assert esaj.extrair_request_scope('var requestScope = [{"aberto": true}') is None


def test_classificar_documento_e_titulo_por_query():
    html = (
        '<a id="linkMovVincProc-999" href="abrirDocumentoVinculadoMovimentacao.do?'
        'cdDocumento=999&nmRecursoAcessado=Decis%C3%A3o"></a>'
    )
    link = BeautifulSoup(html, "html.parser").a

    assert esaj.classificar_documento("#liberarAutoPorSenha") == "restrito_por_senha"
    assert esaj.classificar_documento("outro") == "outro"
    assert esaj.extrair_cd_documento(link, link["href"]) == "999"
    assert esaj.titulo_documento(link, link["href"]) == "Decisão"


def test_incidentes_ignora_linha_de_espacamento_vazia():
    html = """
    <h2>Incidentes</h2>
    <table>
      <tr><td></td><td></td></tr>
      <tr>
        <td>12/12/2018</td>
        <td>
          <a class="incidente" href="/cpopg/show.do?processo.codigo=INC">
            Requisição de Pequeno Valor
          </a>
        </td>
      </tr>
    </table>
    """

    incidentes = esaj.extrair_relacionados(BeautifulSoup(html, "html.parser"))["incidentes"]

    assert [i["classe"] for i in incidentes] == ["Requisição de Pequeno Valor"]
