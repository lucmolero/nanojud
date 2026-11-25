from pathlib import Path

from nanojud import api


def _extrato():
    return {
        "status": "ok",
        "origem": {"url_final": "https://example.test"},
        "dados_basicos": {
            "numero": "1076539-20.2019.8.26.0100",
            "classe": "Ação Civil Pública",
            "assunto": "Meio Ambiente",
            "foro": "Foro Central",
            "vara": "2ª Vara",
            "juiz": "Dr. Exemplo",
        },
        "partes": {
            "principais": [],
            "todas": [],
            "polo_ativo": [{"nomes": ["Empresa Autora"]}],
            "polo_passivo": [{"nomes": ["Empresa Ré"]}],
            "polo_desconhecido": [],
        },
        "movimentacoes": [{"titulo": "Conclusos", "data": "31/07/2026"}],
        "documentos": {"publicos_candidatos_unicos": [{"cd_documento": "123"}]},
    }


def test_api_consultar_tjrj_repassa_limite_de_paginas(monkeypatch):
    chamadas = {}
    resultado = {"status": "partial"}

    def consultar(numero, **kwargs):
        chamadas.update(numero=numero, **kwargs)
        return resultado

    monkeypatch.setattr(api.tjrj, "consultar_processo", consultar)

    assert (
        api.consultar_tjrj_1g("0032991-06.2012.8.19.0066", max_paginas_movimentos=75) == resultado
    )
    assert chamadas["max_paginas_movimentos"] == 75


def test_search_processo_signature():
    resultado = api.search_processo
    assert callable(resultado)


def test_get_partes_signature():
    resultado = api.get_partes
    assert callable(resultado)


def test_get_extrato_signature():
    resultado = api.get_extrato
    assert callable(resultado)


def test_get_extrato_repassa_timeout_para_o_adaptador(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(
        api.esaj,
        "montar_extrato",
        lambda numero, **kwargs: chamadas.update(kwargs) or _extrato(),
    )

    api.get_extrato("1076539-20.2019.8.26.0100", timeout=7)

    assert chamadas["timeout"] == 7


def test_resumo_rapido_signature():
    resultado = api.resumo_rapido
    assert callable(resultado)


def test_consultar_djen_signature():
    resultado = api.consultar_djen
    assert callable(resultado)


def test_consultar_datajud_signature():
    resultado = api.consultar_datajud
    assert callable(resultado)


def test_consultar_eproc_tjsp_2g_repassa_parametros(monkeypatch):
    chamadas = []
    esperado = {"status": "partial", "origem": {"grau": "2G"}}
    monkeypatch.setattr(
        api.eproc_tjsp,
        "consultar_processo_2g",
        lambda numero, **kwargs: chamadas.append((numero, kwargs)) or esperado,
    )
    assert (
        api.consultar_eproc_tjsp_2g(
            "1001194-30.2024.8.26.0114", timeout=12, aguardar_desafio_interativo=True
        )
        == esperado
    )
    assert chamadas == [
        (
            "1001194-30.2024.8.26.0114",
            {"timeout": 12, "headless": False, "aguardar_desafio_interativo": True},
        )
    ]


def test_obter_pdf_pje_tjmg_repassa_limite_de_tamanho(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        api.pje_tjmg,
        "obter_pdf_publico",
        lambda url, **kwargs: chamadas.append((url, kwargs)) or b"%PDF-1.7",
    )

    conteudo = api.obter_pdf_pje_tjmg("url-publica", max_bytes=4096)

    assert conteudo == b"%PDF-1.7"
    assert chamadas == [("url-publica", {"session": None, "timeout": 30.0, "max_bytes": 4096})]


def test_consultar_pje_tjmg_repassa_orcamento_total(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        api.pje_tjmg,
        "consultar_processo",
        lambda numero, **kwargs: chamadas.append((numero, kwargs)) or {"status": "ok"},
    )

    resultado = api.consultar_pje_tjmg("5060583-19.2021.8.13.0024", prazo_total=17)

    assert resultado == {"status": "ok"}
    assert chamadas == [
        (
            "5060583-19.2021.8.13.0024",
            {"session": None, "timeout": 30.0, "prazo_total": 17},
        )
    ]


def test_consultar_tjmg_2g_legado_repassa_identidade_e_sessao(monkeypatch):
    chamadas = []
    esperado = {"status": "partial"}
    monkeypatch.setattr(
        api.tjmg_legado,
        "consultar_processo",
        lambda numero, identificador, **kwargs: (
            chamadas.append((numero, identificador, kwargs)) or esperado
        ),
    )
    assert (
        api.consultar_tjmg_2g_legado("2125575-44.2023.8.13.0000", "10000232125575004") == esperado
    )
    assert chamadas == [
        ("2125575-44.2023.8.13.0000", "10000232125575004", {"session": None, "timeout": 30.0})
    ]


def test_obter_documento_tjmg_legado_repassa_vinculo_e_opcoes(monkeypatch):
    chamadas = []
    session = object()
    esperado = (b"word-bytes", "application/msword")
    monkeypatch.setattr(
        api.tjmg_legado,
        "obter_documento_publico",
        lambda *args, **kwargs: chamadas.append((args, kwargs)) or esperado,
    )
    resultado = api.obter_documento_tjmg_2g_legado(
        "2125575-44.2023.8.13.0000",
        "10000232125575004",
        "12345",
        "2024",
        session=session,
        timeout=11,
        max_bytes=4096,
    )
    assert resultado == esperado
    assert chamadas == [
        (
            ("2125575-44.2023.8.13.0000", "10000232125575004", "12345", "2024"),
            {"session": session, "timeout": 11, "max_bytes": 4096},
        )
    ]


def test_obter_pdf_esaj_delega_para_cliente_configurado(monkeypatch):
    chamadas = []

    class FakeClient:
        def __init__(self, **kwargs):
            chamadas.append(("init", kwargs))

        def obter_pdf_esaj(self, numero, cd_documento, **kwargs):
            chamadas.append((numero, cd_documento, kwargs))
            return b"%PDF-1.7"

    monkeypatch.setattr(api, "NanoJudClient", FakeClient)

    def callback(numero, documentos):
        return None

    resultado = api.obter_pdf_esaj(
        "1076539-20.2019.8.26.0100",
        "123456",
        timeout=9,
        max_bytes=4096,
        senha_processo_provider=callback,
    )

    assert resultado == b"%PDF-1.7"
    assert chamadas == [
        (
            "init",
            {
                "config": api.NanoJudConfig(timeout=9),
                "session": None,
                "senha_processo_provider": callback,
            },
        ),
        (
            "1076539-20.2019.8.26.0100",
            "123456",
            {"max_bytes": 4096, "senha_processo": None},
        ),
    ]


def test_extract_process_signature():
    resultado = api.extract_process
    assert callable(resultado)


def test_create_client_signature():
    resultado = api.create_client
    assert callable(resultado)


def test_create_client_retorna_cliente_configuravel():
    client = api.create_client()

    assert client.config.timeout == 30.0
    assert client.cache is None


def test_search_processo_resume_extrato(monkeypatch):
    monkeypatch.setattr(api, "get_extrato", lambda numero, **kwargs: _extrato())

    resumo = api.search_processo("1076539-20.2019.8.26.0100")

    assert resumo["numero"] == "1076539-20.2019.8.26.0100"
    assert resumo["ultima_movimentacao"] == "Conclusos"


def test_search_processo_preserva_fonte_grau_data_e_completude(monkeypatch):
    extrato = _extrato()
    extrato["origem"].update(
        {
            "grau": "1g",
            "data_coleta": "2026-11-13T21:00:00+00:00",
            "movimentacoes_completas": False,
        }
    )
    monkeypatch.setattr(api, "get_extrato", lambda numero, **kwargs: extrato)

    resumo = api.search_processo("1076539-20.2019.8.26.0100")

    assert resumo["fonte"] == "esaj"
    assert resumo["grau"] == "1g"
    assert resumo["data_coleta"] == "2026-11-13T21:00:00+00:00"
    assert resumo["coleta_completa"] is False


def test_search_processo_preserva_incompletude_no_resumo(monkeypatch):
    extrato = _extrato()
    extrato["origem"]["movimentacoes_completas"] = False
    extrato["origem"]["aviso_movimentacoes"] = "A paginação foi interrompida."
    monkeypatch.setattr(api, "get_extrato", lambda numero, **kwargs: extrato)

    resumo = api.search_processo("1076539-20.2019.8.26.0100")

    assert resumo["status"] == "partial"
    assert "paginação foi interrompida" in resumo["mensagem"].lower()


def test_search_processo_usa_movimentacao_mais_recente_por_data(monkeypatch):
    extrato = _extrato()
    extrato["movimentacoes"] = [
        {"titulo": "Mais recente", "data": "31/07/2026"},
        {"titulo": "Mais antiga", "data": "01/01/2020"},
    ]
    monkeypatch.setattr(api, "get_extrato", lambda numero, **kwargs: extrato)

    resumo = api.search_processo("1076539-20.2019.8.26.0100")

    assert resumo["ultima_movimentacao"] == "Mais recente"
    assert resumo["ultima_data"] == "31/07/2026"


def test_resumo_rapido_usa_partes_do_extrato(monkeypatch):
    monkeypatch.setattr(api, "get_extrato", lambda numero, **kwargs: _extrato())

    resumo = api.resumo_rapido("1076539-20.2019.8.26.0100")

    assert "Empresa Autora" in resumo
    assert "Empresa Ré" in resumo


def test_baixar_pecas_delega_para_esaj(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(api.esaj, "criar_session", lambda **kwargs: object())
    monkeypatch.setattr(
        api.esaj,
        "preparar_documentos",
        lambda s, numero, mov, limite, **kwargs: chamadas.update(numero=numero),
    )

    def fake_baixar(session, movimentos, destino, limite, sobrescrever, *, max_bytes, timeout):
        chamadas["movimentos"] = movimentos
        chamadas["destino"] = destino
        chamadas["limite"] = limite
        chamadas["sobrescrever"] = sobrescrever
        chamadas["max_bytes"] = max_bytes
        chamadas["timeout"] = timeout
        return [{"status": "baixado"}]

    monkeypatch.setattr(api.esaj, "baixar_pecas_publicas", fake_baixar)

    resultado = api.baixar_pecas(_extrato(), Path("pecas"), sobrescrever=True, limite=1)

    assert resultado == [{"status": "baixado"}]
    assert chamadas["movimentos"][0]["documentos"][0]["cd_documento"] == "123"
    assert chamadas["limite"] == 1
    assert chamadas["max_bytes"] == api.esaj.MAX_DOCUMENT_DOWNLOAD_BYTES
    assert chamadas["timeout"] == 30


def test_ler_pecas_delega_para_esaj(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(api.esaj, "criar_session", lambda **kwargs: object())
    monkeypatch.setattr(
        api.esaj,
        "preparar_documentos",
        lambda s, numero, mov, limite, **kwargs: chamadas.update(numero=numero),
    )

    def fake_ler(session, movimentos, limite, max_chars, *, timeout):
        chamadas["movimentos"] = movimentos
        chamadas["limite"] = limite
        chamadas["max_chars"] = max_chars
        chamadas["timeout"] = timeout
        return [{"status": "texto_extraido"}]

    monkeypatch.setattr(api.esaj, "ler_pecas_publicas", fake_ler)

    resultado = api.ler_pecas(_extrato(), limite=2, max_chars=1200)

    assert resultado == [{"status": "texto_extraido"}]
    assert chamadas["movimentos"][0]["documentos"][0]["cd_documento"] == "123"
    assert chamadas["max_chars"] == 1200
    assert chamadas["timeout"] == 30
    assert chamadas["numero"]  # a sessão é preparada com o número do processo


def test_get_extrato_delega_parametros(monkeypatch):
    chamadas = {}

    def fake_montar(numero, **kwargs):
        chamadas["numero"] = numero
        chamadas.update(kwargs)
        return _extrato()

    monkeypatch.setattr(api.esaj, "montar_extrato", fake_montar)

    resultado = api.get_extrato(
        "1076539-20.2019.8.26.0100",
        baixar_pecas=True,
        limite_pecas=2,
        inspecionar_pecas=True,
        limite_inspecao_pecas=4,
        salvar_html=True,
    )

    assert resultado["status"] == "ok"
    assert chamadas["baixar_pecas"] is True
    assert chamadas["limite_pecas"] == 2
    assert chamadas["inspecionar_pecas"] is True
    assert chamadas["limite_inspecao_pecas"] == 4
    assert chamadas["salvar_html"] is True


def test_get_extrato_session_requests_sem_atributo_timeout_usa_timeout_finito(monkeypatch):
    numero = "1076539-20.2019.8.26.0100"

    class Response:
        status_code = 200

        def __init__(self, url):
            self.url = url
            self.text = f'<span id="numeroProcesso">{numero}</span>'
            self.content = self.text.encode()

    class SessionRequests:
        def __init__(self):
            self.timeouts = []

        def get(self, url, **kwargs):
            self.timeouts.append(kwargs.get("timeout"))
            return Response(url)

    monkeypatch.setattr(api.esaj, "detectar_estado_pagina", lambda *args: None)
    monkeypatch.setattr(api.esaj, "extrair_dados_basicos", lambda *args: {"numero": numero})
    monkeypatch.setattr(api.esaj, "extrair_movimentacoes", lambda *args: [])
    session = SessionRequests()

    api.get_extrato(numero, session=session)

    assert session.timeouts
    assert all(timeout == 30.0 for timeout in session.timeouts)


def test_get_partes_retorna_fallback(monkeypatch):
    monkeypatch.setattr(api, "get_extrato", lambda numero, **kwargs: {"status": "ok"})

    partes = api.get_partes("1076539-20.2019.8.26.0100")

    assert partes["polo_ativo"] == []


def test_baixar_pecas_usa_movimentacoes_quando_sem_documentos(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(api.esaj, "criar_session", lambda **kwargs: object())

    def fake_baixar(session, movimentos, destino, limite, sobrescrever, **kwargs):
        chamadas["movimentos"] = movimentos
        return []

    monkeypatch.setattr(api.esaj, "baixar_pecas_publicas", fake_baixar)

    api.baixar_pecas({"documentos": {}, "movimentacoes": [{"documentos": []}]}, Path("pecas"))

    assert chamadas["movimentos"] == [{"documentos": []}]


def test_consultar_djen_delega(monkeypatch):
    chamadas = {}

    def fake_consultar(numero, data_inicio=""):
        chamadas["numero"] = numero
        chamadas["data_inicio"] = data_inicio
        return [{"id": "1"}]

    monkeypatch.setattr(api.djen, "consultar_processo", fake_consultar)

    resultado = api.consultar_djen("1076539-20.2019.8.26.0100", data_inicio="2026-07-01")

    assert resultado == [{"id": "1"}]
    assert chamadas["data_inicio"] == "2026-07-01"


def test_consultar_datajud_delega(monkeypatch):
    chamadas = {}

    def fake_consultar(numero, api_key=None, include_raw=False, prazo_total=60.0):
        chamadas["numero"] = numero
        chamadas["api_key"] = api_key
        chamadas["include_raw"] = include_raw
        chamadas["prazo_total"] = prazo_total
        return {"status": "ok"}

    monkeypatch.setattr(api.datajud, "consultar_processo", fake_consultar)

    resultado = api.consultar_datajud(
        "1076539-20.2019.8.26.0100", api_key="abc", include_raw=True, prazo_total=12
    )

    assert resultado == {"status": "ok"}
    assert chamadas["api_key"] == "abc"
    assert chamadas["include_raw"] is True
    assert chamadas["prazo_total"] == 12


def test_extract_process_delega(monkeypatch):
    chamadas = {}

    def fake_extract(numero, **kwargs):
        chamadas["numero"] = numero
        chamadas.update(kwargs)
        return {"status": "ok", "timeline": []}

    monkeypatch.setattr(api.extraction, "extract_process", fake_extract)

    resultado = api.extract_process(
        "1076539-20.2019.8.26.0100",
        sources=("datajud",),
        datajud_api_key="abc",
        timeout=11,
    )

    assert resultado["status"] == "ok"
    assert chamadas["sources"] == ("datajud",)
    assert chamadas["timeout"] == 11
