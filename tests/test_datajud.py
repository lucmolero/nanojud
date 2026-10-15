import pytest
import requests

from nanojud import datajud
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

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
            ]
        }
    }


def test_indice_datajud_tjsp():
    assert datajud.indice_datajud("1076539-20.2019.8.26.0100") == "tjsp"


def test_indice_datajud_outros_segmentos(monkeypatch):
    monkeypatch.setattr(datajud, "validar_numero_cnj", lambda numero, **kwargs: numero)

    assert datajud.indice_datajud("0000001-02.2020.4.01.0000") == "trf1"
    assert datajud.indice_datajud("0000001-02.2020.5.02.0000") == "trt2"
    assert datajud.indice_datajud("0000001-02.2020.2.00.0000") == "stj"


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


def test_consultar_processo_nao_encontrado():
    session = FakeSession(FakeResponse(200, {"hits": {"hits": []}}))

    resultado = datajud.consultar_processo(
        "1076539-20.2019.8.26.0100",
        api_key="APIKey abc",
        session=session,
        include_raw=True,
        sleep=lambda _: None,
    )

    assert resultado["status"] == "nao_encontrado"
    assert resultado["raw"] == {"hits": {"hits": []}}


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


def test_consultar_processo_http_403():
    session = FakeSession(FakeResponse(403, {}))

    with pytest.raises(AcessoRestrito):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", api_key="abc", session=session)


def test_consultar_processo_http_500():
    session = FakeSession(FakeResponse(500, {}))

    with pytest.raises(ConsultaIndisponivel):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", api_key="abc", session=session)


def test_consultar_processo_json_invalido():
    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("bad json")

    session = FakeSession(BadJsonResponse(200, {}))

    with pytest.raises(ConsultaIndisponivel):
        datajud.consultar_processo("1076539-20.2019.8.26.0100", api_key="abc", session=session)


def test_consultar_processo_erro_rede():
    session = FakeSession(FakeResponse(200, {}), exc=requests.RequestException("offline"))

    with pytest.raises(ConsultaIndisponivel):
        datajud.consultar_processo(
            "1076539-20.2019.8.26.0100",
            api_key="abc",
            session=session,
            retry=1,
        )


def _hit(grau, classe, movimentos, ajuizamento="2020-01-01T00:00:00.000Z"):
    return {
        "_source": {
            "numeroProcesso": "10765392020198260100",
            "tribunal": "TJRJ",
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
            ]
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
