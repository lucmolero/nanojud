"""Contrato do cliente SOAP MNI 2.2.2 publicado por instalações como o TJRJ."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
import requests

from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel, FormatoCNJInvalido
from nanojud.mni_222 import (
    INTERCOMUNICACAO_222_NAMESPACE,
    SERVICE_222_NAMESPACE,
    TYPES_222_NAMESPACE,
    MNI222Client,
    MNI222Config,
    configuracao_mni_desde_env,
)

CNJ = "1001194-30.2024.8.26.0114"
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"


class Response:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.closed = False

    def iter_content(self, chunk_size=1):
        yield self.content

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def close(self):
        self.closed = True


def config(**kwargs):
    return MNI222Config(
        endpoint="https://www12.tjrj.jus.br/MNI/Servico.svc",
        usuario="12345678901",
        senha="senha-secreta",
        **kwargs,
    )


def soap_response(*, sucesso="true", mensagem="Consulta concluída", processo=True):
    envelope = ET.Element(f"{{{SOAP}}}Envelope")
    body = ET.SubElement(envelope, f"{{{SOAP}}}Body")
    root = ET.SubElement(body, f"{{{SERVICE_222_NAMESPACE}}}consultarProcessoResposta")
    ET.SubElement(root, f"{{{TYPES_222_NAMESPACE}}}sucesso").text = sucesso
    ET.SubElement(root, f"{{{TYPES_222_NAMESPACE}}}mensagem").text = mensagem
    if processo:
        proc = ET.SubElement(root, f"{{{INTERCOMUNICACAO_222_NAMESPACE}}}processo")
        basic = ET.SubElement(proc, f"{{{INTERCOMUNICACAO_222_NAMESPACE}}}dadosBasicos")
        basic.set("numero", "10011943020248260114")
        basic.set("classeProcessual", "7")
        basic.set("codigoLocalidade", "1001")
        basic.set("nivelSigilo", "0")
        movement = ET.SubElement(proc, f"{{{INTERCOMUNICACAO_222_NAMESPACE}}}movimento")
        movement.set("dataHora", "2026-11-12T10:00:00-03:00")
        ET.SubElement(
            movement, f"{{{INTERCOMUNICACAO_222_NAMESPACE}}}complemento"
        ).text = "Distribuído"
        document = ET.SubElement(proc, f"{{{INTERCOMUNICACAO_222_NAMESPACE}}}documento")
        document.set("idDocumento", "doc-1")
        document.set("tipoDocumento", "PETICAO")
        document.set("nivelSigilo", "0")
        ET.SubElement(document, f"{{{INTERCOMUNICACAO_222_NAMESPACE}}}conteudo").text = "UEZERg=="
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def test_config_222_validates_endpoint_and_hides_credentials():
    cfg = config()
    assert "senha-secreta" not in repr(cfg)
    assert "12345678901" not in repr(cfg)
    with pytest.raises(ValueError, match="HTTPS"):
        MNI222Config(endpoint="http://mni.example/Servico", usuario="u", senha="s")
    with pytest.raises(ValueError, match="senhaConsultante"):
        MNI222Config(endpoint="https://mni.example/Servico", usuario="u", senha="")
    with pytest.raises(ValueError, match="TLS"):
        MNI222Config(
            endpoint="https://mni.example/Servico", usuario="u", senha="s", verify_tls=False
        )


def test_configuracao_mni_do_ambiente_seleciona_versao_explicitamente(monkeypatch):
    monkeypatch.setenv("NANOJUD_MNI_VERSION", "2.2.2")
    monkeypatch.setenv("NANOJUD_MNI_ENDPOINT", "https://mni.example/Servico")
    monkeypatch.setenv("NANOJUD_MNI_USERNAME", "id-consultante")
    monkeypatch.setenv("NANOJUD_MNI_PASSWORD", "senha")
    configuracao = configuracao_mni_desde_env()
    assert isinstance(configuracao, MNI222Config)
    assert configuracao.usuario == "id-consultante"

    monkeypatch.setenv("NANOJUD_MNI_VERSION", "3.0")
    monkeypatch.delenv("NANOJUD_MNI_USERNAME")
    monkeypatch.delenv("NANOJUD_MNI_PASSWORD")
    monkeypatch.setenv("NANOJUD_MNI_TOKEN", "token")
    assert not isinstance(configuracao_mni_desde_env(), MNI222Config)

    monkeypatch.setenv("NANOJUD_MNI_VERSION", "2.1")
    with pytest.raises(ValueError, match="VERSION"):
        configuracao_mni_desde_env()


def test_config_222_nao_aceita_token_do_mni_30(monkeypatch):
    monkeypatch.setenv("NANOJUD_MNI_ENDPOINT", "https://mni.example/Servico")
    monkeypatch.setenv("NANOJUD_MNI_TOKEN", "token-v3")
    with pytest.raises(ValueError, match="TOKEN"):
        MNI222Config.from_env()


def test_config_v3_nao_interpreta_ambiente_versionado_como_222(monkeypatch):
    from nanojud.mni import MNI3Config

    monkeypatch.setenv("NANOJUD_MNI_VERSION", "2.2.2")
    monkeypatch.setenv("NANOJUD_MNI_ENDPOINT", "https://mni.example/Servico")
    monkeypatch.setenv("NANOJUD_MNI_USERNAME", "id-consultante")
    monkeypatch.setenv("NANOJUD_MNI_PASSWORD", "senha")
    with pytest.raises(ValueError, match="configuracao_mni_desde_env"):
        MNI3Config.from_env()


@pytest.mark.parametrize(
    ("kwargs", "mensagem"),
    [
        ({"usuario": " "}, "usuario/idConsultante"),
        ({"senha": None}, "senha/senhaConsultante"),
        ({"verify_tls": 7}, "verify_tls"),
        ({"max_response_bytes": 0}, "max_response_bytes"),
        ({"max_response_bytes": True}, "max_response_bytes"),
        ({"tribunal": 7}, "tribunal e grau"),
        ({"movimentacoes_completas": 1}, "movimentacoes_completas"),
    ],
)
def test_config_222_rejeita_valores_invalidos(kwargs, mensagem):
    valores = {"endpoint": "https://mni.example/Servico", "usuario": "u", "senha": "s"}
    valores.update(kwargs)
    with pytest.raises(ValueError, match=mensagem):
        MNI222Config(**valores)


def test_config_222_ambiente_ausente_e_booleano_invalido(monkeypatch):
    for name in (
        "ENDPOINT",
        "USERNAME",
        "PASSWORD",
        "TRIBUNAL",
        "GRAU",
        "MOVIMENTACOES_COMPLETAS",
        "TOKEN",
    ):
        monkeypatch.delenv(f"NANOJUD_MNI_{name}", raising=False)
    assert MNI222Config.from_env() is None
    monkeypatch.setenv("NANOJUD_MNI_MOVIMENTACOES_COMPLETAS", "yes")
    with pytest.raises(ValueError, match="MOVIMENTACOES_COMPLETAS"):
        MNI222Config.from_env()


@pytest.mark.parametrize(
    ("status_code", "erro"),
    [(401, AcessoRestrito), (403, AcessoRestrito), (503, ConsultaIndisponivel)],
)
def test_mni_222_classifica_http_e_fecha_resposta(status_code, erro):
    response = Response(b"", status_code=status_code)
    client = MNI222Client(config(), session=Session(response))
    with pytest.raises(erro):
        client.consultar_processo(CNJ)
    assert response.closed


@pytest.mark.parametrize(
    "payload",
    [
        b"<!DOCTYPE x><x/>",
        b"not xml",
        b"<Envelope/>",
        b"<s:Envelope xmlns:s='http://schemas.xmlsoap.org/soap/envelope/'><s:Body/></s:Envelope>",
        b"<s:Envelope xmlns:s='http://schemas.xmlsoap.org/soap/envelope/'><s:Body><s:Fault/></s:Body></s:Envelope>",
        (
            b"<s:Envelope xmlns:s='http://schemas.xmlsoap.org/soap/envelope/'>"
            b"<s:Body><x xmlns='urn:wrong'/></s:Body></s:Envelope>"
        ),
    ],
)
def test_mni_222_rejeita_respostas_xml_soap_invalidas(payload):
    client = MNI222Client(config(), session=Session(Response(payload)))
    with pytest.raises(ConsultaIndisponivel):
        client.consultar_processo(CNJ)


def test_mni_222_rejeita_redirect_e_documento_sem_id_ou_com_recibo_falso():
    redirect = Response(b"", status_code=302)
    client = MNI222Client(config(), session=Session(redirect))
    with pytest.raises(ConsultaIndisponivel, match="HTTP 302"):
        client.consultar_processo(CNJ)
    assert redirect.closed

    xml = ET.fromstring(soap_response())
    documento = xml.find(f".//{{{INTERCOMUNICACAO_222_NAMESPACE}}}documento")
    assert documento is not None
    documento.attrib.pop("idDocumento")
    resposta_sem_id = ET.tostring(xml, encoding="utf-8")
    client = MNI222Client(config(), session=Session(Response(resposta_sem_id)))
    with pytest.raises(ConsultaIndisponivel, match="sem identificador"):
        client.consultar_documentos_processo(CNJ, ["doc-1"])

    client = MNI222Client(
        config(), session=Session(Response(soap_response(sucesso="false", mensagem="Falha")))
    )
    with pytest.raises(ConsultaIndisponivel, match="não confirmou"):
        client.consultar_documentos_processo(CNJ, ["doc-1"])


def test_consultar_processo_222_usa_wireschema_e_normaliza_extrato():
    response = Response(soap_response())
    session = Session(response)
    client = MNI222Client(config(), session=session)

    extrato = client.consultar_extrato(CNJ, movimentacoes_completas=True)

    assert extrato["status"] == "ok"
    assert extrato["dados_basicos"]["numero"] == CNJ
    assert extrato["movimentacoes"][0]["teor"] == "Distribuído"
    assert extrato["origem"]["endpoint_host"] == "www12.tjrj.jus.br"
    assert extrato["origem"]["sistema"] == "MNI 2.2.2"
    url, kwargs = session.calls[0]
    assert url == "https://www12.tjrj.jus.br/MNI/Servico.svc"
    assert kwargs["allow_redirects"] is False
    assert kwargs["verify"] is True
    request = ET.fromstring(kwargs["data"])
    operation = request.find(f"{{{SOAP}}}Body/{{{SERVICE_222_NAMESPACE}}}consultarProcesso")
    assert operation is not None
    assert operation.findtext(f"{{{TYPES_222_NAMESPACE}}}idConsultante") == "12345678901"
    assert operation.findtext(f"{{{TYPES_222_NAMESPACE}}}senhaConsultante") == "senha-secreta"
    assert operation.findtext(f"{{{TYPES_222_NAMESPACE}}}numeroProcesso") == "10011943020248260114"
    assert operation.findtext(f"{{{TYPES_222_NAMESPACE}}}movimentos") == "true"
    assert operation.findtext(f"{{{TYPES_222_NAMESPACE}}}incluirDocumentos") == "false"
    assert kwargs["headers"]["SOAPAction"] == (f'"{SERVICE_222_NAMESPACE}consultarProcesso"')
    assert response.closed


def test_consultar_processo_222_explica_erros_de_acesso_e_recibo():
    denied = MNI222Client(
        config(),
        session=Session(Response(soap_response(sucesso="false", mensagem="Acesso não autorizado"))),
    )
    with pytest.raises(AcessoRestrito):
        denied.consultar_extrato(CNJ)

    failed = MNI222Client(config(), session=Session(Response(soap_response(processo=False))))
    with pytest.raises(ConsultaIndisponivel, match="não incluiu os dados do processo"):
        failed.consultar_extrato(CNJ)


def test_consultar_processo_222_valida_cnj_antes_da_rede():
    session = Session(Response(soap_response()))
    client = MNI222Client(config(), session=session)
    with pytest.raises(FormatoCNJInvalido):
        client.consultar_processo("0000000-00.2024.8.26.0114")
    assert not session.calls


def test_extraction_usa_cliente_mni_222_quando_configurado(monkeypatch):
    from nanojud import extraction

    recebido = []

    class Cliente:
        def __init__(self, cfg):
            recebido.append(cfg)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def consultar_extrato(self, numero):
            return {
                "status": "partial",
                "origem": {"movimentacoes_completas": False, "aviso_movimentacoes": "Parcial"},
                "movimentacoes": [],
            }

    monkeypatch.setattr(extraction, "MNI222Client", Cliente)
    cfg = config()
    envelope = extraction.extract_process(CNJ, sources=["mni"], mni_config=cfg)

    assert recebido == [cfg]
    assert envelope["source_status"]["mni"]["status"] == "partial"


def test_consultar_processo_222_impede_redirect_e_resposta_excessiva():
    redirect_client = MNI222Client(config(), session=Session(Response(b"", 302)))
    with pytest.raises(ConsultaIndisponivel, match="HTTP 302"):
        redirect_client.consultar_processo(CNJ)

    limited = MNI222Client(
        config(max_response_bytes=10), session=Session(Response(soap_response()))
    )
    with pytest.raises(ConsultaIndisponivel, match="limite de tamanho"):
        limited.consultar_processo(CNJ)


def test_consultar_processo_222_sanitiza_falha_de_transporte():
    class FailedSession(Session):
        def post(self, url, **kwargs):
            raise requests.Timeout("senha-secreta")

    client = MNI222Client(config(), session=FailedSession(Response(b"")))
    with pytest.raises(ConsultaIndisponivel, match="Timeout") as exc:
        client.consultar_processo(CNJ)
    assert "senha-secreta" not in str(exc.value)


def test_consultar_documentos_222_filtra_ids_e_confirma_identidade():
    client = MNI222Client(config(), session=Session(Response(soap_response())))
    assert client.consultar_documentos_processo(CNJ, ["doc-1"]) == {
        "documentos": [
            {
                "@idDocumento": "doc-1",
                "@tipoDocumento": "PETICAO",
                "@nivelSigilo": "0",
                "conteudo": "UEZERg==",
            }
        ]
    }

    mismatched = soap_response().replace(
        b'numero="10011943020248260114"', b'numero="10765392020198260100"'
    )
    client = MNI222Client(config(), session=Session(Response(mismatched)))
    with pytest.raises(ConsultaIndisponivel, match="diferente do solicitado"):
        client.consultar_documentos_processo(CNJ, ["doc-1"])
