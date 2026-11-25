from copy import deepcopy
from datetime import UTC, datetime
from email.utils import format_datetime

import pytest
import requests

from nanojud import datajud
from nanojud.datajud import resumo_do_datajud
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel


class FakeResponse:
    def __init__(self, status_code, payload, *, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response, *, exc=None):
        self.responses = list(response) if isinstance(response, list) else [response]
        self.exc = exc
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        if self.exc:
            raise self.exc
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


def _payload():
    return {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_source": {
                        "numeroProcesso": "10765392020198260100",
                        "tribunal": "TJSP",
                        "grau": "G1",
                        "classe": {"nome": "Procedimento Comum Civel"},
                        "orgaoJulgador": {"nome": "1 Vara Civel"},
                        "assuntos": [{"nome": "Contratos"}],
                        "movimentos": [
                            {
                                "codigo": 26,
                                "nome": "Distribuicao",
                                "dataHora": "2019-08-20T10:00:00",
                                "complementosTabelados": [{"nome": "Livre"}],
                            }
                        ],
                        "partes": [
                            {
                                "nome": "Parte Exemplo",
                                "tipoParte": "AUTOR",
                                "polo": "ATIVO",
                                "advogados": [{"nome": "Advogada Exemplo", "numeroOAB": "123"}],
                            }
                        ],
                    }
                }
            ],
        }
    }


def test_resumo_do_datajud_preserva_grau_data_e_completude():
    resumo = resumo_do_datajud(
        {
            "status": "partial",
            "numero_cnj": "1076539-20.2019.8.26.0100",
            "tribunal": "TJSP",
            "grau": "G1",
            "classe": "Procedimento Comum",
            "movimentos": [
                {"nome": "Movimento de segundo grau", "data": "2026-11-13", "grau": "G2"}
            ],
            "metadata": {
                "source": "datajud",
                "source_url": "https://api-publica.datajud.cnj.jus.br/",
                "extracted_at": "2026-11-13T21:00:00+00:00",
                "records_complete": False,
            },
        }
    )

    assert resumo["fonte"] == "datajud"
    assert resumo["grau"] == "G2"
    assert resumo["data_coleta"] == "2026-11-13T21:00:00+00:00"
    assert resumo["coleta_completa"] is False


def test_indice_datajud_tjsp():
    assert datajud.indice_datajud("1076539-20.2019.8.26.0100") == "tjsp"


def test_indice_datajud_outros_segmentos(monkeypatch):
    monkeypatch.setattr(datajud, "validar_numero_cnj", lambda numero, **kwargs: numero)

    assert datajud.indice_datajud("0000001-02.2020.4.01.0000") == "trf1"
    assert datajud.indice_datajud("0000001-02.2020.5.02.0000") == "trt2"
    assert datajud.indice_datajud("0000001-02.2020.2.00.0000") == ""
    assert datajud.indice_datajud("0000001-02.2020.3.00.0000") == "stj"
    assert datajud.indice_datajud("0000001-02.2020.5.00.0000") == "tst"
    assert datajud.indice_datajud("0000001-02.2020.6.00.0000") == "tse"
    assert datajud.indice_datajud("0000001-02.2020.6.26.0000") == "tre-sp"
    assert datajud.indice_datajud("0000001-02.2020.6.07.0000") == "tre-dft"
    assert datajud.indice_datajud("0000001-02.2020.7.00.0000") == "stm"
    assert datajud.indice_datajud("0000001-02.2020.9.13.0000") == "tjmmg"
    assert datajud.indice_datajud("0000001-02.2020.9.21.0000") == "tjmrs"
    assert datajud.indice_datajud("0000001-02.2020.9.26.0000") == "tjmsp"
    assert datajud.indice_datajud("0000001-02.2020.9.01.0000") == ""


def test_indice_datajud_cobre_aliases_oficiais_por_segmento(monkeypatch):
    monkeypatch.setattr(datajud, "validar_numero_cnj", lambda numero, **kwargs: numero)

    for tribunal, alias in datajud.INDICES_JUSTICA_ESTADUAL.items():
        assert datajud.indice_datajud(f"0000001-02.2020.8.{tribunal}.0000") == alias
        assert datajud.indice_datajud(f"0000001-02.2020.6.{tribunal}.0000") == (
            f"tre-{alias.removeprefix('tj')}"
        )
    for tribunal, alias in datajud.INDICES_JUSTICA_MILITAR_ESTADUAL.items():
        assert datajud.indice_datajud(f"0000001-02.2020.9.{tribunal}.0000") == alias
    for regiao in range(1, 7):
        assert datajud.indice_datajud(f"0000001-02.2020.4.{regiao:02d}.0000") == f"trf{regiao}"
    for regiao in range(1, 25):
        assert datajud.indice_datajud(f"0000001-02.2020.5.{regiao:02d}.0000") == f"trt{regiao}"


def test_api_key_usa_chave_publica_oficial(monkeypatch):
    monkeypatch.delenv("NANOJUD_DATAJUD_API_KEY", raising=False)
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    monkeypatch.delenv("CNJ_DATAJUD_API_KEY", raising=False)

    assert datajud.datajud_api_key() == f"APIKey {datajud.PUBLIC_DATAJUD_API_KEY}"


def test_api_key_usa_env(monkeypatch):
    monkeypatch.setenv("NANOJUD_DATAJUD_API_KEY", "xyz")

    assert datajud.datajud_api_key() == "APIKey xyz"


def test_consultar_processo_normaliza_payload():
    session = FakeSession(FakeResponse(200, _payload()))

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        api_key="abc",
        session=session,
        sleep=lambda _: None,
    )

    assert session.calls[0]["url"].endswith("api_publica_tjsp/_search")
    assert session.calls[0]["kwargs"]["headers"]["Authorization"] == "APIKey abc"
    assert resultado["status"] == "ok"
    assert resultado["classe"] == "Procedimento Comum Civel"
    assert resultado["movimentos"][0]["data"] == "2019-08-20"
    assert resultado["partes"][0]["advogados"][0]["oab"] == "123"


def test_consultar_processo_rejeita_cnj_divergente_retornado_pelo_datajud():
    corpo = _payload()
    corpo["hits"]["hits"][0]["_source"]["numeroProcesso"] = "00150202320108260053"
    session = FakeSession(FakeResponse(200, corpo))

    with pytest.raises(ConsultaIndisponivel, match="CNJ divergente"):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)


def test_consultar_processo_rejeita_tribunal_divergente_do_cnj():
    corpo = _payload()
    corpo["hits"]["hits"][0]["_source"]["tribunal"] = "TJMG"
    session = FakeSession(FakeResponse(200, corpo))

    with pytest.raises(ConsultaIndisponivel, match="tribunal divergente"):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)


def test_consultar_processo_rejeita_hit_sem_tribunal():
    corpo = _payload()
    corpo["hits"]["hits"][0]["_source"].pop("tribunal")
    session = FakeSession(FakeResponse(200, corpo))

    with pytest.raises(ConsultaIndisponivel, match="sem tribunal"):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)


@pytest.mark.parametrize("timeout", [None, 0, float("nan"), float("inf"), 86401])
def test_consultar_processo_rejeita_timeout_invalido_antes_do_request(timeout):
    class SessionSemRede:
        def post(self, *args, **kwargs):
            pytest.fail("Timeout inválido não pode chegar ao transporte HTTP")

    with pytest.raises(ValueError, match="timeout"):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100", session=SessionSemRede(), timeout=timeout
        )


@pytest.mark.parametrize("prazo_total", [True, -1, float("nan"), float("inf"), 86401])
def test_consultar_processo_rejeita_prazo_total_invalido_antes_do_request(prazo_total):
    class SessionSemRede:
        def post(self, *args, **kwargs):
            pytest.fail("Prazo total inválido não pode chegar ao transporte HTTP")

    with pytest.raises(ValueError, match="prazo_total"):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100",
            session=SessionSemRede(),
            prazo_total=prazo_total,
        )


@pytest.mark.parametrize("backoff", [None, True, -0.1, float("nan"), float("inf"), "1"])
def test_consultar_processo_rejeita_backoff_invalido_antes_do_request(backoff):
    class SessionSemRede:
        def post(self, *args, **kwargs):
            pytest.fail("Backoff inválido não pode chegar ao transporte HTTP")

    with pytest.raises(ValueError, match="backoff"):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100", session=SessionSemRede(), backoff=backoff
        )


def test_consultar_processo_nao_encontrado():
    session = FakeSession(
        FakeResponse(200, {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}})
    )

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        api_key="APIKey abc",
        session=session,
        include_raw=True,
        sleep=lambda _: None,
    )

    assert resultado["status"] == "nao_encontrado"
    assert resultado["raw"] == {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}


def test_consultar_processo_nao_chama_zero_hits_sem_total_de_nao_encontrado():
    session = FakeSession(FakeResponse(200, {"hits": {"hits": []}}))

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)

    assert resultado["status"] == "partial"
    assert resultado["metadata"]["records_complete"] is False
    assert resultado["warnings"]


def test_consultar_processo_aceita_total_inteiro_legado():
    corpo = _payload()
    corpo["hits"]["total"] = 1
    session = FakeSession(FakeResponse(200, corpo))

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)

    assert resultado["status"] == "ok"
    assert resultado["metadata"]["records_complete"] is True
    assert resultado["metadata"]["total_relation"] == "eq"


def test_consultar_processo_retry_429():
    session = FakeSession([FakeResponse(429, {}), FakeResponse(200, _payload())])
    sleeps = []

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        api_key="abc",
        session=session,
        sleep=lambda segundos: sleeps.append(segundos),
    )

    assert resultado["status"] == "ok"
    assert sleeps == [1.0]
    assert len(session.calls) == 2


def test_consultar_processo_obedece_retry_after_em_segundos():
    session = FakeSession(
        [
            FakeResponse(429, {}, headers={"Retry-After": "7"}),
            FakeResponse(200, _payload()),
        ]
    )
    sleeps = []

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        api_key="abc",
        session=session,
        sleep=sleeps.append,
    )

    assert resultado["status"] == "ok"
    assert sleeps == [7.0]
    assert len(session.calls) == 2


def test_consultar_processo_nao_espera_retry_after_que_excede_prazo_total():
    session = FakeSession(FakeResponse(429, {}, headers={"Retry-After": "7"}))
    sleeps = []

    with pytest.raises(ConsultaIndisponivel, match="prazo total"):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100",
            session=session,
            retry=3,
            prazo_total=5,
            sleep=sleeps.append,
        )

    assert not sleeps
    assert len(session.calls) == 1


def test_retry_after_aceita_data_http_e_rejeita_data_passada():
    agora = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
    futura = datetime(2026, 11, 12, 12, 0, 5, tzinfo=UTC)
    passada = datetime(2026, 11, 12, 11, 59, 55, tzinfo=UTC)
    response_futura = FakeResponse(
        503,
        {},
        headers={"Retry-After": format_datetime(futura, usegmt=True)},
    )
    response_passada = FakeResponse(
        503,
        {},
        headers={"Retry-After": format_datetime(passada, usegmt=True)},
    )

    assert datajud._retry_after_seconds(response_futura, now=agora) == 5.0
    assert datajud._retry_after_seconds(response_passada, now=agora) == 0.0


@pytest.mark.parametrize("valor", ["-3", "not an HTTP date"])
def test_retry_after_invalido_usa_backoff_padrao(valor):
    response = FakeResponse(429, {}, headers={"Retry-After": valor})

    assert datajud._retry_after_seconds(response) is None


def test_retry_after_data_sem_fuso_e_now_sem_fuso_sao_tratados_como_utc(monkeypatch):
    response = FakeResponse(503, {}, headers={"Retry-After": "Wed, 12 Nov 2026 12:00:05 GMT"})
    monkeypatch.setattr(
        datajud,
        "parsedate_to_datetime",
        lambda _: datetime(2026, 11, 12, 12, 0, 5),
    )
    agora = datetime(2026, 11, 12, 12, 0)

    assert datajud._retry_after_seconds(response, now=agora) == 5.0


def test_consultar_processo_nao_repete_antes_de_retry_after_alto():
    session = FakeSession([FakeResponse(429, {}, headers={"Retry-After": "120"})])
    sleeps = []

    with pytest.raises(ConsultaIndisponivel, match="Retry-After"):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100",
            api_key="abc",
            session=session,
            retry=3,
            sleep=sleeps.append,
        )

    assert sleeps == []
    assert len(session.calls) == 1


def test_consultar_processo_retry_503_e_recupera():
    session = FakeSession([FakeResponse(503, {}), FakeResponse(200, _payload())])
    sleeps = []

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        api_key="abc",
        session=session,
        retry=2,
        sleep=lambda segundos: sleeps.append(segundos),
    )

    assert resultado["status"] == "ok"
    assert sleeps == [1.0]
    assert len(session.calls) == 2


def test_consultar_processo_erro_5xx_esgota_tentativas_com_backoff():
    session = FakeSession(FakeResponse(500, {}))
    sleeps = []

    with pytest.raises(ConsultaIndisponivel, match="HTTP 500"):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100",
            api_key="abc",
            session=session,
            retry=3,
            sleep=lambda segundos: sleeps.append(segundos),
        )

    assert sleeps == [1.0, 2.0]
    assert len(session.calls) == 3


def test_consultar_processo_aplica_prazo_total_a_tentativas_e_backoff(monkeypatch):
    agora = [0.0]

    class SessionComTempo(FakeSession):
        def post(self, url, **kwargs):
            self.calls.append({"url": url, "kwargs": kwargs})
            agora[0] += 4.0
            raise requests.Timeout("tempo esgotado")

    monkeypatch.setattr(datajud.time, "monotonic", lambda: agora[0])
    session = SessionComTempo([])
    sleeps = []

    def dormir(segundos):
        sleeps.append(segundos)
        agora[0] += segundos

    with pytest.raises(ConsultaIndisponivel, match="prazo total"):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100",
            session=session,
            timeout=8,
            retry=3,
            backoff=2,
            sleep=dormir,
            prazo_total=10,
        )

    assert [call["kwargs"]["timeout"] for call in session.calls] == [8, 4]
    assert sleeps == [2]
    assert agora[0] == 10


def test_consultar_processo_prazo_total_zero_nao_acessa_rede():
    session = FakeSession(FakeResponse(200, _payload()))

    with pytest.raises(ConsultaIndisponivel, match="prazo total"):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, prazo_total=0)

    assert not session.calls


def test_consultar_processo_http_403():
    session = FakeSession(FakeResponse(403, {}))

    with pytest.raises(AcessoRestrito):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", api_key="abc", session=session)


def test_consultar_processo_http_500():
    session = FakeSession(FakeResponse(500, {}))

    with pytest.raises(ConsultaIndisponivel):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100", api_key="abc", session=session, retry=1
        )


def test_consultar_processo_json_invalido():
    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("bad json")

    session = FakeSession(BadJsonResponse(200, {}))

    with pytest.raises(ConsultaIndisponivel):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", api_key="abc", session=session)


def test_consultar_processo_erro_rede():
    session = FakeSession(
        FakeResponse(200, {}),
        exc=requests.RequestException("offline at https://datajud.test/?api_key=private"),
    )

    with pytest.raises(ConsultaIndisponivel) as erro:
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100",
            api_key="abc",
            session=session,
            retry=1,
        )
    assert "RequestException" in str(erro.value)
    assert "api_key=private" not in str(erro.value)


def _hit(grau, classe, movimentos, ajuizamento="2020-01-01T00:00:00.000Z"):
    return {
        "_source": {
            "numeroProcesso": "10765392020198260100",
            "tribunal": "TJSP",
            "grau": grau,
            "classe": {"nome": classe},
            "orgaoJulgador": {"nome": f"Orgao {grau}"},
            "dataAjuizamento": ajuizamento,
            "movimentos": movimentos,
        }
    }


def test_consolida_todos_os_graus_priorizando_o_primeiro_grau():
    # o DataJud devolve G2 antes de G1; a ordem de chegada nao pode definir o processo
    corpo = {
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "hits": [
                _hit(
                    "G2",
                    "Apelacao Civel",
                    [{"codigo": 1, "nome": "Recurso", "dataHora": "2023-03-01T10:00:00.000Z"}],
                ),
                _hit(
                    "G1",
                    "Usucapiao",
                    [
                        {
                            "codigo": 2,
                            "nome": "Distribuicao",
                            "dataHora": "2012-09-10T10:00:00.000Z",
                        },
                        {"codigo": 3, "nome": "Sentenca", "dataHora": "2022-01-01T10:00:00.000Z"},
                    ],
                ),
            ],
        }
    }
    session = FakeSession(FakeResponse(200, corpo))

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session)

    assert session.calls[0]["kwargs"]["json"]["size"] == datajud.MAX_REGISTROS
    assert resultado["grau"] == "G1"
    assert resultado["classe"] == "Usucapiao"
    assert [g["grau"] for g in resultado["graus"]] == ["G1", "G2"]
    assert [g["total_movimentos"] for g in resultado["graus"]] == [2, 1]
    assert [m["grau"] for m in resultado["movimentos"]] == ["G1", "G1", "G2"]
    datas = [m["data_hora"] for m in resultado["movimentos"]]
    assert datas == sorted(datas)


def test_consultar_processo_marca_parcial_quando_total_excede_teto():
    corpo = _payload()
    hit = corpo["hits"]["hits"][0]
    corpo["hits"]["hits"] = [hit for _ in range(datajud.MAX_REGISTROS)]
    corpo["hits"]["total"] = {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"}
    session = FakeSession(FakeResponse(200, corpo))

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)

    assert resultado["status"] == "partial"
    assert resultado["metadata"]["records_complete"] is False
    assert resultado["metadata"]["total_hits"] == datajud.MAX_REGISTROS + 1
    assert resultado["metadata"]["records_returned"] == datajud.MAX_REGISTROS


def test_consultar_processo_pagina_todos_os_registros_com_cursor_search_after():
    primeiro = _payload()
    hit_modelo = primeiro["hits"]["hits"][0]
    primeiro["hits"]["hits"] = []
    for ordem in range(datajud.MAX_REGISTROS):
        hit = deepcopy(hit_modelo)
        hit["_id"] = f"registro-{ordem}"
        hit["sort"] = [ordem]
        primeiro["hits"]["hits"].append(hit)
    primeiro["hits"]["total"] = {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"}

    segundo = {
        "hits": {
            "total": {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"},
            "hits": [
                {
                    **deepcopy(hit_modelo),
                    "_id": f"registro-{datajud.MAX_REGISTROS}",
                    "sort": [datajud.MAX_REGISTROS],
                }
            ],
        }
    }
    session = FakeSession([FakeResponse(200, primeiro), FakeResponse(200, segundo)])

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        session=session,
        include_raw=True,
        retry=1,
    )

    assert resultado["status"] == "ok"
    assert resultado["metadata"]["records_complete"] is True
    assert resultado["metadata"]["records_returned"] == datajud.MAX_REGISTROS + 1
    assert resultado["metadata"]["records_pages"] == 2
    assert len(resultado["raw"]["hits"]["hits"]) == datajud.MAX_REGISTROS + 1
    payloads = [chamada["kwargs"]["json"] for chamada in session.calls]
    assert payloads[0]["sort"] == [{"@timestamp": {"order": "asc"}}]
    assert payloads[1]["search_after"] == [datajud.MAX_REGISTROS - 1]


def test_consultar_processo_compartilha_prazo_total_entre_paginas(monkeypatch):
    agora = [0.0]
    primeiro = _payload()
    hit_modelo = primeiro["hits"]["hits"][0]
    primeiro["hits"]["hits"] = []
    for ordem in range(datajud.MAX_REGISTROS):
        hit = deepcopy(hit_modelo)
        hit["_id"] = f"registro-{ordem}"
        hit["sort"] = [ordem]
        primeiro["hits"]["hits"].append(hit)
    primeiro["hits"]["total"] = {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"}
    segundo = {
        "hits": {
            "total": {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"},
            "hits": [
                {
                    **deepcopy(hit_modelo),
                    "_id": f"registro-{datajud.MAX_REGISTROS}",
                    "sort": [datajud.MAX_REGISTROS],
                }
            ],
        }
    }

    class SessionComLatencia(FakeSession):
        def post(self, url, **kwargs):
            response = super().post(url, **kwargs)
            if len(self.calls) == 1:
                agora[0] += 3.0
            return response

    monkeypatch.setattr(datajud.time, "monotonic", lambda: agora[0])
    session = SessionComLatencia([FakeResponse(200, primeiro), FakeResponse(200, segundo)])

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100", session=session, retry=1, prazo_total=5
    )

    assert resultado["status"] == "ok"
    assert [call["kwargs"]["timeout"] for call in session.calls] == [5, 2]


def test_consultar_processo_preserva_primeira_pagina_quando_paginacao_falha():
    primeiro = _payload()
    hit_modelo = primeiro["hits"]["hits"][0]
    primeiro["hits"]["hits"] = [
        {
            **deepcopy(hit_modelo),
            "_id": f"registro-{ordem}",
            "sort": [ordem],
        }
        for ordem in range(datajud.MAX_REGISTROS)
    ]
    primeiro["hits"]["total"] = {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"}
    session = FakeSession([FakeResponse(200, primeiro), FakeResponse(503, {})])

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        session=session,
        retry=1,
    )

    assert resultado["status"] == "partial"
    assert resultado["metadata"]["records_complete"] is False
    assert resultado["metadata"]["records_returned"] == datajud.MAX_REGISTROS
    assert resultado["metadata"]["records_pages"] == 1
    assert any("não concluiu a paginação" in aviso for aviso in resultado["warnings"])


def test_consultar_processo_retorna_parcial_se_cursor_nao_for_informado():
    corpo = _payload()
    hit_modelo = corpo["hits"]["hits"][0]
    corpo["hits"]["hits"] = [
        {**deepcopy(hit_modelo), "_id": f"registro-{ordem}"}
        for ordem in range(datajud.MAX_REGISTROS)
    ]
    corpo["hits"]["total"] = {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"}
    session = FakeSession(FakeResponse(200, corpo))

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)

    assert resultado["status"] == "partial"
    assert resultado["metadata"]["records_complete"] is False
    assert resultado["metadata"]["records_pages"] == 1
    assert any("cursor válido" in aviso for aviso in resultado["warnings"])


def test_consultar_processo_respeita_limite_de_paginas(monkeypatch):
    monkeypatch.setattr(datajud, "MAX_PAGINAS", 1)
    corpo = _payload()
    hit_modelo = corpo["hits"]["hits"][0]
    corpo["hits"]["hits"] = [
        {**deepcopy(hit_modelo), "_id": f"registro-{ordem}", "sort": [ordem]}
        for ordem in range(datajud.MAX_REGISTROS)
    ]
    corpo["hits"]["total"] = {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"}
    session = FakeSession(FakeResponse(200, corpo))

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)

    assert resultado["status"] == "partial"
    assert resultado["metadata"]["records_complete"] is False
    assert resultado["metadata"]["records_returned"] == datajud.MAX_REGISTROS
    assert resultado["metadata"]["records_pages"] == 1
    assert len(session.calls) == 1
    assert any("limite de 1 páginas" in aviso for aviso in resultado["warnings"])


def test_consultar_processo_nao_declara_completo_com_id_repetido_entre_paginas():
    primeiro = _payload()
    hit_modelo = primeiro["hits"]["hits"][0]
    primeiro["hits"]["hits"] = [
        {
            **deepcopy(hit_modelo),
            "_id": f"registro-{ordem}",
            "sort": [ordem],
        }
        for ordem in range(datajud.MAX_REGISTROS)
    ]
    primeiro["hits"]["total"] = {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"}
    duplicado = {
        "hits": {
            "total": {"value": datajud.MAX_REGISTROS + 1, "relation": "eq"},
            "hits": [
                {
                    **deepcopy(hit_modelo),
                    "_id": f"registro-{datajud.MAX_REGISTROS - 1}",
                    "sort": [datajud.MAX_REGISTROS],
                }
            ],
        }
    }
    session = FakeSession([FakeResponse(200, primeiro), FakeResponse(200, duplicado)])

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)

    assert resultado["status"] == "partial"
    assert resultado["metadata"]["records_complete"] is False
    assert resultado["metadata"]["records_returned"] == datajud.MAX_REGISTROS
    assert any("repetiu ou omitiu identificadores" in aviso for aviso in resultado["warnings"])


def test_consultar_processo_marca_parcial_quando_total_e_apenas_limite_inferior():
    corpo = _payload()
    corpo["hits"]["total"] = {"value": 1, "relation": "gte"}
    session = FakeSession(FakeResponse(200, corpo))

    resultado = datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session, retry=1)

    assert resultado["status"] == "partial"
    assert resultado["metadata"]["records_complete"] is False
    assert resultado["metadata"]["total_relation"] == "gte"


@pytest.mark.parametrize(
    "body", [{}, None, {"hits": []}, {"hits": {"hits": [None]}}, {"hits": {"hits": [{}]}}]
)
def test_consultar_processo_rejeita_estrutura_invalida(body):
    session = FakeSession(FakeResponse(200, body))
    with pytest.raises(ConsultaIndisponivel, match="estrutura"):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", session=session)
