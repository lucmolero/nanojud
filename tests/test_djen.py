from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from nanojud import djen
from nanojud.djen import _extrair_items, _normalizar_item, _parse_data
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel

CNJ_CONSULTADO = "1076539-20.2019.8.26.0100"
CNJ_DIVERGENTE = "0015020-23.2010.8.26.0053"


def test_parse_data_iso():
    assert _parse_data({"data_disponibilizacao": "2026-07-30T10:00:00"}) == "2026-07-30"


def test_parse_data_brasileira():
    assert _parse_data({"datadisponibilizacao": "30/07/2026"}) == "2026-07-30"


def test_parse_data_vazia():
    assert _parse_data({}) == ""


def test_parse_data_brasileira_com_formato_incompleto_fica_vazia():
    assert _parse_data({"datadisponibilizacao": "30/07"}) == ""


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


def _comunicacao(codigo, **campos):
    return {
        "id": codigo,
        "numeroprocessocommascara": CNJ_CONSULTADO,
        **campos,
    }


def test_consultar_processo_pagina_e_deduplica():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "items": [
                        _comunicacao("1", texto="um", data_disponibilizacao="2026-07-30"),
                        _comunicacao("1", texto="duplicado", data_disponibilizacao="2026-07-30"),
                    ]
                },
            )
        ]
    )

    resultado = djen.consultar_processo(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=100,
        sleep=lambda _: None,
    )

    assert len(resultado) == 1
    assert resultado[0]["texto"] == "um"


def test_consultar_processo_retries_429():
    session = FakeSession(
        [
            FakeResponse(429, {}),
            FakeResponse(
                200,
                [_comunicacao("2", texto="ok", datadisponibilizacao="30/07/2026")],
            ),
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
    assert _extrair_items([{"id": "1"}]) == [{"id": "1"}]
    assert _extrair_items({"content": [{"id": "2"}]}) == [{"id": "2"}]
    assert _extrair_items({"resultado": []}) == []


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
    assert item["fonte"] == "djen"


def test_consultar_processo_pagina_ate_max_pages():
    session = FakeSession(
        [
            FakeResponse(200, {"items": [_comunicacao(str(i)) for i in range(1, 6)]}),
            FakeResponse(200, {"items": [_comunicacao("6")]}),
        ]
    )

    resultado = djen.consultar_processo(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=5,
        max_pages=2,
        sleep=lambda _: None,
    )

    assert [item["id"] for item in resultado] == ["1", "2", "3", "4", "5", "6"]


def test_consultar_processo_detalhado_marca_completude_ao_atingir_limite():
    session = FakeSession(
        [FakeResponse(200, {"items": [_comunicacao(str(i)) for i in range(1, 6)]})]
    )

    resultado = djen.consultar_processo_detalhado(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=5,
        max_pages=1,
        sleep=lambda _: None,
    )

    assert resultado["status"] == "partial"
    assert resultado["completo"] is False
    assert resultado["paginas"] == 1
    assert [item["id"] for item in resultado["comunicacoes"]] == ["1", "2", "3", "4", "5"]
    assert "limite de 1 páginas" in resultado["avisos"][0]


def test_consultar_processo_detalhado_marca_vazio_como_completo():
    session = FakeSession([FakeResponse(200, {"items": []})])

    resultado = djen.consultar_processo_detalhado(
        "1076539-20.2019.8.26.0100", session=session, sleep=lambda _: None
    )

    assert resultado == {
        "status": "ok",
        "completo": True,
        "paginas": 1,
        "comunicacoes": [],
        "avisos": [],
    }


def test_consultar_processo_detalhado_respeita_retry_after():
    class RateLimitResponse(FakeResponse):
        headers = {"Retry-After": "7"}

    session = FakeSession(
        [
            RateLimitResponse(429, {}),
            FakeResponse(200, {"items": [_comunicacao("1")]}),
        ]
    )
    esperas = []

    djen.consultar_processo_detalhado(
        "1076539-20.2019.8.26.0100",
        session=session,
        retry=2,
        backoff=0.1,
        sleep=esperas.append,
    )

    assert esperas == [7]


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
            raise djen.requests.RequestException(
                "rede fora at https://djen.test/?numeroProcesso=private"
            )

    try:
        djen.consultar_processo(
            "1076539-20.2019.8.26.0100",
            session=SessionComErro(),
            retry=1,
            sleep=lambda _: None,
        )
    except ConsultaIndisponivel as exc:
        assert "RequestException" in str(exc)
        assert "numeroProcesso=private" not in str(exc)
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


def test_normalizar_item_nao_assume_comunicacao_ativa_quando_fonte_omite_flag():
    item = _normalizar_item({"numero_processo": CNJ_CONSULTADO})

    assert item["ativo"] is None
    assert item["data_cancelamento"] == ""
    assert item["motivo_cancelamento"] == ""


def test_identidade_rejeita_cnj_com_digito_verificador_invalido():
    assert djen._identidade_item({"numero_processo": "1076539-21.2019.8.26.0100"}) == ""


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, None), ("texto inválido", None), ("-2", None), ("Wed, 21 Oct 2015 07:28:00", 0.0)],
)
def test_retry_after_aceita_ou_rejeita_valores_sem_fuso_com_seguranca(valor, esperado):
    class Response:
        headers = {} if valor is None else {"Retry-After": valor}

    assert djen._retry_after_seconds(Response()) == esperado


def test_retry_after_interpreta_data_http_futura():
    class Response:
        headers = {
            "Retry-After": format_datetime(datetime.now(UTC) + timedelta(seconds=300), usegmt=True)
        }

    espera = djen._retry_after_seconds(Response())
    assert espera is not None
    assert 290 <= espera <= 300


def test_comunicacao_do_processo_principal_nao_tem_incidente():
    item = _normalizar_item({"texto": "Processo 0015020-23.2010.8.26.0053 (053.10.015020-1) - X"})

    assert item["incidente"] == ""


@pytest.mark.parametrize("body", [{}, {"items": None}, {"items": ["inválido"]}, None])
def test_consultar_processo_rejeita_estrutura_invalida(body):
    session = FakeSession([FakeResponse(200, body)])
    with pytest.raises(ConsultaIndisponivel, match="estrutura"):
        djen.consultar_processo("1076539-20.2019.8.26.0100", session=session)


@pytest.mark.parametrize("parametro", ["page_size", "max_pages", "retry"])
@pytest.mark.parametrize("valor", [0, -1, False, 1.5])
def test_consultar_processo_rejeita_limite_invalido_sem_rede(parametro, valor):
    session = FakeSession([])
    with pytest.raises(ValueError, match=parametro):
        djen.consultar_processo("1076539-20.2019.8.26.0100", session=session, **{parametro: valor})
    assert session.calls == []


def test_detalhado_preserva_pagina_apos_falha_tardia():
    session = FakeSession(
        [
            FakeResponse(200, {"items": [_comunicacao(str(i)) for i in range(1, 6)]}),
            FakeResponse(500, {}),
        ]
    )
    resultado = djen.consultar_processo_detalhado(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=5,
        retry=1,
        sleep=lambda _: None,
    )

    assert resultado["status"] == "partial"
    assert resultado["completo"] is False
    assert resultado["paginas"] == 1
    assert [item["id"] for item in resultado["comunicacoes"]] == ["1", "2", "3", "4", "5"]
    assert "HTTP 500" in resultado["avisos"][0]


def test_detalhado_rejeita_comunicacao_de_outro_processo_e_marca_parcial():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "items": [
                        {
                            "id": "correta",
                            "numeroprocessocommascara": CNJ_CONSULTADO,
                        },
                        {
                            "id": "divergente",
                            "numeroprocessocommascara": CNJ_DIVERGENTE,
                        },
                    ]
                },
            )
        ]
    )

    resultado = djen.consultar_processo_detalhado(CNJ_CONSULTADO, session=session)

    assert resultado["status"] == "partial"
    assert resultado["completo"] is False
    assert [item["id"] for item in resultado["comunicacoes"]] == ["correta"]
    assert any("identidade" in aviso.lower() for aviso in resultado["avisos"])


def test_detalhado_rejeita_comunicacao_sem_numero_confirmavel():
    session = FakeSession([FakeResponse(200, {"items": [{"id": "sem-cnj"}]})])

    resultado = djen.consultar_processo_detalhado(CNJ_CONSULTADO, session=session)

    assert resultado["status"] == "partial"
    assert resultado["completo"] is False
    assert resultado["comunicacoes"] == []
    assert any("identidade" in aviso.lower() for aviso in resultado["avisos"])


def test_identidade_djen_aceita_numero_sem_mascara_e_sufixo_de_incidente():
    item = {
        "numeroprocessocommascara": "10765392020198260100/47",
    }

    assert djen._identidade_item(item) == djen.validar_numero_cnj(
        CNJ_CONSULTADO, segmento=None, tribunal=None
    )


def test_detalhado_respeita_orcamento_total_entre_paginas():
    session = FakeSession(
        [FakeResponse(200, {"items": [_comunicacao(str(i)) for i in range(1, 6)]})]
    )
    instante = [0.0]

    def dormir(segundos):
        instante[0] += segundos

    resultado = djen.consultar_processo_detalhado(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=5,
        total_timeout=0.1,
        monotonic=lambda: instante[0],
        sleep=dormir,
    )

    assert resultado["status"] == "partial"
    assert [item["id"] for item in resultado["comunicacoes"]] == ["1", "2", "3", "4", "5"]
    assert len(session.calls) == 1
    assert any("tempo total" in aviso for aviso in resultado["avisos"])


@pytest.mark.parametrize("segunda", [FakeResponse(200, ValueError("json")), FakeResponse(403, {})])
def test_detalhado_preserva_resultado_apos_resposta_invalida_ou_restrita(segunda):
    session = FakeSession(
        [FakeResponse(200, {"items": [_comunicacao(str(i)) for i in range(1, 6)]}), segunda]
    )
    resultado = djen.consultar_processo_detalhado(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=5,
        retry=1,
        sleep=lambda _: None,
    )

    assert resultado["status"] == "partial"
    assert resultado["comunicacoes"][0]["id"] == "1"
    assert resultado["paginas"] == 1


def test_detalhado_nao_espera_retry_after_acima_do_orcamento():
    class RateLimitResponse(FakeResponse):
        headers = {"Retry-After": "10"}

    session = FakeSession(
        [
            FakeResponse(200, {"items": [_comunicacao(str(i)) for i in range(1, 6)]}),
            RateLimitResponse(429, {}),
        ]
    )
    esperas = []
    resultado = djen.consultar_processo_detalhado(
        "1076539-20.2019.8.26.0100",
        session=session,
        page_size=5,
        retry=2,
        total_timeout=1,
        sleep=esperas.append,
        monotonic=lambda: 0.0,
    )

    assert resultado["status"] == "partial"
    assert len(resultado["comunicacoes"]) == 5
    assert esperas == [0.2]


def test_detalhado_rejeita_retry_after_acima_de_60_segundos_sem_repetir():
    class RateLimitResponse(FakeResponse):
        headers = {"Retry-After": "61"}

    session = FakeSession([RateLimitResponse(429, {})])
    esperas = []

    with pytest.raises(ConsultaIndisponivel, match="mais de 60 segundos"):
        djen.consultar_processo_detalhado(
            CNJ_CONSULTADO, session=session, retry=2, sleep=esperas.append
        )

    assert len(session.calls) == 1
    assert esperas == []


def test_detalhado_preserva_dados_se_a_pausa_entre_paginas_excede_orcamento():
    session = FakeSession([FakeResponse(200, {"items": [_comunicacao(str(i)) for i in range(5)]})])
    instantes = iter((10.0, 10.0, 10.9))

    resultado = djen.consultar_processo_detalhado(
        CNJ_CONSULTADO,
        session=session,
        page_size=5,
        total_timeout=1.0,
        monotonic=lambda: next(instantes),
    )

    assert resultado["status"] == "partial"
    assert resultado["completo"] is False
    assert resultado["paginas"] == 1
    assert len(resultado["comunicacoes"]) == 5
    assert "tempo total" in resultado["avisos"][0]


def test_detalhado_detecta_pagina_repetida_e_nao_duplica_comunicacoes():
    items = [_comunicacao(str(i)) for i in range(5)]
    session = FakeSession(
        [FakeResponse(200, {"items": items}), FakeResponse(200, {"items": items})]
    )

    resultado = djen.consultar_processo_detalhado(
        CNJ_CONSULTADO, session=session, page_size=5, retry=1, sleep=lambda _: None
    )

    assert resultado["status"] == "partial"
    assert resultado["completo"] is False
    assert resultado["paginas"] == 2
    assert [item["id"] for item in resultado["comunicacoes"]] == [str(i) for i in range(5)]
    assert "repetiu uma página" in resultado["avisos"][0]


def test_djen_usa_parametros_oficiais_de_paginacao():
    session = FakeSession([FakeResponse(200, {"items": [_comunicacao("1")]})])

    djen.consultar_processo_detalhado(CNJ_CONSULTADO, session=session, page_size=5)

    assert session.calls[0]["params"]["pagina"] == 1
    assert session.calls[0]["params"]["itensPorPagina"] == 5
    assert "page" not in session.calls[0]["params"]
    assert "size" not in session.calls[0]["params"]


@pytest.mark.parametrize("page_size", [1, 2, 20, 99, 101])
def test_djen_rejeita_tamanho_de_pagina_fora_do_contrato(page_size):
    session = FakeSession([])

    with pytest.raises(ValueError, match="page_size"):
        djen.consultar_processo_detalhado(CNJ_CONSULTADO, session=session, page_size=page_size)

    assert session.calls == []
