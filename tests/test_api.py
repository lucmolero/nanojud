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


def test_search_processo_signature():
    resultado = api.search_processo
    assert callable(resultado)


def test_get_partes_signature():
    resultado = api.get_partes
    assert callable(resultado)


def test_get_extrato_signature():
    resultado = api.get_extrato
    assert callable(resultado)


def test_resumo_rapido_signature():
    resultado = api.resumo_rapido
    assert callable(resultado)


def test_consultar_djen_signature():
    resultado = api.consultar_djen
    assert callable(resultado)


def test_consultar_datajud_signature():
    resultado = api.consultar_datajud
    assert callable(resultado)


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
    monkeypatch.setattr(api.esaj, "criar_session", lambda: object())
    monkeypatch.setattr(
        api.esaj,
        "preparar_documentos",
        lambda s, numero, mov, limite: chamadas.update(numero=numero),
    )

    def fake_baixar(session, movimentos, destino, limite, sobrescrever):
        chamadas["movimentos"] = movimentos
        chamadas["destino"] = destino
        chamadas["limite"] = limite
        chamadas["sobrescrever"] = sobrescrever
        return [{"status": "baixado"}]

    monkeypatch.setattr(api.esaj, "baixar_pecas_publicas", fake_baixar)

    resultado = api.baixar_pecas(_extrato(), Path("pecas"), sobrescrever=True, limite=1)

    assert resultado == [{"status": "baixado"}]
    assert chamadas["movimentos"][0]["documentos"][0]["cd_documento"] == "123"
    assert chamadas["limite"] == 1


def test_ler_pecas_delega_para_esaj(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(api.esaj, "criar_session", lambda: object())
    monkeypatch.setattr(
        api.esaj,
        "preparar_documentos",
        lambda s, numero, mov, limite: chamadas.update(numero=numero),
    )

    def fake_ler(session, movimentos, limite, max_chars):
        chamadas["movimentos"] = movimentos
        chamadas["limite"] = limite
        chamadas["max_chars"] = max_chars
        return [{"status": "texto_extraido"}]

    monkeypatch.setattr(api.esaj, "ler_pecas_publicas", fake_ler)

    resultado = api.ler_pecas(_extrato(), limite=2, max_chars=1200)

    assert resultado == [{"status": "texto_extraido"}]
    assert chamadas["movimentos"][0]["documentos"][0]["cd_documento"] == "123"
    assert chamadas["max_chars"] == 1200
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


def test_get_partes_retorna_fallback(monkeypatch):
    monkeypatch.setattr(api, "get_extrato", lambda numero, **kwargs: {"status": "ok"})

    partes = api.get_partes("1076539-20.2019.8.26.0100")

    assert partes["polo_ativo"] == []


def test_baixar_pecas_usa_movimentacoes_quando_sem_documentos(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(api.esaj, "criar_session", lambda: object())

    def fake_baixar(session, movimentos, destino, limite, sobrescrever):
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

    def fake_consultar(numero, api_key=None, include_raw=False):
        chamadas["numero"] = numero
        chamadas["api_key"] = api_key
        chamadas["include_raw"] = include_raw
        return {"status": "ok"}

    monkeypatch.setattr(api.datajud, "consultar_processo", fake_consultar)

    resultado = api.consultar_datajud("1076539-20.2019.8.26.0100", api_key="abc", include_raw=True)

    assert resultado == {"status": "ok"}
    assert chamadas["api_key"] == "abc"
    assert chamadas["include_raw"] is True


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
    )

    assert resultado["status"] == "ok"
    assert chamadas["sources"] == ("datajud",)
