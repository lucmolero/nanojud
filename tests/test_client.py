import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from nanojud.client import NanoJudClient, RateLimitedSession
from nanojud.config import NanoJudConfig
from nanojud.mni import MNI3Config


@pytest.mark.parametrize("timeout", [None, 0, -1, float("nan"), float("inf"), 86401, 1e100, True])
def test_config_rejeita_timeout_de_rede_sem_limite(timeout):
    with pytest.raises(ValueError, match="timeout"):
        NanoJudConfig(timeout=timeout)


@pytest.mark.parametrize("ttl", [-1, True, 1.5, "60"])
def test_config_rejeita_ttl_de_cache_invalido(ttl):
    with pytest.raises(ValueError, match="cache_ttl_seconds"):
        NanoJudConfig(cache_ttl_seconds=ttl)


def _extrato():
    return {
        "status": "ok",
        "origem": {"url_final": "https://example.test"},
        "dados_basicos": {"numero": "1076539-20.2019.8.26.0100", "classe": "Classe"},
        "partes": {
            "principais": [],
            "todas": [],
            "polo_ativo": [],
            "polo_passivo": [],
            "polo_desconhecido": [],
        },
        "movimentacoes": [{"titulo": "Mov", "data": "31/07/2026"}],
        "documentos": {},
    }


def test_client_get_extrato_usa_cache_sem_registrar_cnj(monkeypatch, caplog):
    chamadas = {"count": 0}

    def fake_montar(*args, **kwargs):
        chamadas["count"] += 1
        return _extrato()

    monkeypatch.setattr("nanojud.client.esaj.montar_extrato", fake_montar)
    client = NanoJudClient(
        NanoJudConfig(cache_enabled=True, cache_dir=f".tmp/test-client-cache-{uuid4()}"),
        logger=logging.getLogger("nanojud.cache-test"),
    )

    with caplog.at_level(logging.DEBUG, logger="nanojud.cache-test"):
        primeiro = client.get_extrato("1076539-20.2019.8.26.0100")
        segundo = client.get_extrato("1076539-20.2019.8.26.0100")

    assert primeiro == segundo
    assert chamadas["count"] == 1
    assert "1076539-20.2019.8.26.0100" not in caplog.text


def test_client_cache_distingue_solicitacao_de_salvar_html(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "nanojud.client.esaj.montar_extrato",
        lambda *args, **kwargs: chamadas.append(kwargs["salvar_html"]) or _extrato(),
    )
    client = NanoJudClient(
        NanoJudConfig(cache_enabled=True, cache_dir=f".tmp/test-cache-html-{uuid4()}")
    )

    client.get_extrato("1076539-20.2019.8.26.0100")
    client.get_extrato("1076539-20.2019.8.26.0100", salvar_html=True)
    client.get_extrato("1076539-20.2019.8.26.0100", salvar_html=True)

    assert chamadas == [False, True]


def test_client_search_nao_reusa_extrato_com_movimentacoes_parciais(monkeypatch):
    from nanojud import esaj

    consultas = []
    numero = "1076539-20.2019.8.26.0100"

    def montar(_numero, *, limite_movimentacoes, **kwargs):
        consultas.append(limite_movimentacoes)
        extrato = _extrato()
        extrato["origem"]["movimentacoes_completas"] = limite_movimentacoes is None
        return extrato

    monkeypatch.setattr("nanojud.client.esaj.montar_extrato", montar)
    client = NanoJudClient()

    client.get_extrato(numero, limite_movimentacoes=1)
    client.search_processo(numero)

    assert consultas == [1, esaj.LIMITE_RESUMO]


def test_client_obter_pdf_pje_reutiliza_sessao_e_tempo_limite(monkeypatch):
    from nanojud.client import pje_tjmg

    sessao = object()
    chamadas = []
    cliente = NanoJudClient(
        config=NanoJudConfig(timeout=7),
        session=sessao,
    )
    monkeypatch.setattr(
        pje_tjmg,
        "obter_pdf_publico",
        lambda url, **kwargs: chamadas.append((url, kwargs)) or b"%PDF-1.7",
    )

    conteudo = cliente.obter_pdf_pje_tjmg("url-publica", max_bytes=2048)

    assert conteudo == b"%PDF-1.7"
    assert chamadas == [
        (
            "url-publica",
            {"session": sessao, "timeout": 7, "max_bytes": 2048},
        )
    ]


def test_client_obter_pdf_esaj_seleciona_um_documento_e_limita_saida(monkeypatch, tmp_path):
    numero = "1076539-20.2019.8.26.0100"
    extrato = {
        "origem": {"entrada": numero},
        "documentos": {
            "publicos_candidatos_unicos": [
                {"cd_documento": "123", "titulo": "Inicial"},
                {"cd_documento": "456", "titulo": "Decisão"},
            ],
            "restritos_por_senha_unicos": [],
        },
    }
    chamadas = []
    cliente = NanoJudClient()
    monkeypatch.setattr(
        cliente,
        "get_extrato",
        lambda numero_arg, **kwargs: chamadas.append((numero_arg, kwargs)) or extrato,
    )

    def baixar(extrato_arg, destino, *, limite, max_bytes):
        docs = extrato_arg["documentos"]["publicos_candidatos_unicos"]
        chamadas.append(([doc["cd_documento"] for doc in docs], limite, max_bytes))
        docs[0]["download_status"] = "baixado"
        arquivo = destino / "documento.pdf"
        arquivo.write_bytes(b"%PDF-1.7\npeca")
        return [{"status": "baixado", "arquivo": str(arquivo)}]

    monkeypatch.setattr(cliente, "baixar_pecas", baixar)

    pdf = cliente.obter_pdf_esaj(numero, "456", max_bytes=2048)

    assert pdf == b"%PDF-1.7\npeca"
    assert chamadas == [
        (numero, {"limite_movimentacoes": None, "senha_processo": None}),
        (["456"], 1, 2048),
    ]
    assert "download_status" not in extrato["documentos"]["publicos_candidatos_unicos"][1]


def test_client_obter_pdf_esaj_diferencia_documento_restrito_e_ausente(monkeypatch):
    from nanojud.exceptions import AcessoRestrito, DocumentoNaoEncontrado

    cliente = NanoJudClient()
    monkeypatch.setattr(
        cliente,
        "get_extrato",
        lambda *args, **kwargs: {
            "documentos": {
                "publicos_candidatos_unicos": [],
                "restritos_por_senha_unicos": [{"cd_documento": "restrito"}],
            }
        },
    )

    with pytest.raises(AcessoRestrito):
        cliente.obter_pdf_esaj("1076539-20.2019.8.26.0100", "restrito")
    with pytest.raises(DocumentoNaoEncontrado):
        cliente.obter_pdf_esaj("1076539-20.2019.8.26.0100", "ausente")


def test_client_obter_pdf_esaj_reusa_extrato_completo_e_remove_temporario(monkeypatch):
    numero = "1076539-20.2019.8.26.0100"
    extrato = {
        "origem": {"movimentacoes_completas": True, "entrada": numero},
        "documentos": {
            "publicos_candidatos_unicos": [{"cd_documento": "123", "titulo": "Peça"}],
            "restritos_por_senha_unicos": [],
        },
    }
    caminhos = []
    cliente = NanoJudClient()
    cliente._extratos[numero] = extrato
    monkeypatch.setattr(
        cliente,
        "get_extrato",
        lambda *args, **kwargs: pytest.fail("extrato completo deve ser reutilizado"),
    )

    def baixar(extrato_arg, destino, **kwargs):
        arquivo = destino / "documento.pdf"
        arquivo.write_bytes(b"%PDF-1.7\nconteudo")
        caminhos.append(arquivo)
        return [{"status": "baixado", "arquivo": str(arquivo)}]

    monkeypatch.setattr(cliente, "baixar_pecas", baixar)

    pdf = cliente.obter_pdf_esaj(numero, "123")

    assert pdf == b"%PDF-1.7\nconteudo"
    assert len(caminhos) == 1
    assert not caminhos[0].exists()


def test_client_obter_pdf_esaj_aplica_senha_apos_consulta_publica(monkeypatch):
    numero = "1076539-20.2019.8.26.0100"
    documento = {"cd_documento": "123"}
    pdf = b"%PDF-1.7\nconteudo"
    cliente = NanoJudClient()

    def montar_extrato(*args, senha_processo=None, **kwargs):
        autorizado = senha_processo == "senha-de-teste"
        return {
            "origem": {"movimentacoes_completas": True},
            "documentos": {
                "publicos_candidatos_unicos": [documento] if autorizado else [],
                "restritos_por_senha_unicos": [] if autorizado else [documento],
            },
        }

    def baixar(extrato, destino, **kwargs):
        arquivo = destino / "documento.pdf"
        arquivo.write_bytes(pdf)
        return [{"status": "baixado", "arquivo": str(arquivo)}]

    monkeypatch.setattr("nanojud.client.esaj.montar_extrato", montar_extrato)
    monkeypatch.setattr(cliente, "baixar_pecas", baixar)
    cliente.get_extrato(numero, limite_movimentacoes=None)

    assert cliente.obter_pdf_esaj(numero, "123", senha_processo="senha-de-teste") == pdf


@pytest.mark.parametrize(
    ("status", "conteudo", "tipo_erro", "mensagem"),
    [
        ("sessao_expirada", None, "AcessoRestrito", "recusou o acesso"),
        ("documento_muito_grande", None, "DownloadIndisponivel", "excede o limite"),
        ("erro_http", None, "DownloadIndisponivel", "erro_http"),
        ("baixado", b"<html>Login</html>", "DownloadIndisponivel", "PDF válido"),
        ("baixado", b"%PDF-" + b"x" * 64, "DownloadIndisponivel", "PDF válido"),
    ],
)
def test_client_obter_pdf_esaj_traduz_falhas_do_download(
    monkeypatch, status, conteudo, tipo_erro, mensagem
):
    from nanojud import exceptions

    numero = "1076539-20.2019.8.26.0100"
    cliente = NanoJudClient()
    monkeypatch.setattr(
        "nanojud.client.esaj.montar_extrato",
        lambda *a, **k: {"documentos": {"publicos_candidatos_unicos": [{"cd_documento": "123"}]}},
    )

    def baixar(extrato, destino, **kwargs):
        extrato["documentos"]["publicos_candidatos_unicos"][0]["download_status"] = status
        if conteudo is None:
            return []
        arquivo = destino / "documento.pdf"
        arquivo.write_bytes(conteudo)
        return [{"status": "baixado", "arquivo": str(arquivo)}]

    monkeypatch.setattr(cliente, "baixar_pecas", baixar)

    with pytest.raises(getattr(exceptions, tipo_erro), match=mensagem):
        cliente.obter_pdf_esaj(numero, "123", max_bytes=32)


@pytest.mark.parametrize(
    ("numero", "documento", "limite", "mensagem"),
    [
        ("5060583-19.2021.8.13.0024", "123", 32, "TJSP"),
        ("1076539-20.2019.8.26.0100", " ", 32, "cd_documento"),
        ("1076539-20.2019.8.26.0100", "123", 0, "max_bytes"),
        ("1076539-20.2019.8.26.0100", "123", 1.5, "max_bytes"),
        ("1076539-20.2019.8.26.0100", "123", "32", "max_bytes"),
        ("1076539-20.2019.8.26.0100", "123", None, "max_bytes"),
        ("1076539-20.2019.8.26.0100", "123", True, "max_bytes"),
    ],
)
def test_client_obter_pdf_esaj_rejeita_entrada_invalida_antes_da_consulta(
    monkeypatch, numero, documento, limite, mensagem
):
    monkeypatch.setattr(
        "nanojud.client.esaj.montar_extrato",
        lambda *a, **k: pytest.fail("Entrada inválida não deve consultar o portal"),
    )

    with pytest.raises(ValueError, match=mensagem):
        NanoJudClient().obter_pdf_esaj(numero, documento, max_bytes=limite)


def test_client_get_extrato_define_pasta_de_download(monkeypatch, tmp_path):
    chamadas = {}

    def fake_montar(*args, **kwargs):
        chamadas.update(kwargs)
        return _extrato()

    monkeypatch.setattr("nanojud.client.esaj.montar_extrato", fake_montar)
    pasta = tmp_path / "autos"

    NanoJudClient().get_extrato("1076539-20.2019.8.26.0100", baixar_pecas=True, pasta_pecas=pasta)

    assert chamadas["pasta_pecas"] == pasta


def test_client_search_processo_resume_extrato(monkeypatch):
    monkeypatch.setattr("nanojud.client.esaj.montar_extrato", lambda *a, **k: _extrato())

    resumo = NanoJudClient().search_processo("1076539-20.2019.8.26.0100")

    assert resumo["classe"] == "Classe"
    assert resumo["ultima_movimentacao"] == "Mov"


def test_client_search_processo_usa_movimentacao_mais_recente(monkeypatch):
    extrato = _extrato()
    extrato["movimentacoes"] = [
        {"titulo": "Mais recente", "data": "31/07/2026"},
        {"titulo": "Mais antiga", "data": "01/01/2020"},
    ]
    monkeypatch.setattr("nanojud.client.esaj.montar_extrato", lambda *a, **k: extrato)

    resumo = NanoJudClient().search_processo("1076539-20.2019.8.26.0100")

    assert resumo["ultima_movimentacao"] == "Mais recente"


def test_client_consultar_eproc_tjsp_2g_usa_timeout_configurado(monkeypatch):
    chamadas = []
    esperado = {"status": "partial", "origem": {"grau": "2G"}}
    monkeypatch.setattr(
        "nanojud.client.eproc_tjsp.consultar_processo_2g",
        lambda numero, **kwargs: chamadas.append((numero, kwargs)) or esperado,
    )
    resultado = NanoJudClient(config=NanoJudConfig(timeout=17)).consultar_eproc_tjsp_2g(
        "1001194-30.2024.8.26.0114", aguardar_desafio_interativo=True
    )
    assert resultado == esperado
    assert chamadas == [
        (
            "1001194-30.2024.8.26.0114",
            {
                "timeout": 17,
                "headless": False,
                "aguardar_desafio_interativo": True,
            },
        )
    ]


def test_client_consultar_pje_tjmg_repassa_orcamento_total(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "nanojud.client.pje_tjmg.consultar_processo",
        lambda numero, **kwargs: chamadas.append((numero, kwargs)) or {"status": "ok"},
    )
    cliente = NanoJudClient(config=NanoJudConfig(timeout=11))

    resultado = cliente.consultar_pje_tjmg("5060583-19.2021.8.13.0024", prazo_total=19)

    assert resultado == {"status": "ok"}
    assert chamadas == [
        (
            "5060583-19.2021.8.13.0024",
            {"session": cliente.session, "timeout": 11, "prazo_total": 19},
        )
    ]


def test_client_consultar_tjmg_2g_legado_repassa_sessao_e_timeout(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "nanojud.client.tjmg_legado.consultar_processo",
        lambda numero, identificador, **kwargs: (
            chamadas.append((numero, identificador, kwargs)) or {"status": "partial"}
        ),
    )
    cliente = NanoJudClient(config=NanoJudConfig(timeout=11))
    resultado = cliente.consultar_tjmg_2g_legado("2125575-44.2023.8.13.0000", "10000232125575004")
    assert resultado == {"status": "partial"}
    assert chamadas == [
        (
            "2125575-44.2023.8.13.0000",
            "10000232125575004",
            {"session": cliente.session, "timeout": 11},
        )
    ]


def test_client_obter_documento_tjmg_legado_repassa_sessao_e_limite(monkeypatch):
    chamadas = []
    esperado = (b"word-bytes", "application/msword")
    monkeypatch.setattr(
        "nanojud.client.tjmg_legado.obter_documento_publico",
        lambda *args, **kwargs: chamadas.append((args, kwargs)) or esperado,
    )
    cliente = NanoJudClient(config=NanoJudConfig(timeout=11))
    resultado = cliente.obter_documento_tjmg_2g_legado(
        "2125575-44.2023.8.13.0000", "10000232125575004", "12345", "2024", max_bytes=4096
    )
    assert resultado == esperado
    assert chamadas == [
        (
            ("2125575-44.2023.8.13.0000", "10000232125575004", "12345", "2024"),
            {"session": cliente.session, "timeout": 11, "max_bytes": 4096},
        )
    ]


def test_rate_limited_session_define_user_agent():
    session = RateLimitedSession(
        timeout=10,
        rate_limit_interval=0,
        logger=logging.getLogger("test"),
        user_agent="teste-agent",
    )

    assert session.timeout == 10
    assert session.headers["User-Agent"] == "teste-agent"


def test_client_get_partes(monkeypatch):
    monkeypatch.setattr("nanojud.client.esaj.montar_extrato", lambda *a, **k: _extrato())

    partes = NanoJudClient().get_partes("1076539-20.2019.8.26.0100")

    assert partes["principais"] == []


def test_client_consultar_djen_usa_cache(monkeypatch):
    chamadas = {"count": 0}
    parametros = []

    def fake_consultar(*args, **kwargs):
        chamadas["count"] += 1
        parametros.append(kwargs)
        return {"comunicacoes": [{"id": "1"}], "completo": True}

    monkeypatch.setattr("nanojud.client.djen.consultar_processo_detalhado", fake_consultar)
    client = NanoJudClient(
        NanoJudConfig(timeout=7, cache_enabled=True, cache_dir=f".tmp/test-djen-cache-{uuid4()}")
    )

    primeiro = client.consultar_djen("1076539-20.2019.8.26.0100")
    segundo = client.consultar_djen("1076539-20.2019.8.26.0100")

    assert primeiro == segundo == [{"id": "1"}]
    assert chamadas["count"] == 1
    assert parametros[0]["timeout"] == 7


def test_client_cache_djen_nao_colide_com_delimitadores_de_entrada(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "nanojud.client.djen.consultar_processo_detalhado",
        lambda numero, **kwargs: (
            chamadas.append(kwargs["data_inicio"])
            or {"comunicacoes": [{"inicio": kwargs["data_inicio"]}], "completo": True}
        ),
    )
    client = NanoJudClient(
        NanoJudConfig(cache_enabled=True, cache_dir=f".tmp/test-cache-djen-collision-{uuid4()}")
    )
    numero = "1076539-20.2019.8.26.0100"

    primeira = client.consultar_djen(numero, "x|data_inicio=2020-01-01")
    segunda = client.consultar_djen(f"{numero}|data_inicio=x", "2020-01-01")

    assert primeira == [{"inicio": "x|data_inicio=2020-01-01"}]
    assert segunda == [{"inicio": "2020-01-01"}]
    assert chamadas == ["x|data_inicio=2020-01-01", "2020-01-01"]


def test_client_djen_parcial_nao_e_guardado_como_resultado_completo(monkeypatch, tmp_path):
    chamadas = []

    def consulta(numero, **kwargs):
        chamadas.append(numero)
        return {"comunicacoes": [{"id": str(len(chamadas))}], "completo": False}

    monkeypatch.setattr("nanojud.client.djen.consultar_processo_detalhado", consulta)
    client = NanoJudClient(NanoJudConfig(cache_enabled=True, cache_dir=str(tmp_path)))

    primeiro = client.consultar_djen("1076539-20.2019.8.26.0100")
    segundo = client.consultar_djen("1076539-20.2019.8.26.0100")

    assert primeiro == [{"id": "1"}]
    assert segundo == [{"id": "2"}]


def test_client_consultar_datajud_usa_cache(monkeypatch):
    chamadas = {"count": 0, "prazo_total": None}

    def fake_consultar(*args, **kwargs):
        chamadas["count"] += 1
        chamadas["prazo_total"] = kwargs["prazo_total"]
        return {"status": "ok", "numero_cnj": args[0]}

    monkeypatch.setattr("nanojud.client.datajud.consultar_processo", fake_consultar)
    client = NanoJudClient(
        NanoJudConfig(cache_enabled=True, cache_dir=f".tmp/test-datajud-cache-{uuid4()}")
    )

    primeiro = client.consultar_datajud("1076539-20.2019.8.26.0100", api_key="abc", prazo_total=17)
    segundo = client.consultar_datajud("1076539-20.2019.8.26.0100", api_key="abc")

    assert primeiro == segundo
    assert chamadas["count"] == 1
    assert chamadas["prazo_total"] == 17


def test_client_nao_armazena_resultado_datajud_parcial(monkeypatch):
    chamadas = {"count": 0}

    def fake_consultar(*args, **kwargs):
        chamadas["count"] += 1
        return {"status": "partial", "numero_cnj": args[0]}

    monkeypatch.setattr("nanojud.client.datajud.consultar_processo", fake_consultar)
    client = NanoJudClient(
        NanoJudConfig(cache_enabled=True, cache_dir=f".tmp/test-datajud-partial-{uuid4()}")
    )

    client.consultar_datajud("1076539-20.2019.8.26.0100")
    client.consultar_datajud("1076539-20.2019.8.26.0100", prazo_total=120)

    assert chamadas["count"] == 2


def test_client_extract_process_delega(monkeypatch):
    chamadas = {}

    def fake_extract(numero, **kwargs):
        chamadas["numero"] = numero
        chamadas.update(kwargs)
        return {"status": "ok", "timeline": []}

    monkeypatch.setattr("nanojud.client.extraction.extract_process", fake_extract)
    client = NanoJudClient(NanoJudConfig(datajud_api_key="abc"))

    resultado = client.extract_process("1076539-20.2019.8.26.0100", sources=("datajud",))

    assert resultado["status"] == "ok"
    assert chamadas["datajud_api_key"] == "abc"

    client.extract_process(
        "1076539-20.2019.8.26.0100", sources=("datajud",), datajud_api_key="override"
    )
    assert chamadas["datajud_api_key"] == "override"


def test_client_baixar_pecas_delega(monkeypatch):
    from nanojud import esaj

    chamadas = {}

    def fake_baixar(session, movimentos, destino, limite, sobrescrever, *, max_bytes, timeout):
        chamadas["movimentos"] = movimentos
        chamadas["limite"] = limite
        chamadas["sobrescrever"] = sobrescrever
        chamadas["max_bytes"] = max_bytes
        chamadas["timeout"] = timeout
        return [{"status": "baixado"}]

    monkeypatch.setattr("nanojud.client.esaj.baixar_pecas_publicas", fake_baixar)
    client = NanoJudClient(NanoJudConfig(timeout=7))

    resultado = client.baixar_pecas(
        {"documentos": {"publicos_candidatos_unicos": [{"cd_documento": "1"}]}},
        destino=__import__("pathlib").Path("pecas"),
        sobrescrever=True,
        limite=1,
    )

    assert resultado == [{"status": "baixado"}]
    assert chamadas["movimentos"][0]["documentos"][0]["cd_documento"] == "1"
    assert chamadas["sobrescrever"] is True
    assert chamadas["max_bytes"] == esaj.MAX_DOCUMENT_DOWNLOAD_BYTES
    assert chamadas["timeout"] == 7


def test_client_ler_pecas_delega(monkeypatch):
    chamadas = {}

    def fake_ler(session, movimentos, limite, max_chars, *, timeout):
        chamadas["movimentos"] = movimentos
        chamadas["limite"] = limite
        chamadas["max_chars"] = max_chars
        chamadas["timeout"] = timeout
        return [{"status": "texto_extraido"}]

    monkeypatch.setattr("nanojud.client.esaj.ler_pecas_publicas", fake_ler)
    client = NanoJudClient(NanoJudConfig(timeout=7))

    resultado = client.ler_pecas(
        {"documentos": {"publicos_candidatos_unicos": [{"cd_documento": "1"}]}},
        limite=2,
        max_chars=500,
    )

    assert resultado == [{"status": "texto_extraido"}]
    assert chamadas["movimentos"][0]["documentos"][0]["cd_documento"] == "1"
    assert chamadas["max_chars"] == 500
    assert chamadas["timeout"] == 7


def test_rate_limited_session_request_usa_timeout(monkeypatch):
    chamadas = {}

    def fake_request(self, method, url, **kwargs):
        chamadas["method"] = method
        chamadas["url"] = url
        chamadas["timeout"] = kwargs["timeout"]
        return type("Response", (), {"status_code": 200})()

    monkeypatch.setattr("requests.Session.request", fake_request)
    session = RateLimitedSession(
        timeout=7,
        rate_limit_interval=0,
        logger=logging.getLogger("test"),
        user_agent="agent",
    )

    response = session.request("GET", "https://example.test")

    assert response.status_code == 200
    assert chamadas["timeout"] == 7


def test_rate_limited_session_nao_registra_caminho_ou_query(monkeypatch, caplog):
    monkeypatch.setattr(
        "requests.Session.request",
        lambda self, method, url, **kwargs: type("Response", (), {"status_code": 200})(),
    )
    logger = logging.getLogger("nanojud.http-private-test")
    session = RateLimitedSession(
        timeout=7,
        rate_limit_interval=0,
        logger=logger,
        user_agent="agent",
    )
    numero = "1076539-20.2019.8.26.0100"
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.numero={numero}&token=private"

    with caplog.at_level(logging.DEBUG, logger="nanojud.http-private-test"):
        session.request("GET", url)

    assert "esaj.tjsp.jus.br" in caplog.text
    assert "cpopg/show.do" not in caplog.text
    assert numero not in caplog.text
    assert "token=private" not in caplog.text


def test_rate_limited_session_aguarda_intervalo(monkeypatch):
    sleeps = []
    tempos = iter([10.2])
    monkeypatch.setattr("nanojud.client.time.monotonic", lambda: next(tempos))
    monkeypatch.setattr("nanojud.client.time.sleep", lambda segundos: sleeps.append(segundos))
    session = RateLimitedSession(
        timeout=7,
        rate_limit_interval=1.0,
        logger=logging.getLogger("test"),
        user_agent="agent",
    )
    session._last_request_at_by_origin["https://example.test"] = 10.0

    session._wait_if_needed("https://example.test")

    assert sleeps[0] == pytest.approx(0.8)


def test_rate_limited_session_aguarda_apos_erro_de_rede(monkeypatch):
    import requests

    sleeps = []
    tempos = iter([1.5, 2.0, 2.5, 3.0])
    chamadas = []
    monkeypatch.setattr("nanojud.client.time.monotonic", lambda: next(tempos))
    monkeypatch.setattr("nanojud.client.time.sleep", lambda segundos: sleeps.append(segundos))

    def falha_e_depois_responde(self, method, url, **kwargs):
        chamadas.append(url)
        if len(chamadas) == 1:
            raise requests.ConnectionError("conexão encerrada")
        return type("Response", (), {"status_code": 200})()

    monkeypatch.setattr("requests.Session.request", falha_e_depois_responde)
    session = RateLimitedSession(
        timeout=7,
        rate_limit_interval=1.0,
        logger=logging.getLogger("test"),
        user_agent="agent",
    )
    session._last_request_at_by_origin["https://example.test"] = 1.0

    with pytest.raises(requests.ConnectionError):
        session.request("GET", "https://example.test/first")
    response = session.request("GET", "https://example.test/second")

    assert response.status_code == 200
    assert chamadas == ["https://example.test/first", "https://example.test/second"]
    assert sleeps == pytest.approx([0.5, 0.5])


def test_rate_limited_session_serializa_requisicoes_ao_mesmo_host(monkeypatch):
    primeira_iniciada = threading.Event()
    segunda_iniciada = threading.Event()
    liberar_primeira = threading.Event()
    active = 0
    max_active = 0
    active_lock = threading.Lock()

    def fake_request(self, method, url, **kwargs):
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            if url.endswith("/first"):
                primeira_iniciada.set()
                assert liberar_primeira.wait(timeout=2)
            else:
                segunda_iniciada.set()
            return type("Response", (), {"status_code": 200})()
        finally:
            with active_lock:
                active -= 1

    monkeypatch.setattr("requests.Session.request", fake_request)
    session = RateLimitedSession(
        timeout=7,
        rate_limit_interval=0,
        logger=logging.getLogger("test"),
        user_agent="agent",
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        primeira = pool.submit(session.request, "GET", "https://example.test/first")
        assert primeira_iniciada.wait(timeout=1)
        segunda = pool.submit(session.request, "GET", "https://example.test/second")
        try:
            assert not segunda_iniciada.wait(timeout=0.05)
        finally:
            liberar_primeira.set()
        assert primeira.result().status_code == 200
        assert segunda.result().status_code == 200

    assert max_active == 1


def test_rate_limited_session_nao_bloqueia_hosts_independentes(monkeypatch):
    primeira_iniciada = threading.Event()
    liberar_primeira = threading.Event()

    def fake_request(self, method, url, **kwargs):
        if "primeiro.test" in url:
            primeira_iniciada.set()
            assert liberar_primeira.wait(timeout=2)
        return type("Response", (), {"status_code": 200})()

    monkeypatch.setattr("requests.Session.request", fake_request)
    session = RateLimitedSession(
        timeout=7,
        rate_limit_interval=0,
        logger=logging.getLogger("test"),
        user_agent="agent",
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        primeira = pool.submit(session.request, "GET", "https://primeiro.test/first")
        assert primeira_iniciada.wait(timeout=1)
        try:
            segunda = pool.submit(session.request, "GET", "https://segundo.test/second")
            assert segunda.result(timeout=1).status_code == 200
        finally:
            liberar_primeira.set()
        assert primeira.result().status_code == 200


def test_rate_limited_session_aplica_intervalo_por_host(monkeypatch):
    sleeps = []
    monkeypatch.setattr("nanojud.client.time.monotonic", lambda: 10.0)
    monkeypatch.setattr("nanojud.client.time.sleep", sleeps.append)
    monkeypatch.setattr(
        "requests.Session.request",
        lambda self, method, url, **kwargs: type("Response", (), {"status_code": 200})(),
    )
    session = RateLimitedSession(
        timeout=7,
        rate_limit_interval=2.0,
        logger=logging.getLogger("test"),
        user_agent="agent",
    )

    session.request("GET", "https://primeiro.test/1")
    session.request("GET", "https://primeiro.test/2")
    session.request("GET", "https://segundo.test/1")

    assert sleeps == [2.0]


def test_client_baixar_pecas_usa_movimentacoes_quando_sem_documentos(monkeypatch):
    chamadas = {}

    def fake_baixar(session, movimentos, destino, limite, sobrescrever, **kwargs):
        chamadas["movimentos"] = movimentos
        return []

    monkeypatch.setattr("nanojud.client.esaj.baixar_pecas_publicas", fake_baixar)
    extrato = {"documentos": {}, "movimentacoes": [{"documentos": []}]}

    NanoJudClient().baixar_pecas(extrato, destino=__import__("pathlib").Path("pecas"))

    assert chamadas["movimentos"] == [{"documentos": []}]


def test_client_extract_process_repassa_configuracao_mni(monkeypatch):
    config = MNI3Config(endpoint="https://mni.example/Servico", token="token")
    chamadas = {}

    def fake_extract(numero, **kwargs):
        chamadas.update(numero=numero, **kwargs)
        return {"status": "ok"}

    monkeypatch.setattr("nanojud.client.extraction.extract_process", fake_extract)
    client = NanoJudClient(NanoJudConfig(mni_config=config))

    client.extract_process("1001194-30.2024.8.26.0114", sources=("mni",))

    assert chamadas["mni_config"] is config
    assert chamadas["sources"] == ("mni",)
