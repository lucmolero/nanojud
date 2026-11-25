import pytest

from nanojud.batch import extract_processes, iter_extract_dockets, iter_extract_processes
from nanojud.exceptions import ConsultaIndisponivel
from nanojud.mni import MNI3Config


def test_batch_nao_expoe_detalhes_de_excecao_http():
    import requests

    marcador = "https://portal.example/download?ticket=segredo-sentinela"

    def extrair(*args, **kwargs):
        raise requests.ConnectionError(f"falha em {marcador}")

    item = next(
        iter_extract_processes(
            ["1076539-20.2019.8.26.0100"],
            sources=["datajud"],
            _extractor=extrair,
        )
    )

    assert item["error"]["type"] == "ConnectionError"
    assert item["error"]["message"] == "Falha HTTP (ConnectionError)."
    assert marcador not in str(item)


def test_batch_mni_requer_worker_unico_antes_de_consumir_entrada():
    def entradas():
        pytest.fail("A entrada não deve ser consumida com concorrência MNI não validada")
        yield ""

    with pytest.raises(ValueError, match="MNI usam max_workers=1"):
        list(iter_extract_processes(entradas(), sources=["mni"], max_workers=2))


def test_batch_repassa_configuracao_mni_ao_extrator():
    config = MNI3Config(endpoint="https://mni.example/Servico", token="token")
    chamadas = []

    def extrair(numero, **kwargs):
        chamadas.append(kwargs)
        return {
            "schema_version": "1.0",
            "package_version": "0.5.3",
            "status": "ok",
            "numero_cnj": numero,
            "sources": ["mni"],
            "extracted_at": "2026-11-12T00:00:00Z",
            "data": {},
            "timeline": [],
            "warnings": [],
            "errors": [],
            "source_status": {"mni": {"status": "ok", "records": 0}},
        }

    item = next(
        iter_extract_processes(
            ["1001194-30.2024.8.26.0114"],
            sources=["mni"],
            mni_config=config,
            _extractor=extrair,
        )
    )

    assert item["status"] == "ok"
    assert chamadas[0]["mni_config"] is config


def test_fechar_iterador_cancela_futures_ainda_nao_iniciados(monkeypatch):
    from concurrent.futures import Future

    import nanojud.batch as batch

    class PoolControlado:
        def __init__(self, **kwargs):
            self.futures = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def submit(self, _func, *_args):
            futuro = Future()
            if not self.futures:
                futuro.set_result({"index": 0, "input": "cnj-0", "status": "error"})
            self.futures.append(futuro)
            return futuro

    pools = []

    def criar_pool(**kwargs):
        pool = PoolControlado(**kwargs)
        pools.append(pool)
        return pool

    monkeypatch.setattr(batch, "ThreadPoolExecutor", criar_pool)
    iterador = iter_extract_processes(["cnj-0", "cnj-1"], sources=["datajud"], max_workers=2)

    assert next(iterador)["input"] == "cnj-0"
    iterador.close()

    assert pools[0].futures[1].cancelled()


def _envelope(numero, status="ok", errors=None, source_status=None):
    return {
        "schema_version": "1.0",
        "package_version": "0.5.3",
        "status": status,
        "numero_cnj": numero,
        "sources": ["datajud"],
        "extracted_at": "2026-01-01T00:00:00Z",
        "data": {},
        "timeline": [],
        "warnings": [],
        "errors": errors or [],
        "source_status": source_status or {"datajud": {"status": "ok", "records": 1}},
    }


def test_batch_usa_tentativas_padrao_do_cliente_datajud():
    chamadas = []

    def extrair(numero, **kwargs):
        chamadas.append(kwargs)
        return _envelope(numero)

    item = next(
        iter_extract_processes(
            ["1076539-20.2019.8.26.0100"],
            sources=["datajud"],
            _extractor=extrair,
        )
    )

    assert item["status"] == "ok"
    assert chamadas[0]["datajud_retry"] == 3
    assert chamadas[0]["prazo_total"] == 60.0


def test_batch_isola_expiracao_datajud_e_preserva_djen(monkeypatch):
    from nanojud import batch, extraction

    datajud_chamadas = []
    djen_chamadas = []

    def datajud_expirado(numero, **kwargs):
        datajud_chamadas.append(numero)
        assert kwargs["prazo_total"] > 0
        raise TimeoutError("DataJud excedeu o prazo total da consulta.")

    def djen_ok(numero, **kwargs):
        djen_chamadas.append(numero)
        return {
            "status": "ok",
            "completo": True,
            "paginas": 1,
            "avisos": [],
            "comunicacoes": [
                {
                    "id": f"comunicacao-{len(djen_chamadas)}",
                    "numeroProcesso": numero,
                    "dataDisponibilizacao": "2026-11-12",
                    "tipoComunicacao": "Intimação",
                    "texto": "Comunicação pública",
                }
            ],
        }

    monkeypatch.setattr(extraction.datajud, "consultar_processo", datajud_expirado)
    monkeypatch.setattr(extraction.djen, "consultar_processo_detalhado", djen_ok)
    numeros = ["0015020-23.2010.8.26.0053", "1076539-20.2019.8.26.0100"]

    resultado = batch.extract_processes(
        numeros,
        sources=["datajud", "djen"],
        prazo_total=5,
        _extractor=extraction.extract_process,
    )

    assert resultado["partial"] == 2
    assert resultado["failed"] == 0
    assert datajud_chamadas == [numeros[0]]
    assert djen_chamadas == numeros
    primeiro, segundo = resultado["items"]
    assert primeiro["result"]["source_status"]["datajud"]["status"] == "error"
    assert primeiro["result"]["source_status"]["datajud"]["type"] == "TimeoutError"
    assert primeiro["result"]["source_status"]["djen"]["status"] == "ok"
    assert segundo["result"]["source_status"]["datajud"]["status"] == "skipped"
    assert segundo["result"]["source_status"]["djen"]["status"] == "ok"
    assert all(item["result"]["data"]["djen"] for item in (primeiro, segundo))
    assert all(item["result"]["timeline"] for item in (primeiro, segundo))


@pytest.mark.parametrize(
    ("opcoes", "mensagem"),
    [
        ({"max_workers": 0}, "max_workers"),
        ({"max_workers": True}, "max_workers"),
        ({"max_workers": 1.5}, "max_workers"),
        ({"circuit_breaker_threshold": 0}, "circuit_breaker_threshold"),
        ({"circuit_breaker_threshold": False}, "circuit_breaker_threshold"),
        ({"circuit_breaker_threshold": 1.5}, "circuit_breaker_threshold"),
        ({"circuit_breaker_cooldown": -1}, "circuit_breaker_cooldown"),
        ({"circuit_breaker_cooldown": True}, "circuit_breaker_cooldown"),
        ({"circuit_breaker_cooldown": float("nan")}, "circuit_breaker_cooldown"),
        ({"circuit_breaker_cooldown": float("inf")}, "circuit_breaker_cooldown"),
        ({"circuit_breaker_cooldown": 10**1000}, "circuit_breaker_cooldown"),
        ({"datajud_retry": 0}, "datajud_retry"),
        ({"datajud_retry": True}, "datajud_retry"),
        ({"datajud_retry": 1.5}, "datajud_retry"),
        ({"timeout": None}, "timeout"),
        ({"timeout": 0}, "timeout"),
        ({"timeout": float("nan")}, "timeout"),
        ({"timeout": float("inf")}, "timeout"),
        ({"timeout": 86401}, "timeout"),
        ({"timeout": 1e100}, "timeout"),
        ({"prazo_total": -1}, "prazo_total"),
        ({"prazo_total": float("nan")}, "prazo_total"),
        ({"prazo_total": float("inf")}, "prazo_total"),
        ({"prazo_total": 86401}, "prazo_total"),
        ({"prazo_total": 1e100}, "prazo_total"),
        ({"sources": []}, "pelo menos uma fonte"),
    ],
)
def test_batch_rejeita_configuracao_invalida_antes_de_consumir_entrada(opcoes, mensagem):
    def entradas():
        pytest.fail("A entrada não deve ser consumida com configuração inválida")
        yield ""

    with pytest.raises(ValueError, match=mensagem):
        list(iter_extract_processes(entradas(), **opcoes))


def test_lote_de_autos_isola_falha_do_portal_de_entrada_invalida(tmp_path):
    def indisponivel(*args, **kwargs):
        raise ConsultaIndisponivel("Portal temporariamente indisponível")

    itens = list(
        iter_extract_dockets(
            ["5060583-19.2021.8.13.0024", "inválido", "1076539-20.2019.8.26.0100"],
            destination=str(tmp_path),
            _consultar_pje=indisponivel,
            _get_extrato=indisponivel,
        )
    )

    assert [item["status"] for item in itens] == ["error", "error", "error"]
    assert [item["index"] for item in itens] == [0, 1, 2]
    assert itens[0]["error"]["type"] == itens[2]["error"]["type"] == "ConsultaIndisponivel"
    assert "numero_cnj" not in itens[1]
    assert list(tmp_path.iterdir()) == []


def test_lote_de_autos_repassa_timeout_a_esaj_e_pje(monkeypatch, tmp_path):
    from nanojud import api

    esaj_numero = "1076539-20.2019.8.26.0100"
    pje_numero = "5060583-19.2021.8.13.0024"
    chamadas = []

    def extrato_esaj(numero, **kwargs):
        chamadas.append(("esaj", kwargs["timeout"]))
        return {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True},
            "documentos": {"publicos_candidatos_unicos": [], "baixados": []},
        }

    def consultar_pje(numero, *, timeout, session):
        chamadas.append(("pje", timeout))
        return {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True, "documentos_completos": True},
            "documentos": {
                "publicos_candidatos_unicos": [
                    {"cd_documento": "doc-1", "titulo": "Decisão", "href": "https://pje/doc"}
                ]
            },
        }

    def baixar_pje(url, destino, *, timeout, session):
        chamadas.append(("baixar_pje", timeout))
        return {"status": "baixado", "arquivo": str(destino), "bytes": 8}

    monkeypatch.setattr(api, "get_extrato", extrato_esaj)
    monkeypatch.setattr(api, "consultar_pje_tjmg", consultar_pje)
    monkeypatch.setattr(api, "baixar_documento_pje_tjmg", baixar_pje)
    itens = list(
        iter_extract_dockets([esaj_numero, pje_numero], destination=str(tmp_path), timeout=7)
    )

    assert [item["status"] for item in itens] == ["no_documents", "ok"]
    assert chamadas == [("esaj", 7), ("pje", 7), ("baixar_pje", 7)]


@pytest.mark.parametrize(
    ("opcao", "valor"),
    [
        ("max_documents_per_process", False),
        ("max_documents_per_process", True),
        ("max_documents_per_process", 1.5),
        ("document_max_chars", False),
        ("document_max_chars", True),
        ("document_max_chars", 1.5),
    ],
)
def test_lote_de_autos_rejeita_limites_que_nao_sao_inteiros(opcao, valor, tmp_path):
    with pytest.raises(ValueError, match=opcao):
        list(iter_extract_dockets([], destination=str(tmp_path), **{opcao: valor}))


@pytest.mark.parametrize(
    ("opcao", "valor"),
    [("max_documents_per_process", -1), ("document_max_chars", -1)],
)
def test_lote_de_autos_valida_limites_antes_de_criar_sessao_pje(
    monkeypatch, tmp_path, opcao, valor
):
    from nanojud import pje_tjmg

    def sessao_nao_deve_ser_criada():
        pytest.fail("A sessão PJe não deve ser criada para configuração inválida")

    monkeypatch.setattr(pje_tjmg, "criar_sessao", sessao_nao_deve_ser_criada)
    with pytest.raises(ValueError, match=opcao):
        list(iter_extract_dockets([], destination=str(tmp_path), **{opcao: valor}))


@pytest.mark.parametrize("numeros", [[], ["1076539-20.2019.8.26.0100"]])
def test_lote_de_autos_nao_abre_sessao_pje_sem_consulta_pje(monkeypatch, tmp_path, numeros):
    from nanojud import pje_tjmg

    def sessao_pje_nao_e_necessaria():
        pytest.fail("Lotes vazios ou apenas eSAJ não devem abrir uma sessão PJe")

    monkeypatch.setattr(pje_tjmg, "criar_sessao", sessao_pje_nao_e_necessaria)
    extrato = {
        "status": "ok",
        "dados_basicos": {},
        "movimentacoes": [],
        "origem": {"movimentacoes_completas": True},
        "documentos": {
            "publicos_candidatos_unicos": [],
            "restritos_por_senha_unicos": [],
            "baixados": [],
        },
    }
    list(
        iter_extract_dockets(
            numeros,
            destination=str(tmp_path),
            _get_extrato=lambda *_args, **_kwargs: extrato,
        )
    )


def test_lote_de_autos_cria_sessao_pje_so_ao_precisar_e_reutiliza(monkeypatch, tmp_path):
    from nanojud import api, pje_tjmg

    class Sessao:
        fechada = False

        def close(self):
            self.fechada = True

    sessao = Sessao()
    criacoes = []
    sessoes_usadas = []
    numeros = ["5060583-19.2021.8.13.0024", "6000890-97.2015.8.13.0024"]

    def criar_sessao():
        criacoes.append(True)
        return sessao

    def consultar(numero, *, session, timeout):
        sessoes_usadas.append(session)
        return {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True, "documentos_completos": True},
            "documentos": {
                "publicos_candidatos_unicos": [
                    {"cd_documento": numero, "href": "https://pje.test/doc"}
                ]
            },
        }

    def baixar(url, destino, *, session, timeout):
        sessoes_usadas.append(session)
        return {"status": "baixado", "arquivo": str(destino)}

    monkeypatch.setattr(pje_tjmg, "criar_sessao", criar_sessao)
    monkeypatch.setattr(api, "consultar_pje_tjmg", consultar)
    monkeypatch.setattr(api, "baixar_documento_pje_tjmg", baixar)
    itens = list(iter_extract_dockets(numeros, destination=str(tmp_path)))

    assert [item["status"] for item in itens] == ["ok", "ok"]
    assert criacoes == [True]
    assert sessoes_usadas == [sessao] * 4
    assert sessao.fechada


def test_lote_de_autos_fecha_sessao_pje_ao_interromper_iterador(monkeypatch, tmp_path):
    from nanojud import api, pje_tjmg

    class Sessao:
        fechada = False

        def close(self):
            self.fechada = True

    sessao = Sessao()
    monkeypatch.setattr(pje_tjmg, "criar_sessao", lambda: sessao)
    monkeypatch.setattr(
        api,
        "consultar_pje_tjmg",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True, "documentos_completos": True},
            "documentos": {"publicos_candidatos_unicos": []},
        },
    )
    numeros = ["5060583-19.2021.8.13.0024", "6000890-97.2015.8.13.0024"]
    iterador = iter_extract_dockets(numeros, destination=str(tmp_path))

    assert next(iterador)["status"] == "no_documents"
    iterador.close()

    assert sessao.fechada


@pytest.mark.parametrize("timeout", [None, 0, -1, float("nan"), float("inf"), 86401, True])
def test_lote_de_autos_rejeita_timeout_invalido_antes_de_consumir_entrada(timeout, tmp_path):
    def entradas():
        pytest.fail("A entrada não deve ser consumida com timeout inválido")
        yield ""

    with pytest.raises(ValueError, match="timeout"):
        list(iter_extract_dockets(entradas(), destination=str(tmp_path), timeout=timeout))


def test_lote_de_autos_isola_sucesso_restricao_e_indisponibilidade(tmp_path):
    cnj_publico = "1076539-20.2019.8.26.0100"
    cnj_restrito = "0015020-23.2010.8.26.0053"
    cnj_indisponivel = "5060583-19.2021.8.13.0024"

    def obter_extrato(numero, **kwargs):
        if numero == cnj_restrito:
            return {
                "status": "ok",
                "dados_basicos": {},
                "movimentacoes": [],
                "origem": {"movimentacoes_completas": True},
                "documentos": {
                    "publicos_candidatos_unicos": [],
                    "restritos_por_senha_unicos": [{"cd_documento": "restrito-1"}],
                    "baixados": [],
                },
            }
        return {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True},
            "documentos": {
                "publicos_candidatos_unicos": [
                    {"cd_documento": "publico-1", "download_status": "baixado"}
                ],
                "restritos_por_senha_unicos": [],
                "baixados": [{"cd_documento": "publico-1", "status": "baixado"}],
            },
        }

    def consultar_pje(numero):
        raise ConsultaIndisponivel("PJe temporariamente indisponível")

    itens = list(
        iter_extract_dockets(
            [cnj_publico, cnj_restrito, cnj_indisponivel],
            destination=str(tmp_path),
            _get_extrato=obter_extrato,
            _consultar_pje=consultar_pje,
        )
    )

    assert [item["input"] for item in itens] == [cnj_publico, cnj_restrito, cnj_indisponivel]
    assert [item["status"] for item in itens] == ["ok", "partial", "error"]
    assert itens[0]["downloaded"][0]["cd_documento"] == "publico-1"
    assert itens[1]["restricted_documents"] == 1
    assert "restrito" in " ".join(itens[1]["warnings"])
    assert itens[2]["error"]["type"] == "ConsultaIndisponivel"


def test_lote_esaj_preserva_aviso_especifico_de_paginacao_parcial(tmp_path):
    numero = "1076539-20.2019.8.26.0100"
    aviso = "A página 3 de movimentações expirou; 2 páginas ficaram pendentes."

    item = next(
        iter_extract_dockets(
            [numero],
            destination=str(tmp_path),
            _get_extrato=lambda *_args, **_kwargs: {
                "status": "ok",
                "dados_basicos": {},
                "movimentacoes": [],
                "origem": {
                    "movimentacoes_completas": False,
                    "aviso_movimentacoes": aviso,
                },
                "documentos": {
                    "publicos_candidatos_unicos": [],
                    "restritos_por_senha_unicos": [],
                    "baixados": [],
                },
            },
        )
    )

    assert item["status"] == "partial"
    assert aviso in item["warnings"]


@pytest.mark.parametrize(
    ("liberado", "status_tentativa", "status_item"),
    [
        (False, "nao_liberado_pelo_portal", "partial"),
        (True, "liberado", "ok"),
    ],
)
def test_lote_esaj_preserva_resultado_da_tentativa_de_senha_sem_expor_credencial(
    tmp_path, liberado, status_tentativa, status_item
):
    numero = "1076539-20.2019.8.26.0100"
    documento = {"cd_documento": "doc-1", "titulo": "Petição"}
    documentos = {
        "publicos_candidatos_unicos": [
            {**documento, "status_acesso": "publico_candidato", "download_status": "baixado"}
        ]
        if liberado
        else [],
        "restritos_por_senha_unicos": [] if liberado else [documento],
        "tentativas_autorizacao": [
            {"status": status_tentativa, "documentos_liberados": int(liberado)}
        ],
        "baixados": [{**documento, "status": "baixado"}] if liberado else [],
    }
    extrato = {
        "status": "ok",
        "dados_basicos": {},
        "movimentacoes": [],
        "origem": {"movimentacoes_completas": True},
        "documentos": documentos,
    }

    item = next(
        iter_extract_dockets(
            [numero],
            destination=str(tmp_path),
            _get_extrato=lambda *_args, **_kwargs: extrato,
        )
    )

    assert item["status"] == status_item
    assert item["authorization_attempts"] == documentos["tentativas_autorizacao"]
    assert item["restricted_documents"] == int(not liberado)
    assert "senha_processo" not in str(item)


def test_batch_isola_entrada_invalida_e_preserva_ordem():
    vistos = []

    def extrair(numero, **kwargs):
        vistos.append(numero)
        return _envelope(numero)

    itens = list(
        iter_extract_processes(
            ["1076539-20.2019.8.26.0100", "invalido", "0015020-23.2010.8.26.0053"],
            sources=["datajud"],
            _extractor=extrair,
        )
    )

    assert [item["index"] for item in itens] == [0, 1, 2]
    assert [item["status"] for item in itens] == ["ok", "error", "ok"]
    assert len(vistos) == 2
    assert extract_processes([], sources=["datajud"]) == {
        "schema_version": "1.0",
        "total": 0,
        "succeeded": 0,
        "partial": 0,
        "failed": 0,
        "items": [],
    }


def test_batch_abre_circuito_para_fonte_indisponivel():
    chamadas = []

    def extrair(numero, *, sources, **kwargs):
        chamadas.append(tuple(sources))
        if "datajud" in sources:
            return _envelope(
                numero,
                "partial",
                [{"source": "datajud", "type": "ConsultaIndisponivel", "message": "timeout"}],
                {"datajud": {"status": "error", "type": "ConsultaIndisponivel"}},
            )
        return _envelope(numero, "partial", [], {"datajud": {"status": "skipped"}})

    itens = list(
        iter_extract_processes(
            ["1076539-20.2019.8.26.0100", "0015020-23.2010.8.26.0053"],
            sources=["datajud"],
            _extractor=extrair,
        )
    )

    assert chamadas == [("datajud",)]
    assert itens[1]["result"]["source_status"]["datajud"]["status"] == "skipped"
    assert itens[1]["result"]["errors"][0]["type"] == "CircuitBreakerOpen"


def test_batch_reseta_falhas_datajud_apos_resposta_parcial_com_dados():
    chamadas = []

    def extrair(numero, **kwargs):
        chamadas.append(numero)
        if len(chamadas) in {1, 3}:
            return _envelope(
                numero,
                "error",
                [{"source": "datajud", "type": "ConsultaIndisponivel", "message": "429"}],
                {"datajud": {"status": "error", "type": "ConsultaIndisponivel"}},
            )
        if len(chamadas) == 2:
            return _envelope(
                numero,
                "partial",
                source_status={"datajud": {"status": "partial", "records": 1}},
            )
        return _envelope(numero)

    itens = list(
        iter_extract_processes(
            [
                "1076539-20.2019.8.26.0100",
                "0015020-23.2010.8.26.0053",
                "5060583-19.2021.8.13.0024",
                "1001194-30.2024.8.26.0114",
            ],
            sources=["datajud"],
            circuit_breaker_threshold=2,
            _extractor=extrair,
        )
    )

    assert len(chamadas) == 4
    assert [item["result"]["source_status"]["datajud"]["status"] for item in itens] == [
        "error",
        "partial",
        "error",
        "ok",
    ]


def test_batch_sem_fontes_ativas_preserva_status_skipped(monkeypatch):
    from nanojud import extraction

    chamadas = []

    def indisponivel(*args, **kwargs):
        chamadas.append(args[0])
        raise ConsultaIndisponivel("temporariamente indisponível")

    monkeypatch.setattr(extraction.datajud, "consultar_processo", indisponivel)
    itens = list(
        iter_extract_processes(
            ["1076539-20.2019.8.26.0100", "0015020-23.2010.8.26.0053"],
            sources=["datajud"],
            prazo_total=None,
        )
    )

    assert len(chamadas) == 1
    resultado = itens[1]["result"]
    assert resultado["status"] == "error"
    assert resultado["source_status"]["datajud"]["status"] == "skipped"
    assert resultado["errors"][0]["type"] == "CircuitBreakerOpen"


def test_batch_reabre_fonte_apos_expiracao_do_circuit_breaker(monkeypatch):
    from nanojud import batch

    agora = [0.0]
    chamadas = []

    def numeros():
        yield "1076539-20.2019.8.26.0100"
        yield "0015020-23.2010.8.26.0053"
        agora[0] = 61.0
        yield "0015020-23.2010.8.26.0053"

    def extrair(numero, **kwargs):
        chamadas.append(numero)
        if len(chamadas) == 1:
            return _envelope(
                numero,
                "error",
                [{"source": "datajud", "type": "ConsultaIndisponivel", "message": "timeout"}],
                {"datajud": {"status": "error", "type": "ConsultaIndisponivel"}},
            )
        return _envelope(numero, source_status={"datajud": {"status": "ok", "records": 1}})

    monkeypatch.setattr(batch.time, "monotonic", lambda: agora[0])
    itens = list(
        iter_extract_processes(
            numeros(),
            sources=["datajud"],
            circuit_breaker_cooldown=60,
            _extractor=extrair,
        )
    )

    assert chamadas == ["1076539-20.2019.8.26.0100", "0015020-23.2010.8.26.0053"]
    assert [item["status"] for item in itens] == ["error", "error", "ok"]
    assert itens[1]["result"]["source_status"]["datajud"]["status"] == "skipped"


def test_batch_concorrente_preserva_ordem():
    itens = list(
        iter_extract_processes(
            ["1076539-20.2019.8.26.0100", "0015020-23.2010.8.26.0053"],
            sources=["datajud"],
            max_workers=2,
            _extractor=lambda numero, **kwargs: _envelope(numero),
        )
    )
    assert [item["index"] for item in itens] == [0, 1]


def test_batch_concorrente_aplica_circuito_aberto_a_processos_novos():
    primeira = "1076539-20.2019.8.26.0100"
    segunda = "0015020-23.2010.8.26.0053"
    terceira = "5060583-19.2021.8.13.0024"
    chamadas = []

    def extrair(numero, *, sources, **kwargs):
        chamadas.append(numero)
        if numero == primeira:
            return _envelope(
                numero,
                "error",
                [{"source": "datajud", "type": "ConsultaIndisponivel", "message": "timeout"}],
                {"datajud": {"status": "error", "type": "ConsultaIndisponivel"}},
            )
        return _envelope(numero)

    itens = list(
        iter_extract_processes(
            [primeira, segunda, terceira],
            sources=["datajud"],
            max_workers=2,
            _extractor=extrair,
        )
    )

    assert [item["index"] for item in itens] == [0, 1, 2]
    assert "datajud" not in itens[2]["result"]["data"]
    assert itens[2]["result"]["source_status"]["datajud"]["status"] == "skipped"
    assert itens[2]["result"]["errors"][-1]["type"] == "CircuitBreakerOpen"
    assert terceira not in chamadas


def test_dockets_batch_downloads_into_process_directory(monkeypatch, tmp_path):
    from nanojud import api

    chamados = {}

    def obter(numero, **kwargs):
        chamados.update(kwargs)
        return {
            "status": "ok",
            "dados_basicos": {"classe": "Cível"},
            "movimentacoes": [{"data": "2026-01-01"}],
            "origem": {"movimentacoes_completas": True},
            "documentos": {
                "publicos_candidatos_unicos": [
                    {"cd_documento": "doc-1", "download_status": "baixado"}
                ],
                "baixados": [{"cd_documento": "doc-1", "status": "baixado"}],
            },
        }

    monkeypatch.setattr(api, "get_extrato", obter)
    itens = list(
        iter_extract_dockets(
            ["1076539-20.2019.8.26.0100"],
            destination=str(tmp_path),
            max_documents_per_process=2,
        )
    )

    assert itens[0]["status"] == "ok"
    assert itens[0]["document_candidates"] == 1
    assert itens[0]["downloaded"][0]["status"] == "baixado"
    assert chamados["baixar_pecas"] is True
    assert chamados["pasta_pecas"] == tmp_path / "1076539-20.2019.8.26.0100"


def test_dockets_batch_read_from_public_candidate_without_local_pdf(monkeypatch, tmp_path):
    from nanojud import api

    chamadas = {}
    monkeypatch.setattr(
        api,
        "get_extrato",
        lambda numero, **kwargs: (
            chamadas.update(kwargs)
            or {
                "status": "ok",
                "dados_basicos": {},
                "movimentacoes": [],
                "origem": {"movimentacoes_completas": True},
                "documentos": {
                    "publicos_candidatos_unicos": [{"cd_documento": "doc-1"}],
                    "restritos_por_senha_unicos": [],
                },
            }
        ),
    )
    monkeypatch.setattr(
        api,
        "ler_pecas",
        lambda extrato, limite, max_chars, timeout: [
            {"cd_documento": "doc-1", "status": "texto_extraido", "texto_chars": 20}
        ],
    )

    item = next(
        iter_extract_dockets(
            ["1076539-20.2019.8.26.0100"],
            destination=str(tmp_path),
            max_documents_per_process=1,
            read_documents=True,
        )
    )

    assert chamadas["baixar_pecas"] is False
    assert item["status"] == "ok"
    assert item["documents_read"][0]["texto_chars"] == 20


def test_dockets_batch_representa_sem_documentos_e_fonte_nao_suportada(monkeypatch, tmp_path):
    from nanojud import api

    monkeypatch.setattr(
        api,
        "get_extrato",
        lambda numero, **kwargs: {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True},
            "documentos": {"publicos_candidatos_unicos": []},
        },
    )

    itens = list(
        iter_extract_dockets(
            ["1076539-20.2019.8.26.0100", "0000001-19.2020.4.01.0000"],
            destination=str(tmp_path),
        )
    )

    assert itens[0]["status"] == "no_documents"
    assert itens[1]["status"] == "unsupported"


def test_dockets_batch_baixa_pje_publico_e_preserva_completude_parcial(tmp_path):
    from nanojud.batch import iter_extract_dockets

    numero = "5060583-19.2021.8.13.0024"
    extrato = {
        "status": "partial",
        "dados_basicos": {"classe": "Cível"},
        "movimentacoes": [{"data": "2026-10-21"}],
        "origem": {
            "movimentacoes_completas": False,
            "documentos_completos": False,
            "aviso_movimentacoes": "Há páginas de movimentos pendentes.",
            "aviso_documentos": "Há páginas de documentos pendentes.",
        },
        "documentos": {
            "publicos_candidatos_unicos": [
                {"cd_documento": "doc-1", "titulo": "Decisão", "href": "https://pje/doc1"},
                {"cd_documento": "doc-2", "titulo": "Petição", "href": "https://pje/doc2"},
            ]
        },
    }
    chamadas = []

    def consultar(cnj):
        chamadas.append(("consultar", cnj))
        return extrato

    def baixar(url, destino):
        chamadas.append(("baixar", url, destino))
        return {"status": "baixado", "arquivo": str(destino), "bytes": 42}

    item = next(
        iter_extract_dockets(
            [numero],
            destination=str(tmp_path),
            max_documents_per_process=1,
            _consultar_pje=consultar,
            _baixar_pje=baixar,
        )
    )

    destino = chamadas[1][2]
    assert destino.parent == tmp_path / numero
    assert destino.suffix == ".pdf"
    assert item["status"] == "partial"
    assert item["document_candidates"] == 2
    assert item["summary"]["movimentacoes_completas"] is False
    assert item["summary"]["documentos_completos"] is False
    assert item["downloaded"] == [
        {
            "cd_documento": "doc-1",
            "titulo": "Decisão",
            "status": "baixado",
            "arquivo": str(destino),
            "bytes": 42,
        }
    ]
    assert item["document_statuses"] == [
        {
            "cd_documento": "doc-1",
            "titulo": "Decisão",
            "status": "baixado",
            "message": "",
        }
    ]
    assert any("páginas" in aviso for aviso in item["warnings"])
    assert chamadas == [("consultar", numero), ("baixar", "https://pje/doc1", destino)]


def test_lote_pje_reutiliza_pdf_da_mesma_peca_apos_reordenacao(tmp_path):
    numero = "5060583-19.2021.8.13.0024"
    candidatos = [
        {"cd_documento": "10", "href": "https://pje.test/10"},
        {"cd_documento": "20", "href": "https://pje.test/20"},
        {"href": "https://pje.test/sem-id"},
    ]

    def consultar(cnj):
        return {
            "origem": {"movimentacoes_completas": True, "documentos_completos": True},
            "documentos": {"publicos_candidatos_unicos": candidatos},
        }

    def baixar(url, destino):
        if destino.exists():
            return {"status": "existente", "arquivo": str(destino)}
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(url, encoding="utf-8")
        return {"status": "baixado", "arquivo": str(destino)}

    def rodar_lote():
        return next(
            iter_extract_dockets(
                [numero],
                destination=str(tmp_path),
                _consultar_pje=consultar,
                _baixar_pje=baixar,
            )
        )

    inicial = rodar_lote()
    candidatos.reverse()
    repetido = rodar_lote()

    assert inicial["status"] == repetido["status"] == "ok"
    assert [doc["status"] for doc in repetido["downloaded"]] == ["existente"] * 3
    assert [doc["arquivo"] for doc in repetido["downloaded"]] == [
        doc["arquivo"] for doc in reversed(inicial["downloaded"])
    ]


def test_dockets_batch_le_pje_pdf_em_memoria_e_isola_falha_por_documento(tmp_path):
    numero = "5060583-19.2021.8.13.0024"
    extrato = {
        "status": "ok",
        "dados_basicos": {},
        "movimentacoes": [],
        "origem": {"movimentacoes_completas": True, "documentos_completos": True},
        "documentos": {
            "publicos_candidatos_unicos": [
                {"cd_documento": "doc-1", "titulo": "Sem texto", "href": "https://pje/doc1"},
                {"cd_documento": "doc-2", "titulo": "Com texto", "href": "https://pje/doc2"},
            ]
        },
    }
    chamadas = []

    def ler(url, *, max_chars):
        chamadas.append((url, max_chars))
        if url.endswith("doc1"):
            raise RuntimeError("PDF público indisponível")
        return {"status": "texto_extraido", "texto": "trecho", "bytes": 50}

    item = next(
        iter_extract_dockets(
            [numero],
            destination=str(tmp_path),
            max_documents_per_process=2,
            read_documents=True,
            document_max_chars=350,
            _consultar_pje=lambda _: extrato,
            _ler_pje=ler,
        )
    )

    assert chamadas == [("https://pje/doc1", 350), ("https://pje/doc2", 350)]
    assert item["status"] == "partial"
    assert item["documents_read"][0]["status"] == "error"
    assert item["documents_read"][1]["status"] == "texto_extraido"
    assert item["document_statuses"][0]["message"] == "PDF público indisponível"
    assert "output_directory" not in item


@pytest.mark.parametrize("provedor", ["esaj", "pje_tjmg"])
def test_lote_considera_texto_html_extraido_uma_leitura_bem_sucedida(tmp_path, provedor):
    numero = "1076539-20.2019.8.26.0100" if provedor == "esaj" else "5060583-19.2021.8.13.0024"
    extrato = {
        "status": "ok",
        "dados_basicos": {},
        "movimentacoes": [],
        "origem": {"movimentacoes_completas": True, "documentos_completos": True},
        "documentos": {
            "publicos_candidatos_unicos": [
                {"cd_documento": "html-1", "titulo": "Peça HTML", "href": "https://tribunal/doc1"}
            ],
            "restritos_por_senha_unicos": [],
        },
    }
    if provedor == "esaj":
        kwargs = {
            "_get_extrato": lambda *_args, **_kwargs: extrato,
            "_read_documents": lambda *_args, **_kwargs: [
                {"cd_documento": "html-1", "status": "texto_html_extraido", "texto": "conteúdo"}
            ],
        }
    else:
        kwargs = {
            "_consultar_pje": lambda _cnj: extrato,
            "_ler_pje": lambda *_args, **_kwargs: {
                "status": "texto_html_extraido",
                "texto": "conteúdo",
            },
        }

    item = next(
        iter_extract_dockets(
            [numero],
            destination=str(tmp_path),
            read_documents=True,
            **kwargs,
        )
    )

    assert item["status"] == "ok"
    assert item["document_statuses"][0]["status"] == "texto_html_extraido"
    assert "warnings" not in item


@pytest.mark.parametrize("provedor", ["esaj", "pje_tjmg"])
@pytest.mark.parametrize(
    "status_leitura", ["pdf_sem_texto_extraido", "pdf_parser_indisponivel", "sessao_expirada"]
)
def test_lote_nao_confunde_pdf_sem_texto_ou_sessao_expirada_com_leitura(
    tmp_path, provedor, status_leitura
):
    numero = "1076539-20.2019.8.26.0100" if provedor == "esaj" else "5060583-19.2021.8.13.0024"
    extrato = {
        "status": "ok",
        "dados_basicos": {},
        "movimentacoes": [],
        "origem": {"movimentacoes_completas": True, "documentos_completos": True},
        "documentos": {
            "publicos_candidatos_unicos": [
                {"cd_documento": "doc-1", "titulo": "Peça", "href": "https://tribunal/doc1"}
            ],
            "restritos_por_senha_unicos": [],
        },
    }
    leitura = {"status": status_leitura, "mensagem": "Leitura de texto não concluída."}
    if provedor == "esaj":
        kwargs = {
            "_get_extrato": lambda *_args, **_kwargs: extrato,
            "_read_documents": lambda *_args, **_kwargs: [{"cd_documento": "doc-1", **leitura}],
        }
    else:
        kwargs = {
            "_consultar_pje": lambda _cnj: extrato,
            "_ler_pje": lambda *_args, **_kwargs: leitura,
        }

    item = next(
        iter_extract_dockets([numero], destination=str(tmp_path), read_documents=True, **kwargs)
    )

    assert item["status"] == "partial"
    assert item["document_statuses"][0]["status"] == status_leitura
    assert item["document_statuses"][0]["message"]


def test_dockets_batch_nao_expoe_url_em_erro_http_de_documento(tmp_path):
    import requests

    numero = "5060583-19.2021.8.13.0024"
    marcador = "https://pje.example/download?ca=segredo-sentinela"
    extrato = {
        "origem": {"movimentacoes_completas": True, "documentos_completos": True},
        "documentos": {
            "publicos_candidatos_unicos": [
                {"cd_documento": "doc-1", "titulo": "Documento", "href": "https://pje/doc1"}
            ]
        },
    }

    def ler(url, *, max_chars):
        raise requests.ConnectionError(f"falha em {marcador}")

    item = next(
        iter_extract_dockets(
            [numero],
            destination=str(tmp_path),
            read_documents=True,
            _consultar_pje=lambda _: extrato,
            _ler_pje=ler,
        )
    )

    assert item["status"] == "partial"
    assert item["document_statuses"][0]["status"] == "error"
    assert item["document_statuses"][0]["message"] == ("Falha HTTP (ConnectionError).")
    assert marcador not in str(item)


def test_dockets_batch_pje_separa_downloads_concluidos_das_falhas(tmp_path):
    numero = "5060583-19.2021.8.13.0024"
    extrato = {
        "status": "ok",
        "dados_basicos": {},
        "movimentacoes": [],
        "origem": {"movimentacoes_completas": True, "documentos_completos": True},
        "documentos": {
            "publicos_candidatos_unicos": [
                {"cd_documento": "doc-1", "titulo": "Indisponível", "href": "https://pje/doc1"},
                {"cd_documento": "doc-2", "titulo": "Obtido", "href": "https://pje/doc2"},
            ]
        },
    }

    def baixar(url, destino):
        if url.endswith("doc1"):
            return {"status": "error", "mensagem": "PDF indisponível"}
        return {"status": "baixado", "arquivo": str(destino), "bytes": 42}

    item = next(
        iter_extract_dockets(
            [numero],
            destination=str(tmp_path),
            max_documents_per_process=2,
            _consultar_pje=lambda _: extrato,
            _baixar_pje=baixar,
        )
    )

    assert item["status"] == "partial"
    assert [documento["cd_documento"] for documento in item["downloaded"]] == ["doc-2"]
    assert [estado["status"] for estado in item["document_statuses"]] == ["error", "baixado"]


def test_client_autos_pje_reutiliza_sessao_entre_consulta_e_download(monkeypatch, tmp_path):
    from nanojud import pje_tjmg
    from nanojud.client import NanoJudClient

    numero = "5060583-19.2021.8.13.0024"
    chamadas = []

    def consultar(cnj, *, session, timeout, prazo_total):
        chamadas.append(("consultar", session, timeout, prazo_total))
        return {
            "status": "ok",
            "dados_basicos": {},
            "movimentacoes": [],
            "origem": {"movimentacoes_completas": True, "documentos_completos": True},
            "documentos": {
                "publicos_candidatos_unicos": [
                    {"cd_documento": "doc-1", "titulo": "Decisão", "href": "https://pje/doc1"}
                ]
            },
        }

    def baixar(url, destino, *, session, timeout, sobrescrever):
        chamadas.append(("baixar", session, timeout))
        return {"status": "baixado", "arquivo": str(destino), "bytes": 20}

    monkeypatch.setattr(pje_tjmg, "consultar_processo", consultar)
    monkeypatch.setattr(pje_tjmg, "baixar_documento_publico", baixar)
    client = NanoJudClient()

    item = next(
        client.iter_extract_dockets(
            [numero], destination=tmp_path, max_documents_per_process=1, timeout=9
        )
    )

    assert item["status"] == "ok"
    assert chamadas == [
        ("consultar", client.session, 9, 60.0),
        ("baixar", client.session, 9),
    ]


def test_client_processa_lote_com_sessao_e_opcoes(monkeypatch):
    from nanojud.client import NanoJudClient
    from nanojud.config import NanoJudConfig

    numero = "1076539-20.2019.8.26.0100"
    client = NanoJudClient(NanoJudConfig(datajud_api_key="config-key"))
    chamadas = []

    def extrair(cnj, **kwargs):
        chamadas.append(kwargs)
        return _envelope(cnj)

    monkeypatch.setattr("nanojud.client.extraction.extract_process", extrair)
    opcoes = {
        "sources": ["datajud"],
        "timeout": 7,
        "limite_movimentacoes": None,
        "datajud_api_key": None,
    }
    itens = list(client.iter_extract_processes([numero], **opcoes))
    resumo = client.extract_processes([numero], **opcoes)

    assert itens[0]["status"] == "ok"
    assert resumo["items"] == itens
    assert len(chamadas) == 2
    assert all(chamada["session"] is client.session for chamada in chamadas)
    assert all(chamada["timeout"] == 7 for chamada in chamadas)
    assert all(chamada["limite_movimentacoes"] is None for chamada in chamadas)
    assert all(chamada["datajud_api_key"] == "config-key" for chamada in chamadas)
