from __future__ import annotations

import pytest
import requests

from nanojud import extraction, tjrj
from nanojud.client import NanoJudClient
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado
from nanojud.sources import ALL_SOURCES, normalizar_fonte

CNJ = "0032991-06.2012.8.19.0066"


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if hasattr(self, "post_error"):
            raise self.post_error
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.get_url = url
        if hasattr(self, "get_error"):
            raise self.get_error
        return getattr(self, "get_response", FakeResponse({}))


def _search():
    return [
        {
            "codigoCnj": CNJ,
            "numProcesso": "2012.066.032481-3",
            "tipoProcesso": 1,
        }
    ]


def _detail(**overrides):
    return {
        "codCnj": CNJ,
        "codProc": "2012.066.032481-3",
        "codTipProcesso": "1",
        "formaConsulta": "PUBLICA",
        "indSigilo": "N",
        "isAutenticado": False,
        "txtAcao": "Ação pública",
        "txtAssunto": "Assunto público",
        "descServ": "Comarca de exemplo",
        "descVara": "Vara Cível",
        "dataDis": "2012-01-01",
        "todosMovimentos": False,
        "processoVolumoso": False,
        "exibePaginacaoProcessoVolumoso": False,
        **overrides,
    }


def _movements(**overrides):
    return {
        "codCnj": CNJ,
        "codTipProcesso": "1",
        "formaConsulta": "PUBLICA",
        "indSigilo": "N",
        "isAutenticado": False,
        "todosMovimentos": True,
        "processoVolumoso": False,
        "exibePaginacaoProcessoVolumoso": False,
        "movimentosProc": [
            {
                "ordem": 1,
                "dtMovimento": "12/11/2026",
                "descrMov": "Juntada de petição",
                "descricao": "Descrição pública",
                "codTipAnd": 12,
            }
        ],
        **overrides,
    }


def _movement_group(order: int | None, *, submovements: int = 1):
    return {
        **({"ordem": order} if order is not None else {}),
        "dtMovimento": "12/11/2026",
        "descrMov": "Movimentação agrupada",
        "descricao": "Descrição do grupo",
        "codTipAnd": 12,
        "movimentosExibicao": [
            {
                "tipoMovimento": f"Tipo {index}",
                "resumoOuIntegra": {"descResumida": f"Resumo {index}"},
                "detalhesMovimento": [],
            }
            for index in range(submovements)
        ],
    }


def test_consultar_processo_monta_extrato_e_confirma_completude():
    session = FakeSession(
        [FakeResponse(_search()), FakeResponse(_detail()), FakeResponse(_movements())]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert result["status"] == "ok"
    assert result["dados_basicos"]["numero"] == CNJ
    assert result["dados_basicos"]["vara"] == "Vara Cível"
    assert result["origem"]["movimentacoes_completas"] is True
    assert result["movimentacoes"][0]["titulo"] == "Juntada de petição"
    assert session.get_url == f"{tjrj.ORIGIN}/"
    assert len(session.posts) == 3
    assert session.posts[0][1]["json"]["codigoProcesso"] == CNJ
    assert session.posts[1][1]["json"]["codigoProcesso"] == "2012.066.032481-3"
    assert session.posts[2][1]["json"]["indProcVolumoso"] == "N"
    assert "ultimaOrdemExibida" not in session.posts[2][1]["json"]


def test_consultar_processo_rejeita_resposta_de_outro_cnj():
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail(codCnj="0000000-00.0000.8.19.0000")),
        ]
    )

    with pytest.raises(ConsultaIndisponivel, match="não confirmou o CNJ"):
        tjrj.consultar_processo(CNJ, session=session)


def test_consultar_processo_nao_afirma_completude_se_api_indica_paginacao():
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail()),
            FakeResponse(
                _movements(
                    todosMovimentos=False,
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                )
            ),
            FakeResponse(
                _movements(
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                    movimentosProc=[_movement_group(1)],
                )
            ),
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert result["status"] == "partial"
    assert result["origem"]["movimentacoes_completas"] is False


def test_consultar_processo_expande_submovimentacoes_exibidas_pelo_portal():
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail()),
            FakeResponse(_movements(movimentosProc=[_movement_group(3, submovements=2)])),
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert len(result["movimentacoes"]) == 2
    assert [item["metadados"]["tipo_movimento"] for item in result["movimentacoes"]] == [
        "Tipo 0",
        "Tipo 1",
    ]


def test_consultar_processo_preserva_tipo_e_detalhes_do_submovimento():
    grupo = {
        "ordem": 3,
        "movimentosExibicao": [
            {
                "descrTipAto": "Despacho",
                "detalhesMovimento": [{"descricao": "Conclusos para decisão"}],
            }
        ],
    }
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail()),
            FakeResponse(_movements(movimentosProc=[grupo])),
        ]
    )

    movement = tjrj.consultar_processo(CNJ, session=session)["movimentacoes"][0]

    assert movement["titulo"] == "Despacho"
    assert movement["teor"] == "Conclusos para decisão"
    assert movement["metadados"]["descricao_tipo_ato"] == "Despacho"
    assert movement["metadados"]["detalhes_movimento"] == ["Conclusos para decisão"]


def test_consultar_processo_pagina_historico_volumoso_ate_cursor_terminal():
    first_page = _movements(
        processoVolumoso=True,
        exibePaginacaoProcessoVolumoso=True,
        movimentosProc=[_movement_group(10, submovements=2)],
    )
    terminal_page = _movements(
        processoVolumoso=True,
        exibePaginacaoProcessoVolumoso=True,
        movimentosProc=[_movement_group(None)],
    )
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail(processoVolumoso=True, exibePaginacaoProcessoVolumoso=True)),
            FakeResponse(first_page),
            FakeResponse(terminal_page),
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert result["status"] == "ok"
    assert result["origem"]["movimentacoes_completas"] is True
    assert result["origem"]["movimentacoes_paginas"] == 2
    assert result["origem"]["movimentacoes_registros"] == 3
    assert len(result["movimentacoes"]) == 3
    assert session.posts[3][1]["json"]["ultimaOrdemExibida"] == 10


def test_consultar_processo_volumoso_respeita_limite_e_mantem_partial():
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail(processoVolumoso=True, exibePaginacaoProcessoVolumoso=True)),
            FakeResponse(
                _movements(
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                    movimentosProc=[_movement_group(10)],
                )
            ),
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session, max_paginas_movimentos=1)

    assert result["status"] == "partial"
    assert result["origem"]["movimentacoes_paginas"] == 1
    assert len(result["movimentacoes"]) == 1
    assert len(session.posts) == 3


def test_consultar_processo_volumoso_nao_duplica_pagina_com_cursor_repetido():
    grupo = _movement_group(10)
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail(processoVolumoso=True, exibePaginacaoProcessoVolumoso=True)),
            FakeResponse(
                _movements(
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                    movimentosProc=[grupo],
                )
            ),
            FakeResponse(
                _movements(
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                    movimentosProc=[grupo],
                )
            ),
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert result["status"] == "partial"
    assert result["origem"]["movimentacoes_completas"] is False
    assert result["origem"]["movimentacoes_paginas"] == 2
    assert len(result["movimentacoes"]) == 1


def test_consultar_processo_volumoso_aceita_ordem_zero_como_fim():
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail(processoVolumoso=True, exibePaginacaoProcessoVolumoso=True)),
            FakeResponse(
                _movements(
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                    movimentosProc=[_movement_group(0)],
                )
            ),
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert result["status"] == "ok"
    assert result["origem"]["movimentacoes_completas"] is True
    assert result["movimentacoes"][0]["ordem"] == 0


@pytest.mark.parametrize(
    "pagina_ruim",
    [
        FakeResponse({}, status_code=503),
        FakeResponse(_movements(codCnj="0000000-00.0000.8.19.0000")),
        FakeResponse(_movements(movimentosProc="inesperado")),
        FakeResponse(_movements(movimentosProc=[{"ordem": 9, "movimentosExibicao": "inesperado"}])),
    ],
)
def test_consultar_processo_volumoso_preserva_parcial_se_pagina_seguinte_falha(pagina_ruim):
    primeira = _movements(
        processoVolumoso=True,
        exibePaginacaoProcessoVolumoso=True,
        movimentosProc=[_movement_group(10)],
    )
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail(processoVolumoso=True, exibePaginacaoProcessoVolumoso=True)),
            FakeResponse(primeira),
            pagina_ruim,
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert result["status"] == "partial"
    assert result["origem"]["movimentacoes_completas"] is False
    assert result["movimentacoes"]


def test_consultar_processo_volumoso_fecha_historico_com_pagina_vazia_confirmada():
    session = FakeSession(
        [
            FakeResponse(_search()),
            FakeResponse(_detail(processoVolumoso=True, exibePaginacaoProcessoVolumoso=True)),
            FakeResponse(
                _movements(
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                    movimentosProc=[_movement_group(10)],
                )
            ),
            FakeResponse(
                _movements(
                    processoVolumoso=True,
                    exibePaginacaoProcessoVolumoso=True,
                    movimentosProc=[],
                )
            ),
        ]
    )

    result = tjrj.consultar_processo(CNJ, session=session)

    assert result["status"] == "ok"
    assert result["origem"]["movimentacoes_paginas"] == 2


@pytest.mark.parametrize("max_paginas", [True, 0, 501, 1.5, "2"])
def test_consultar_processo_rejeita_limite_de_paginas_invalido_antes_da_rede(max_paginas):
    session = FakeSession([])

    with pytest.raises(ValueError, match="max_paginas_movimentos"):
        tjrj.consultar_processo(CNJ, session=session, max_paginas_movimentos=max_paginas)

    assert not session.posts
    assert not hasattr(session, "get_url")


def test_consultar_processo_nao_expoe_parte_e_rejeita_sigilo():
    session = FakeSession([FakeResponse(_search()), FakeResponse(_detail(indSigilo="S"))])

    with pytest.raises(AcessoRestrito, match="sigilo"):
        tjrj.consultar_processo(CNJ, session=session)


def test_tjrj_fica_opt_in_e_tem_selecao_de_fonte():
    assert "tjrj_1g" not in ALL_SOURCES
    assert normalizar_fonte("tjrj_1g") == "tjrj_1g"


def test_cliente_repassa_sessao_e_timeout_para_tjrj(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "nanojud.client.tjrj.consultar_processo",
        lambda numero, **kwargs: captured.update(kwargs) or {"status": "ok"},
    )
    client = NanoJudClient()

    assert client.consultar_tjrj_1g(CNJ, timeout=9, max_paginas_movimentos=17) == {"status": "ok"}
    assert captured["session"] is client.session
    assert captured["timeout"] == 9
    assert captured["max_paginas_movimentos"] == 17


def test_extracao_selecionada_tjrj_preserva_capa_e_timeline(monkeypatch):
    monkeypatch.setattr(
        "nanojud.extraction.tjrj.consultar_processo",
        lambda numero, **kwargs: {
            "status": "ok",
            "origem": {
                "movimentacoes_completas": True,
                "grau": "1G",
                "url_final": "https://example.test",
            },
            "dados_basicos": {"numero": numero},
            "movimentacoes": [
                {"ordem": 1, "data": "12/11/2026", "titulo": "Distribuído", "teor": ""}
            ],
        },
    )

    result = extraction.extract_process(CNJ, sources=("tjrj_1g",))

    assert result["source_status"]["tjrj_1g"]["status"] == "ok"
    assert result["data"]["tjrj_1g"]["dados_basicos"]["numero"] == CNJ
    assert result["timeline"][0]["fonte"] == "tjrj_1g"


def test_fonte_tjrj_nao_aplicavel_a_outro_tribunal_sem_rede():
    result = extraction.extract_process("1076539-20.2019.8.26.0100", sources=("tjrj_1g",))

    assert result["source_status"]["tjrj_1g"]["status"] == "nao_aplicavel"


def test_sessao_padrao_tem_cabecalhos_da_spa_publica():
    session = tjrj._sessao(None)

    assert session.headers["Origin"] == tjrj.SITE_ORIGIN
    assert session.headers["Referer"] == f"{tjrj.ORIGIN}/"
    assert session.headers["Content-Type"] == "application/json;charset=UTF-8"


def test_endpoint_rejeita_host_ou_esquema_nao_oficial():
    from nanojud.exceptions import URLInvalida

    with pytest.raises(URLInvalida):
        tjrj._validar_endpoint(
            "http://example.com/consultaprocessual/api/processos/por-numero/publica"
        )


@pytest.mark.parametrize(
    ("status_code", "exception"),
    [
        (401, AcessoRestrito),
        (404, ProcessoNaoEncontrado),
        (429, ConsultaIndisponivel),
        (500, ConsultaIndisponivel),
        (422, ConsultaIndisponivel),
    ],
)
def test_post_classifica_http_sem_expor_corpo(status_code, exception):
    session = FakeSession([FakeResponse({}, status_code=status_code)])

    with pytest.raises(exception):
        tjrj._post(session, tjrj.SEARCH_ENDPOINT, {}, timeout=1)


def test_post_rejeita_json_invalido():
    class InvalidJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("bad json")

    session = FakeSession([InvalidJsonResponse({})])

    with pytest.raises(ConsultaIndisponivel, match="JSON válido"):
        tjrj._post(session, tjrj.SEARCH_ENDPOINT, {}, timeout=1)


def test_post_classifica_falha_de_transporte():
    session = FakeSession([])
    session.post_error = requests.Timeout()

    with pytest.raises(ConsultaIndisponivel, match="Timeout"):
        tjrj._post(session, tjrj.SEARCH_ENDPOINT, {}, timeout=1)


@pytest.mark.parametrize(
    "response,exception",
    [
        (FakeResponse({}, status_code=412), AcessoRestrito),
        (FakeResponse({}, status_code=503), ConsultaIndisponivel),
    ],
)
def test_bootstrap_classifica_status_http(response, exception):
    session = FakeSession([])
    session.get_response = response

    with pytest.raises(exception):
        tjrj._iniciar_sessao(session, timeout=1)


def test_bootstrap_classifica_falha_de_transporte():
    session = FakeSession([])
    session.get_error = requests.ConnectionError()

    with pytest.raises(ConsultaIndisponivel, match="ConnectionError"):
        tjrj._iniciar_sessao(session, timeout=1)


def test_data_lida_com_data_iso_brasileira_e_vazia():
    assert tjrj._data("2026-11-12T10:30:00") == "2026-11-12"
    assert tjrj._data("12/11/2026") == "2026-11-12"
    assert tjrj._data(None) == ""
    assert tjrj._data("not a date") == "not a date"


@pytest.mark.parametrize(
    "payload,exception",
    [
        ({}, ConsultaIndisponivel),
        ([{"codigoCnj": CNJ, "tipoProcesso": 1}], ConsultaIndisponivel),
        (
            [{"codigoCnj": CNJ, "tipoProcesso": 2, "numProcesso": "2023.001.38652"}],
            ProcessoNaoEncontrado,
        ),
        ([{"codigoCnj": CNJ, "tipoProcesso": 1}], ConsultaIndisponivel),
    ],
)
def test_busca_sem_origem_utilizavel_falha_fechado(monkeypatch, payload, exception):
    answers = [payload]
    monkeypatch.setattr(tjrj, "_iniciar_sessao", lambda *a, **k: None)
    monkeypatch.setattr(tjrj, "_post", lambda *a, **k: answers.pop(0))

    with pytest.raises(exception):
        tjrj.consultar_processo(CNJ)


@pytest.mark.parametrize(
    "detail,movements,exception",
    [
        ([], None, ConsultaIndisponivel),
        (_detail(indSigilo="S"), None, AcessoRestrito),
        (_detail(), [], ConsultaIndisponivel),
        (
            _detail(),
            {"codCnj": "0000000-00.0000.8.19.0000", "movimentosProc": []},
            ConsultaIndisponivel,
        ),
        (_detail(), {"codCnj": CNJ, "movimentosProc": "unexpected"}, ConsultaIndisponivel),
    ],
)
def test_detalhe_e_movimentos_inesperados_falham_fechado(monkeypatch, detail, movements, exception):
    answers = [_search(), detail, movements]
    monkeypatch.setattr(tjrj, "_iniciar_sessao", lambda *a, **k: None)
    monkeypatch.setattr(tjrj, "_post", lambda *a, **k: answers.pop(0))

    with pytest.raises(exception):
        tjrj.consultar_processo(CNJ)
