"""Cliente SOAP MNI 2.2.2 para instalações legadas compatíveis."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from os import environ
from typing import Any
from urllib.parse import urlsplit

import requests

from .exceptions import AcessoRestrito, ConsultaIndisponivel
from .mni import SOAP_NAMESPACE, MNI3Config, _elemento_para_valor, _ler_resposta_limitada
from .mni_normalizacao import normalizar_resposta_processo_mni
from .utils import validar_numero_cnj, validar_timeout

SERVICE_222_NAMESPACE = "http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
TYPES_222_NAMESPACE = "http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2"
INTERCOMUNICACAO_222_NAMESPACE = "http://www.cnj.jus.br/intercomunicacao-2.2.2"
MAX_MNI_222_RESPONSE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class MNI222Config:
    """Credenciais e limites de uma instalação MNI SOAP 2.2.2."""

    endpoint: str = field(repr=False)
    usuario: str = field(repr=False)
    senha: str = field(repr=False)
    timeout: float = 30.0
    verify_tls: bool | str = True
    max_response_bytes: int = MAX_MNI_222_RESPONSE_BYTES
    tribunal: str = ""
    grau: str = ""
    movimentacoes_completas: bool = False

    def __post_init__(self) -> None:
        partes = urlsplit(self.endpoint)
        if (
            partes.scheme.casefold() != "https"
            or not partes.hostname
            or partes.username is not None
            or partes.password is not None
            or partes.query
            or partes.fragment
        ):
            raise ValueError(
                "endpoint MNI deve ser HTTPS e não pode conter credenciais, query ou fragmento."
            )
        if not isinstance(self.usuario, str) or not self.usuario.strip():
            raise ValueError("MNI 2.2.2 exige usuario/idConsultante não vazio.")
        if not isinstance(self.senha, str) or not self.senha:
            raise ValueError("MNI 2.2.2 exige senha/senhaConsultante não vazia.")
        validar_timeout(self.timeout)
        if self.verify_tls is False:
            raise ValueError("A validação TLS não pode ser desativada; configure o certificado CA.")
        if not isinstance(self.verify_tls, (bool, str)):
            raise ValueError("verify_tls deve ser True ou caminho de certificado CA.")
        if (
            isinstance(self.max_response_bytes, bool)
            or not isinstance(self.max_response_bytes, int)
            or self.max_response_bytes < 1
        ):
            raise ValueError("max_response_bytes deve ser um inteiro positivo.")
        if not isinstance(self.tribunal, str) or not isinstance(self.grau, str):
            raise ValueError("tribunal e grau devem ser textos.")
        if not isinstance(self.movimentacoes_completas, bool):
            raise ValueError("movimentacoes_completas deve ser booleano.")

    @classmethod
    def from_env(cls, *, prefix: str = "NANOJUD_MNI_") -> MNI222Config | None:
        """Carrega o modo 2.2.2 do ambiente sem mostrar credenciais."""
        token = environ.get(f"{prefix}TOKEN")
        if token:
            raise ValueError(f"{prefix}TOKEN não é aceito pelo MNI 2.2.2.")
        nomes = (
            "ENDPOINT",
            "USERNAME",
            "PASSWORD",
            "TRIBUNAL",
            "GRAU",
            "MOVIMENTACOES_COMPLETAS",
        )
        valores = {nome: environ.get(f"{prefix}{nome}") for nome in nomes}
        if not any(valor is not None for valor in valores.values()):
            return None
        indicador = (valores["MOVIMENTACOES_COMPLETAS"] or "false").strip().casefold()
        if indicador not in {"true", "false"}:
            raise ValueError(f"{prefix}MOVIMENTACOES_COMPLETAS deve ser true ou false.")
        return cls(
            endpoint=valores["ENDPOINT"] or "",
            usuario=valores["USERNAME"] or "",
            senha=valores["PASSWORD"] or "",
            tribunal=valores["TRIBUNAL"] or "",
            grau=valores["GRAU"] or "",
            movimentacoes_completas=indicador == "true",
        )


MNIConfig = MNI3Config | MNI222Config


def configuracao_mni_desde_env(*, prefix: str = "NANOJUD_MNI_") -> MNIConfig | None:
    """Carrega a configuração MNI explicitamente versionada do ambiente local."""
    indicador = environ.get(f"{prefix}VERSION")
    if indicador is None:
        return MNI3Config.from_env(prefix=prefix)
    versao = indicador.strip()
    if versao == "2.2.2":
        return MNI222Config.from_env(prefix=prefix)
    if versao == "3.0":
        return MNI3Config.from_env(prefix=prefix)
    raise ValueError(f"{prefix}VERSION deve ser 2.2.2 ou 3.0.")


class MNI222Client:
    """Consulta o contrato SOAP MNI 2.2.2 com autenticação simples."""

    def __init__(self, config: MNI222Config, *, session: requests.Session | None = None) -> None:
        self.config = config
        self._owns_session = session is None
        self.session = session if session is not None else requests.Session()

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def __enter__(self) -> MNI222Client:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def consultar_processo(
        self,
        numero: str,
        *,
        movimentos: bool = True,
        incluir_cabecalho: bool = True,
        incluir_documentos: bool = False,
    ) -> dict[str, Any]:
        """Executa `consultarProcesso` e retorna o XML convertido para mapping."""
        numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
        if any(
            not isinstance(valor, bool)
            for valor in (movimentos, incluir_cabecalho, incluir_documentos)
        ):
            raise ValueError("As opções movimentos/incluir_* devem ser booleanas.")
        campos = [
            ("idConsultante", self.config.usuario),
            ("senhaConsultante", self.config.senha),
            ("numeroProcesso", re.sub(r"\D", "", numero_cnj)),
            ("movimentos", _bool_xml(movimentos)),
            ("incluirCabecalho", _bool_xml(incluir_cabecalho)),
            ("incluirDocumentos", _bool_xml(incluir_documentos)),
        ]
        raiz = ET.Element(_qname(SERVICE_222_NAMESPACE, "consultarProcesso"))
        for nome, valor in campos:
            ET.SubElement(raiz, _qname(TYPES_222_NAMESPACE, nome)).text = valor
        return self._chamar(raiz)

    def consultar_extrato(
        self,
        numero: str,
        *,
        incluir_cabecalho: bool = True,
        incluir_movimentos: bool = True,
        incluir_documentos: bool = False,
        movimentacoes_completas: bool | None = None,
    ) -> dict[str, Any]:
        if not isinstance(incluir_movimentos, bool) or not isinstance(incluir_documentos, bool):
            raise ValueError("As opções incluir_movimentos/incluir_documentos devem ser booleanas.")
        resposta = self.consultar_processo(
            numero,
            movimentos=incluir_movimentos,
            incluir_cabecalho=incluir_cabecalho,
            incluir_documentos=incluir_documentos,
        )
        mensagens: list[dict[str, str]] = []
        mensagem = _texto(resposta.get("mensagem"))
        if mensagem:
            mensagens.append({"descritivo": mensagem})
        resposta_normalizada = {
            "recibo": {"sucesso": resposta.get("sucesso"), "mensagens": mensagens},
            "processo": _adaptar_processo_222(resposta.get("processo")),
        }
        if resposta_normalizada["processo"] is None:
            resposta_normalizada.pop("processo")
        return normalizar_resposta_processo_mni(
            numero,
            resposta_normalizada,
            endpoint=self.config.endpoint,
            tribunal=self.config.tribunal,
            grau=self.config.grau,
            incluir_movimentos=incluir_movimentos,
            incluir_documentos=incluir_documentos,
            movimentacoes_completas=(
                self.config.movimentacoes_completas
                if movimentacoes_completas is None
                else movimentacoes_completas
            ),
            versao="2.2.2",
        )

    def consultar_documentos_processo(
        self, numero: str, ids_documentos: Iterable[str]
    ) -> dict[str, Any]:
        """Consulta documentos inline pelo contrato 2.2.2 e filtra pelos IDs pedidos."""
        if isinstance(ids_documentos, (str, bytes)):
            raise ValueError("ids_documentos deve ser uma coleção de identificadores.")
        ids = list(ids_documentos)
        if not ids or any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("Informe identificadores de documento não vazios.")
        resposta = self.consultar_processo(numero, incluir_documentos=True)
        processo = resposta.get("processo")
        if not isinstance(processo, Mapping):
            raise ConsultaIndisponivel("O MNI 2.2.2 não retornou o processo para obter documentos.")
        recibo = {"sucesso": resposta.get("sucesso"), "mensagens": resposta.get("mensagem")}
        _validar_sucesso_222(recibo)
        numero_consultado = validar_numero_cnj(numero, segmento=None, tribunal=None)
        processo = _adaptar_processo_222(processo) or {}
        numero_retorno = _texto(processo.get("numeroProcesso"))
        try:
            numero_retorno = validar_numero_cnj(numero_retorno, segmento=None, tribunal=None)
        except (TypeError, ValueError) as exc:
            raise ConsultaIndisponivel("O MNI 2.2.2 retornou processo sem CNJ válido.") from exc
        if numero_retorno != numero_consultado:
            raise ConsultaIndisponivel("O MNI 2.2.2 retornou processo diferente do solicitado.")
        documentos = _lista(processo.get("documento"))
        ids_solicitados = {item.strip() for item in ids}
        selecionados = []
        for documento in documentos:
            if not isinstance(documento, Mapping):
                raise ConsultaIndisponivel("O MNI 2.2.2 retornou documento com estrutura inválida.")
            identificador = _texto(
                documento.get("@idDocumento")
                or documento.get("@id")
                or documento.get("idDocumento")
            )
            if not identificador:
                raise ConsultaIndisponivel("O MNI 2.2.2 retornou documento sem identificador.")
            if identificador in ids_solicitados:
                selecionados.append(dict(documento))
        return {"documentos": selecionados}

    def _chamar(self, operacao: ET.Element) -> dict[str, Any]:
        envelope = ET.Element(_qname(SOAP_NAMESPACE, "Envelope"))
        ET.SubElement(envelope, _qname(SOAP_NAMESPACE, "Header"))
        body = ET.SubElement(envelope, _qname(SOAP_NAMESPACE, "Body"))
        body.append(operacao)
        payload = ET.tostring(envelope, encoding="utf-8", xml_declaration=True)
        soap_action = f'"{SERVICE_222_NAMESPACE}consultarProcesso"'
        try:
            response = self.session.post(
                self.config.endpoint,
                data=payload,
                headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": soap_action},
                timeout=self.config.timeout,
                verify=self.config.verify_tls,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ConsultaIndisponivel(
                f"Falha de comunicação com serviço MNI 2.2.2 ({type(exc).__name__})."
            ) from exc
        if response.status_code in (401, 403):
            response.close()
            raise AcessoRestrito("O serviço MNI 2.2.2 recusou a autenticação ou o acesso.")
        if not 200 <= response.status_code < 300:
            response.close()
            raise ConsultaIndisponivel(
                f"O serviço MNI 2.2.2 respondeu com HTTP {response.status_code}."
            )
        try:
            payload = _ler_resposta_limitada(response, self.config.max_response_bytes)
        except requests.RequestException as exc:
            raise ConsultaIndisponivel(
                f"Falha ao receber resposta do serviço MNI 2.2.2 ({type(exc).__name__})."
            ) from exc
        finally:
            response.close()
        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise ConsultaIndisponivel("O serviço MNI 2.2.2 retornou XML com declaração externa.")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ConsultaIndisponivel("O serviço MNI 2.2.2 retornou XML inválido.") from exc
        if root.tag != _qname(SOAP_NAMESPACE, "Envelope"):
            raise ConsultaIndisponivel("O serviço MNI 2.2.2 retornou SOAP inesperado.")
        soap_body = root.find(_qname(SOAP_NAMESPACE, "Body"))
        if soap_body is None or len(soap_body) != 1:
            raise ConsultaIndisponivel("O serviço MNI 2.2.2 retornou SOAP inesperado.")
        result = soap_body[0]
        if result.tag == _qname(SOAP_NAMESPACE, "Fault"):
            raise ConsultaIndisponivel("O serviço MNI 2.2.2 retornou falha SOAP.")
        if result.tag != _qname(SERVICE_222_NAMESPACE, "consultarProcessoResposta"):
            raise ConsultaIndisponivel("O serviço MNI 2.2.2 respondeu operação inesperada.")
        value = _elemento_para_valor(result)
        if not isinstance(value, dict):
            raise ConsultaIndisponivel("O serviço MNI 2.2.2 retornou resposta inválida.")
        return value


def _adaptar_processo_222(valor: Any) -> dict[str, Any] | None:
    """Adapta atributos CNJ 2.2.2 para os nomes do normalizador já compartilhado."""
    if not isinstance(valor, Mapping):
        return None
    processo = dict(valor)
    basicos = processo.get("dadosBasicos")
    if isinstance(basicos, Mapping):
        cabecalho = dict(basicos)
        for nome in (
            "numero",
            "classeProcessual",
            "competencia",
            "codigoLocalidade",
            "nivelSigilo",
            "dataAjuizamento",
            "valorCausa",
        ):
            if f"@{nome}" in cabecalho:
                cabecalho[nome] = cabecalho[f"@{nome}"]
        if "numero" in cabecalho and "numeroProcesso" not in processo:
            processo["numeroProcesso"] = cabecalho["numero"]
        processo["dadosBasicos"] = cabecalho
    return processo


def _validar_sucesso_222(recibo: Mapping[str, Any]) -> None:
    sucesso = _texto(recibo.get("sucesso")).casefold()
    if sucesso in {"true", "1"}:
        return
    mensagem = " ".join(_texto(item) for item in _lista(recibo.get("mensagens")) if _texto(item))
    if any(
        item in mensagem.casefold()
        for item in ("não autorizado", "nao autorizado", "sigilo", "acesso")
    ):
        raise AcessoRestrito("O MNI 2.2.2 recusou a autenticação ou o acesso ao documento.")
    raise ConsultaIndisponivel("O MNI 2.2.2 não confirmou a consulta de documentos.")


def _lista(valor: Any) -> list[Any]:
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _texto(valor: Any) -> str:
    if isinstance(valor, Mapping):
        valor = valor.get("#text")
    if valor is None or isinstance(valor, (dict, list, bool)):
        return ""
    return str(valor).strip()


def _bool_xml(valor: bool) -> str:
    return "true" if valor else "false"


def _qname(namespace: str, nome: str) -> str:
    return f"{{{namespace}}}{nome}"
