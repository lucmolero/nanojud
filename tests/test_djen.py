from nanojud import djen
from nanojud.djen import _extrair_items, _normalizar_item, _parse_data
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel


def test_parse_data_iso():
    assert _parse_data({"data_disponibilizacao": "2026-07-30T10:00:00"}) == "2026-07-30"


def test_parse_data_brasileira():
    assert _parse_data({"datadisponibilizacao": "30/07/2026"}) == "2026-07-30"


def test_parse_data_vazia():
    assert _parse_data({}) == ""


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        return self.responses.pop(0)


def test_consultar_processo_pagina_e_deduplica():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "items": [
                        {"id": "1", "texto": "um", "data_disponibilizacao": "2026-07-30"},
                        {"id": "1", "texto": "duplicado", "data_disponibilizacao": "2026-07-30"},
                    ]
                },
            )
        ]
    )

    resultado = djen.consultar_processo(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=20,
        sleep=lambda _: None,
    )

    assert len(resultado) == 1
    assert resultado[0]["texto"] == "um"


def test_consultar_processo_retries_429():
    session = FakeSession(
        [
            FakeResponse(429, {}),
            FakeResponse(200, [{"id": "2", "texto": "ok", "datadisponibilizacao": "30/07/2026"}]),
        ]
    )

    resultado = djen.consultar_processo(
        "1076539-20.2019.8.26.0100",
        session=session,
        retry=2,
        sleep=lambda _: None,
    )

    assert len(resultado) == 1
    assert len(session.calls) == 2


def test_consultar_processo_403_vira_acesso_restrito():
    session = FakeSession([FakeResponse(403, {})])

    try:
        djen.consultar_processo("1076539-20.2019.8.26.0100", session=session)
    except AcessoRestrito:
        pass
    else:
        raise AssertionError("403 deveria gerar AcessoRestrito")


def test_extrair_items_aceita_formatos_conhecidos():
    assert _extrair_items([{"id": "1"}, "ignorar"]) == [{"id": "1"}]
    assert _extrair_items({"content": [{"id": "2"}]}) == [{"id": "2"}]
    assert _extrair_items({"resultado": ["ignorar"]}) == []
    assert _extrair_items({"outro": []}) == []


def test_normalizar_item_usa_fallbacks():
    item = _normalizar_item(
        {
            "id": 123,
            "tipoDocumento": "Intimação",
            "datadisponibilizacao": "30/07/2026",
            "texto": 456,
        }
    )

    assert item["id"] == 123
    assert item["tipoComunicacao"] == "Intimação"
    assert item["dataDisponibilizacao"] == "2026-07-30"
    assert item["texto"] == "456"


def test_consultar_processo_pagina_ate_max_pages():
    session = FakeSession(
        [
            FakeResponse(200, {"items": [{"id": "1"}, {"id": "2"}]}),
            FakeResponse(200, {"items": [{"id": "3"}]}),
        ]
    )

    resultado = djen.consultar_processo(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=2,
        max_pages=2,
        sleep=lambda _: None,
    )

    assert [item["id"] for item in resultado] == ["1", "2", "3"]


def test_consultar_processo_http_500_vira_consulta_indisponivel():
    session = FakeSession([FakeResponse(500, {})])

    try:
        djen.consultar_processo("1076539-20.2019.8.26.0100", session=session)
    except ConsultaIndisponivel as exc:
        assert "500" in str(exc)
    else:
        raise AssertionError("HTTP 500 deveria gerar ConsultaIndisponivel")


def test_consultar_processo_json_invalido():
    session = FakeSession([FakeResponse(200, ValueError("json"))])

    try:
        djen.consultar_processo("1076539-20.2019.8.26.0100", session=session)
    except ConsultaIndisponivel as exc:
        assert "JSON" in str(exc)
    else:
        raise AssertionError("JSON inválido deveria gerar ConsultaIndisponivel")


def test_consultar_processo_falha_requests_apos_retry():
    class SessionComErro:
        def get(self, url, params=None, timeout=None):
            raise djen.requests.RequestException("rede fora")

    try:
        djen.consultar_processo(
            "1076539-20.2019.8.26.0100",
            session=SessionComErro(),
            retry=1,
            sleep=lambda _: None,
        )
    except ConsultaIndisponivel as exc:
        assert "rede fora" in str(exc)
    else:
        raise AssertionError("Falha requests deveria gerar ConsultaIndisponivel")


def test_normalizar_item_preserva_numero_incidente_e_cancelamento():
    item = _normalizar_item(
        {
            "id": 1,
            "numero_processo": "00150202320108260053",
            "numeroprocessocommascara": "0015020-23.2010.8.26.0053",
            "texto": "Processo 0015020-23.2010.8.26.0053/47 - Requisição de Pequeno Valor - ADV: X",
            "numeroComunicacao": 9,
            "hash": "abc",
            "status": "P",
            "ativo": False,
            "motivo_cancelamento": "Erro",
            "destinatarioadvogados": [{"advogado": {"nome": "X"}}],
        }
    )

    assert item["numero_processo"] == "0015020-23.2010.8.26.0053"
    assert item["incidente"] == "47"
    assert item["ativo"] is False
    assert item["motivo_cancelamento"] == "Erro"
    assert item["advogados"] == [{"advogado": {"nome": "X"}}]
    assert item["hash"] == "abc"


def test_comunicacao_do_processo_principal_nao_tem_incidente():
    item = _normalizar_item({"texto": "Processo 0015020-23.2010.8.26.0053 (053.10.015020-1) - X"})

    assert item["incidente"] == ""
