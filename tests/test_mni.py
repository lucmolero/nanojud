from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import FrozenInstanceError

import pytest
import requests

from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel, FormatoCNJInvalido
from nanojud.mni import MNI3Client, MNI3Config

CNJ = "1001194-30.2024.8.26.0114"
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
MNI = "http://www.cnj.jus.br/mni/v300/"
TIPOS = "http://www.cnj.jus.br/mni/v300/tipos-servico-intercomunicacao"
INTERCOMUNICACAO = "http://www.cnj.jus.br/mni/v300/intercomunicacao"


class FakeResponse:
    def __init__(self, body: bytes, status_code: int = 200, *, chunks=None) -> None:
        self.body = body
        self.status_code = status_code
        self.chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size: int = 1):
        if self.chunks is None:
            yield self.body
        else:
            yield from self.chunks

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(
        self, response: FakeResponse | None = None, *, error: Exception | None = None
    ) -> None:
        self.response = response or FakeResponse(
            f"""<soap:Envelope xmlns:soap="{SOAP}" xmlns:tic="{MNI}" xmlns:tpi="{TIPOS}">
              <soap:Body><tic:respostaConsultarProcesso>
                <tpi:recibo>
                  <tpi:sucesso>true</tpi:sucesso>
                  <tpi:mensagem>Consulta concluída</tpi:mensagem>
                </tpi:recibo>
                <tpi:processo><tpi:dadosBasicos><tpi:numeroProcesso>10011943020248260114</tpi:numeroProcesso></tpi:dadosBasicos>
                  <tpi:movimento dataHora="2026-11-12T10:00:00-03:00">
                    <tpi:descricao>Distribuído</tpi:descricao>
                  </tpi:movimento>
                </tpi:processo>
              </tic:respostaConsultarProcesso></soap:Body></soap:Envelope>""".encode()
        )
        self.error = error
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        return self.response

    def close(self) -> None:
        self.closed = True


def _requisicao_enviada(session: FakeSession) -> ET.Element:
    payload = session.calls[0]["data"]
    assert isinstance(payload, bytes)
    envelope = ET.fromstring(payload)
    body = envelope.find(f"{{{SOAP}}}Body")
    assert body is not None and len(body) == 1
    return body[0]


def _resposta_documentos_mni(
    *, sucesso: str = "true", mensagem: str = "Documentos consultados", id_documento: str = "doc-1"
) -> bytes:
    return f"""<soap:Envelope xmlns:soap="{SOAP}" xmlns:tic="{MNI}" xmlns:tpi="{TIPOS}">
      <soap:Body><tic:respostaConsultarDocumentosProcesso>
        <tpi:recibo><tpi:sucesso>{sucesso}</tpi:sucesso><tpi:mensagens>
          <tpi:descritivo>{mensagem}</tpi:descritivo>
        </tpi:mensagens></tpi:recibo>
        <tpi:documentos><tpi:idDocumento>{id_documento}</tpi:idDocumento>
          <tpi:conteudo>JVBERg==</tpi:conteudo></tpi:documentos>
      </tic:respostaConsultarDocumentosProcesso></soap:Body></soap:Envelope>""".encode()


def test_config_requer_endpoint_https_e_uma_autenticacao():
    with pytest.raises(ValueError, match="HTTPS"):
        MNI3Config(endpoint="http://mni.tj.example/Servico", usuario="u", senha="s")
    with pytest.raises(ValueError, match="Informe token ou usuario/senha"):
        MNI3Config(endpoint="https://mni.tj.example/Servico")
    with pytest.raises(ValueError, match="exclusivamente"):
        MNI3Config(
            endpoint="https://mni.tj.example/Servico",
            token="segredo-token",
            usuario="usuario",
            senha="segredo-senha",
        )
    with pytest.raises(ValueError, match="query"):
        MNI3Config(endpoint="https://mni.tj.example/Servico?token=secret", token="token")
    with pytest.raises(ValueError, match="TLS não pode ser desativada"):
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="t", verify_tls=False)
    with pytest.raises(ValueError, match="verify_tls"):
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="t", verify_tls=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="max_response_bytes"):
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="t", max_response_bytes=0)
    with pytest.raises(ValueError, match="pessoa_vinculada"):
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="t", pessoa_vinculada="123")


def test_config_oculta_segredos_do_repr_e_e_imutavel():
    config = MNI3Config(
        endpoint="https://mni.tj.example/Servico",
        usuario="usuario-sentinela",
        senha="senha-sentinela",
    )
    assert "sentinela" not in repr(config)
    assert "mni.tj.example" not in repr(config)
    with pytest.raises(FrozenInstanceError):
        config.senha = "outra"  # type: ignore[misc]


def test_config_from_env_is_opcional_e_oculta_credencial(monkeypatch):
    variaveis = (
        "ENDPOINT",
        "TOKEN",
        "USERNAME",
        "PASSWORD",
        "PESSOA_VINCULADA",
        "TRIBUNAL",
        "GRAU",
        "MOVIMENTACOES_COMPLETAS",
    )
    for nome in variaveis:
        monkeypatch.delenv(f"NANOJUD_MNI_{nome}", raising=False)
    assert MNI3Config.from_env() is None

    monkeypatch.setenv("NANOJUD_MNI_ENDPOINT", "https://mni.tj.example/Servico")
    monkeypatch.setenv("NANOJUD_MNI_TOKEN", "token-sentinela")
    monkeypatch.setenv("NANOJUD_MNI_TRIBUNAL", "TJSP")
    monkeypatch.setenv("NANOJUD_MNI_GRAU", "1G")
    monkeypatch.setenv("NANOJUD_MNI_MOVIMENTACOES_COMPLETAS", "true")
    config = MNI3Config.from_env()

    assert config is not None
    assert config.tribunal == "TJSP"
    assert config.grau == "1G"
    assert config.movimentacoes_completas is True
    assert "token-sentinela" not in repr(config)


def test_config_from_env_rejeita_booleano_operacional_ambiguo(monkeypatch):
    monkeypatch.setenv("NANOJUD_MNI_ENDPOINT", "https://mni.tj.example/Servico")
    monkeypatch.setenv("NANOJUD_MNI_TOKEN", "token")
    monkeypatch.setenv("NANOJUD_MNI_MOVIMENTACOES_COMPLETAS", "sim")

    with pytest.raises(ValueError, match="deve ser true ou false"):
        MNI3Config.from_env()


def test_cliente_fecha_somente_sessao_que_ele_criou(monkeypatch):
    propria = FakeSession()
    monkeypatch.setattr(requests, "Session", lambda: propria)
    config = MNI3Config(endpoint="https://mni.tj.example/Servico", token="token")
    cliente_proprio = MNI3Client(config)
    cliente_proprio.close()
    assert propria.closed

    fornecida = FakeSession()
    with MNI3Client(config, session=fornecida) as cliente_injetado:  # type: ignore[arg-type]
        assert cliente_injetado.session is fornecida
    assert not fornecida.closed


def test_consultar_processo_envia_soap_mni_e_converte_resposta():
    session = FakeSession()
    client = MNI3Client(
        MNI3Config(
            endpoint="https://mni.tj.example/Servico",
            usuario="usuario",
            senha="senha",
        ),
        session=session,  # type: ignore[arg-type]
    )

    resultado = client.consultar_processo(CNJ)

    chamada = session.calls[0]
    assert chamada["url"] == "https://mni.tj.example/Servico"
    headers = chamada["headers"]
    assert isinstance(headers, dict)
    assert headers["SOAPAction"] == f'"{MNI}consultarProcesso"'
    assert chamada["allow_redirects"] is False
    assert chamada["verify"] is True
    assert chamada["timeout"] == 30.0
    requisicao = _requisicao_enviada(session)
    assert requisicao.tag == f"{{{MNI}}}requisicaoConsultarProcesso"
    assert requisicao.findtext(f"{{{TIPOS}}}numeroProcesso") == "10011943020248260114"
    assert (
        requisicao.findtext(
            f"{{{TIPOS}}}consultante/{{{INTERCOMUNICACAO}}}"
            f"autenticacaoSimples/{{{INTERCOMUNICACAO}}}usuario"
        )
        == "usuario"
    )
    assert (
        requisicao.findtext(
            f"{{{TIPOS}}}consultante/{{{INTERCOMUNICACAO}}}"
            f"autenticacaoSimples/{{{INTERCOMUNICACAO}}}senha"
        )
        == "senha"
    )
    assert requisicao.findtext(f"{{{TIPOS}}}incluirMovimentos") == "true"
    assert resultado["processo"]["dadosBasicos"]["numeroProcesso"] == "10011943020248260114"
    movimento = resultado["processo"]["movimento"]
    assert movimento["@dataHora"] == "2026-11-12T10:00:00-03:00"
    assert movimento["descricao"] == "Distribuído"


def test_consultar_processo_aceita_token_e_parametros_de_inclusao():
    session = FakeSession()
    client = MNI3Client(
        MNI3Config(
            endpoint="https://mni.tj.example/Servico",
            token="token-secreto",
            pessoa_vinculada="12345678901",
        ),
        session=session,  # type: ignore[arg-type]
    )

    client.consultar_processo(
        CNJ,
        incluir_cabecalho=False,
        incluir_partes=False,
        incluir_enderecos=False,
        incluir_movimentos=False,
        incluir_documentos=True,
    )

    requisicao = _requisicao_enviada(session)
    assert (
        requisicao.findtext(f"{{{TIPOS}}}consultante/{{{INTERCOMUNICACAO}}}token")
        == "token-secreto"
    )
    assert requisicao.findtext(f"{{{TIPOS}}}incluirCabecalho") == "false"
    assert requisicao.findtext(f"{{{TIPOS}}}incluirDocumentos") == "true"
    assert (
        requisicao.find(f"{{{TIPOS}}}consultante/{{{INTERCOMUNICACAO}}}autenticacaoSimples") is None
    )
    assert (
        requisicao.findtext(f"{{{TIPOS}}}consultante/{{{INTERCOMUNICACAO}}}pessoaVinculada")
        == "12345678901"
    )


def test_consultar_documentos_processos_envia_todos_os_ids():
    session = FakeSession(FakeResponse(_resposta_documentos_mni()))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )

    resultado = client.consultar_documentos_processo(CNJ, ["doc-1", "doc-2"])

    requisicao = _requisicao_enviada(session)
    assert [item.text for item in requisicao.findall(f"{{{TIPOS}}}idDocumento")] == [
        "doc-1",
        "doc-2",
    ]
    assert resultado["documentos"]["conteudo"] == "JVBERg=="


def test_consultar_documentos_classifica_recibo_de_acesso_restrito():
    session = FakeSession(
        FakeResponse(_resposta_documentos_mni(sucesso="false", mensagem="Segredo de justiça"))
    )
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )

    with pytest.raises(AcessoRestrito):
        client.consultar_documentos_processo(CNJ, ["doc-1"])


def test_consultar_documentos_rejeita_id_nao_solicitado():
    session = FakeSession(FakeResponse(_resposta_documentos_mni(id_documento="doc-alheio")))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )

    with pytest.raises(ConsultaIndisponivel, match="identificador de documento inesperado"):
        client.consultar_documentos_processo(CNJ, ["doc-1"])


def test_consultar_documentos_rejeita_documento_sem_id():
    session = FakeSession(FakeResponse(_resposta_documentos_mni(id_documento="")))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )

    with pytest.raises(ConsultaIndisponivel, match="documento sem identificador"):
        client.consultar_documentos_processo(CNJ, ["doc-1"])


def test_consultar_documentos_rejeita_recibo_sem_indicador_de_sucesso():
    body = _resposta_documentos_mni().replace(b"<tpi:sucesso>true</tpi:sucesso>", b"")
    session = FakeSession(FakeResponse(body))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )

    with pytest.raises(ConsultaIndisponivel, match="recibo MNI inválido"):
        client.consultar_documentos_processo(CNJ, ["doc-1"])


def test_rejeita_cnj_invalido_antes_de_enviar():
    session = FakeSession()
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(FormatoCNJInvalido):
        client.consultar_processo("111")
    assert session.calls == []


def test_rejeita_opcoes_nao_booleanas_antes_de_enviar():
    session = FakeSession()
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="booleanas"):
        client.consultar_processo(CNJ, incluir_documentos="sim")  # type: ignore[arg-type]
    assert session.calls == []


def test_identifica_autenticacao_recusada_sem_expor_corpo():
    session = FakeSession(FakeResponse(b"credencial-sentinela", status_code=403))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token-sentinela"),
        session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(AcessoRestrito) as erro:
        client.consultar_processo(CNJ)
    assert "sentinela" not in str(erro.value)
    assert session.response.closed


def test_falha_soap_e_xml_invalido_sao_sanitizados():
    for body in (
        f"""<soap:Envelope xmlns:soap="{SOAP}"><soap:Body><soap:Fault>
          <faultcode>soap:Server</faultcode><faultstring>segredo-sentinela</faultstring>
        </soap:Fault></soap:Body></soap:Envelope>""".encode(),
        b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///secret'>]><x>&e;</x>",
    ):
        client = MNI3Client(
            MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
            session=FakeSession(FakeResponse(body)),  # type: ignore[arg-type]
        )
        with pytest.raises(ConsultaIndisponivel) as erro:
            client.consultar_processo(CNJ)
        assert "sentinela" not in str(erro.value)
        assert "secret" not in str(erro.value)


def test_limita_resposta_soap_e_valida_ids_de_documento():
    session = FakeSession(FakeResponse(b"x" * 100))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token", max_response_bytes=20),
        session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(ConsultaIndisponivel, match="limite de tamanho"):
        client.consultar_processo(CNJ)
    with pytest.raises(ValueError, match="pelo menos um identificador"):
        client.consultar_documentos_processo(CNJ, [])
    with pytest.raises(ValueError, match="coleção de identificadores"):
        client.consultar_documentos_processo(CNJ, "doc-1")
    with pytest.raises(ValueError, match="texto não vazio"):
        client.consultar_documentos_processo(CNJ, [""])
    assert session.response.closed


def test_normaliza_resposta_http_invalida_e_sem_expor_payload():
    for status in (302, 500):
        session = FakeSession(FakeResponse(b"body-sentinela", status_code=status))
        client = MNI3Client(
            MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
            session=session,  # type: ignore[arg-type]
        )
        with pytest.raises(ConsultaIndisponivel) as erro:
            client.consultar_processo(CNJ)
        assert "sentinela" not in str(erro.value)
        assert session.response.closed


def test_classifica_falha_de_rede_e_de_stream_sem_vazar_segredos():
    session = FakeSession(error=requests.ConnectionError("senha-sentinela"))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(ConsultaIndisponivel) as erro:
        client.consultar_processo(CNJ)
    assert "sentinela" not in str(erro.value)

    class StreamQueFalha(FakeResponse):
        def iter_content(self, chunk_size: int = 1):
            raise requests.ConnectionError("senha-sentinela")
            yield b""  # pragma: no cover - mantém a função como gerador.

    session = FakeSession(StreamQueFalha(b""))
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=session,  # type: ignore[arg-type]
    )
    with pytest.raises(ConsultaIndisponivel) as erro:
        client.consultar_processo(CNJ)
    assert "sentinela" not in str(erro.value)
    assert session.response.closed


def test_classifica_xml_soap_com_corpo_inesperado():
    for body in (
        b"<not-soap/>",
        f'<soap:Envelope xmlns:soap="{SOAP}"><soap:Body/></soap:Envelope>'.encode(),
        f"""<soap:Envelope xmlns:soap="{SOAP}" xmlns:tic="{MNI}">
          <soap:Body><tic:respostaErrada/></soap:Body></soap:Envelope>""".encode(),
        f"""<soap:Envelope xmlns:soap="{SOAP}" xmlns:alt="urn:outro-namespace">
          <soap:Body><alt:respostaConsultarProcesso/></soap:Body></soap:Envelope>""".encode(),
    ):
        client = MNI3Client(
            MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
            session=FakeSession(FakeResponse(body)),  # type: ignore[arg-type]
        )
        with pytest.raises(
            ConsultaIndisponivel, match="resposta SOAP inesperada|operação diferente"
        ):
            client.consultar_processo(CNJ)


def test_conversor_preserva_nos_repetidos_texto_e_atributos():
    body = f"""<soap:Envelope xmlns:soap="{SOAP}" xmlns:tic="{MNI}" xmlns:tpi="{TIPOS}">
      <soap:Body><tic:respostaConsultarProcesso><tpi:processo>
        <tpi:parte id="p1">Parte A</tpi:parte><tpi:parte id="p2">Parte B</tpi:parte>
      </tpi:processo></tic:respostaConsultarProcesso></soap:Body></soap:Envelope>""".encode()
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.tj.example/Servico", token="token"),
        session=FakeSession(FakeResponse(body)),  # type: ignore[arg-type]
    )

    resultado = client.consultar_processo(CNJ)

    assert resultado["processo"]["parte"] == [
        {"@id": "p1", "#text": "Parte A"},
        {"@id": "p2", "#text": "Parte B"},
    ]
