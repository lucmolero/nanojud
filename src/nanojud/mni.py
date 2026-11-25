"""Cliente SOAP de leitura para o Modelo Nacional de Interoperabilidade 3.0."""

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
from .mni_normalizacao import normalizar_resposta_processo_mni, validar_recibo_mni
from .utils import validar_numero_cnj, validar_timeout

SOAP_NAMESPACE = "http://schemas.xmlsoap.org/soap/envelope/"
MNI_NAMESPACE = "http://www.cnj.jus.br/mni/v300/"
TIPOS_NAMESPACE = "http://www.cnj.jus.br/mni/v300/tipos-servico-intercomunicacao"
INTERCOMUNICACAO_NAMESPACE = "http://www.cnj.jus.br/mni/v300/intercomunicacao"
MAX_MNI_RESPONSE_BYTES = 32 * 1024 * 1024
_LOCAL_NAME = re.compile(r"(?:\{[^}]+\})?([^}]+)$")


@dataclass(frozen=True)
class MNI3Config:
    """Configuração de um endpoint MNI 3.0.

    Configure exatamente uma modalidade: token ou usuário e senha. Segredos são
    excluídos da representação para reduzir vazamentos acidentais em logs.
    """

    endpoint: str = field(repr=False)
    usuario: str | None = field(default=None, repr=False)
    senha: str | None = field(default=None, repr=False)
    token: str | None = field(default=None, repr=False)
    pessoa_vinculada: str | None = field(default=None, repr=False)
    timeout: float = 30.0
    verify_tls: bool | str = True
    max_response_bytes: int = MAX_MNI_RESPONSE_BYTES
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
        if self.token:
            if self.usuario is not None or self.senha is not None:
                raise ValueError("Informe exclusivamente token ou usuario/senha para o MNI.")
        elif not self.usuario or not self.senha:
            raise ValueError("Informe token ou usuario/senha para o MNI.")
        if self.pessoa_vinculada is not None and not re.fullmatch(
            r"(?:\d{11}|\d{14})", self.pessoa_vinculada
        ):
            raise ValueError("pessoa_vinculada deve conter CPF ou CNPJ sem pontuação.")
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
    def from_env(cls, *, prefix: str = "NANOJUD_MNI_") -> MNI3Config | None:
        """Carrega a configuração MNI de variáveis de ambiente, sem exigir cadastro.

        Variáveis: ``ENDPOINT`` e exatamente um de ``TOKEN`` ou ``USERNAME`` +
        ``PASSWORD``. ``PESSOA_VINCULADA``, ``TRIBUNAL``, ``GRAU`` e
        ``MOVIMENTACOES_COMPLETAS`` são opcionais. A configuração só é criada se
        pelo menos uma variável do prefixo estiver presente; uma configuração parcial
        falha explicitamente em vez de ser ignorada.
        """
        versao = environ.get(f"{prefix}VERSION")
        if versao is not None and versao.strip() != "3.0":
            raise ValueError(
                f"Use configuracao_mni_desde_env() para carregar a versão MNI "
                f"{versao.strip()!r}; MNI3Config só aceita 3.0."
            )
        nomes = (
            "ENDPOINT",
            "TOKEN",
            "USERNAME",
            "PASSWORD",
            "PESSOA_VINCULADA",
            "TRIBUNAL",
            "GRAU",
            "MOVIMENTACOES_COMPLETAS",
        )
        valores = {nome: environ.get(f"{prefix}{nome}") for nome in nomes}
        if not any(valor is not None for valor in valores.values()):
            return None
        endpoint = valores["ENDPOINT"] or ""
        indicador_completo = (valores["MOVIMENTACOES_COMPLETAS"] or "false").strip().casefold()
        if indicador_completo not in {"true", "false"}:
            raise ValueError(f"{prefix}MOVIMENTACOES_COMPLETAS deve ser true ou false.")
        return cls(
            endpoint=endpoint,
            token=valores["TOKEN"],
            usuario=valores["USERNAME"],
            senha=valores["PASSWORD"],
            pessoa_vinculada=valores["PESSOA_VINCULADA"],
            tribunal=valores["TRIBUNAL"] or "",
            grau=valores["GRAU"] or "",
            movimentacoes_completas=indicador_completo == "true",
        )


class MNI3Client:
    """Consulta processo e documentos por endpoint SOAP MNI 3.0.

    Os resultados preservam os nomes e atributos do XML MNI em estruturas Python.
    A instância usa a sessão HTTP recebida pelo chamador; não compartilhe uma
    instância entre workers concorrentes sem prover sessões isoladas.
    """

    def __init__(self, config: MNI3Config, *, session: requests.Session | None = None) -> None:
        self.config = config
        self._owns_session = session is None
        self.session = session if session is not None else requests.Session()

    def close(self) -> None:
        """Fecha apenas a sessão HTTP criada pelo próprio cliente."""
        if self._owns_session:
            self.session.close()

    def __enter__(self) -> MNI3Client:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def consultar_processo(
        self,
        numero: str,
        *,
        incluir_cabecalho: bool = True,
        incluir_partes: bool = True,
        incluir_enderecos: bool = False,
        incluir_movimentos: bool = True,
        incluir_documentos: bool = False,
    ) -> dict[str, Any]:
        """Executa `consultarProcesso` e devolve a resposta MNI desserializada."""
        numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
        opcoes = {
            "incluirCabecalho": incluir_cabecalho,
            "incluirPartes": incluir_partes,
            "incluirEnderecos": incluir_enderecos,
            "incluirMovimentos": incluir_movimentos,
            "incluirDocumentos": incluir_documentos,
        }
        if any(not isinstance(valor, bool) for valor in opcoes.values()):
            raise ValueError("As opções incluir_* devem ser booleanas.")
        elementos = [
            (TIPOS_NAMESPACE, "numeroProcesso", re.sub(r"\D", "", numero_cnj)),
            *((TIPOS_NAMESPACE, nome, _bool_xml(valor)) for nome, valor in opcoes.items()),
        ]
        return self._chamar(
            "consultarProcesso",
            "respostaConsultarProcesso",
            "requisicaoConsultarProcesso",
            elementos,
        )

    def consultar_extrato(
        self,
        numero: str,
        *,
        tribunal: str | None = None,
        grau: str | None = None,
        incluir_cabecalho: bool = True,
        incluir_partes: bool = True,
        incluir_enderecos: bool = False,
        incluir_movimentos: bool = True,
        incluir_documentos: bool = False,
        movimentacoes_completas: bool | None = None,
    ) -> dict[str, Any]:
        """Consulta o MNI e normaliza a resposta no formato de extrato NanoJud.

        ``movimentacoes_completas`` deve ser informado como verdadeiro apenas
        quando o contrato operacional da instalação garantir histórico integral.
        O método retorna metadados de documentos; para conteúdo binário use
        ``consultar_documentos_processo``.
        """
        numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
        resposta = self.consultar_processo(
            numero_cnj,
            incluir_cabecalho=incluir_cabecalho,
            incluir_partes=incluir_partes,
            incluir_enderecos=incluir_enderecos,
            incluir_movimentos=incluir_movimentos,
            incluir_documentos=incluir_documentos,
        )
        return normalizar_resposta_processo_mni(
            numero_cnj,
            resposta,
            endpoint=self.config.endpoint,
            tribunal=self.config.tribunal if tribunal is None else tribunal,
            grau=self.config.grau if grau is None else grau,
            incluir_movimentos=incluir_movimentos,
            incluir_documentos=incluir_documentos,
            movimentacoes_completas=(
                self.config.movimentacoes_completas
                if movimentacoes_completas is None
                else movimentacoes_completas
            ),
        )

    def consultar_documentos_processo(
        self, numero: str, ids_documentos: Iterable[str]
    ) -> dict[str, Any]:
        """Obtém conteúdo dos documentos pelos IDs retornados pelo MNI."""
        numero_cnj = validar_numero_cnj(numero, segmento=None, tribunal=None)
        if isinstance(ids_documentos, (str, bytes)):
            raise ValueError("ids_documentos deve ser uma coleção de identificadores.")
        ids = list(ids_documentos)
        if not ids:
            raise ValueError("Informe pelo menos um identificador de documento.")
        if any(
            not isinstance(identificador, str) or not identificador.strip() for identificador in ids
        ):
            raise ValueError("Cada identificador de documento deve ser texto não vazio.")
        elementos = [
            (TIPOS_NAMESPACE, "numeroProcesso", re.sub(r"\D", "", numero_cnj)),
            *((TIPOS_NAMESPACE, "idDocumento", identificador.strip()) for identificador in ids),
        ]
        resposta = self._chamar(
            "consultarDocumentosProcesso",
            "respostaConsultarDocumentosProcesso",
            "requisicaoConsultarDocumentosProcesso",
            elementos,
        )
        recibo = resposta.get("recibo")
        if not isinstance(recibo, Mapping):
            raise ConsultaIndisponivel(
                "O serviço MNI não retornou um recibo válido para documentos."
            )
        validar_recibo_mni(recibo)
        documentos = resposta.get("documentos")
        if documentos is None:
            return resposta
        if isinstance(documentos, Mapping):
            lista_documentos = [documentos]
        elif isinstance(documentos, list):
            lista_documentos = documentos
        else:
            raise ConsultaIndisponivel("O serviço MNI retornou índice de documentos inválido.")
        ids_solicitados = {identificador.strip() for identificador in ids}
        for documento in lista_documentos:
            if not isinstance(documento, Mapping):
                raise ConsultaIndisponivel(
                    "O serviço MNI retornou documento com estrutura inválida."
                )
            id_documento = documento.get("idDocumento")
            if (
                isinstance(id_documento, bool)
                or not isinstance(id_documento, (str, int))
                or not str(id_documento).strip()
            ):
                raise ConsultaIndisponivel("O serviço MNI retornou documento sem identificador.")
            if str(id_documento).strip() not in ids_solicitados:
                raise ConsultaIndisponivel(
                    "O serviço MNI retornou identificador de documento inesperado."
                )
        return resposta

    def _chamar(
        self,
        operacao: str,
        resposta_esperada: str,
        requisicao: str,
        elementos: list[tuple[str, str, str]],
    ) -> dict[str, Any]:
        envelope = ET.Element(_qname(SOAP_NAMESPACE, "Envelope"))
        ET.SubElement(envelope, _qname(SOAP_NAMESPACE, "Header"))
        body = ET.SubElement(envelope, _qname(SOAP_NAMESPACE, "Body"))
        raiz = ET.SubElement(body, _qname(MNI_NAMESPACE, requisicao))
        self._adicionar_consultante(raiz)
        for namespace, nome, valor in elementos:
            ET.SubElement(raiz, _qname(namespace, nome)).text = valor
        payload = ET.tostring(envelope, encoding="utf-8", xml_declaration=True)
        try:
            resposta = self.session.post(
                self.config.endpoint,
                data=payload,
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": f'"{MNI_NAMESPACE}{operacao}"',
                },
                timeout=self.config.timeout,
                verify=self.config.verify_tls,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ConsultaIndisponivel(
                f"Falha de comunicação com serviço MNI 3.0 ({type(exc).__name__})."
            ) from exc

        if resposta.status_code in (401, 403):
            resposta.close()
            raise AcessoRestrito("O serviço MNI recusou a autenticação ou o acesso solicitado.")
        if not 200 <= resposta.status_code < 300:
            resposta.close()
            raise ConsultaIndisponivel(f"O serviço MNI respondeu com HTTP {resposta.status_code}.")
        try:
            conteudo = _ler_resposta_limitada(resposta, self.config.max_response_bytes)
        except requests.RequestException as exc:
            raise ConsultaIndisponivel(
                f"Falha ao receber resposta do serviço MNI 3.0 ({type(exc).__name__})."
            ) from exc
        finally:
            resposta.close()
        if b"<!DOCTYPE" in conteudo.upper() or b"<!ENTITY" in conteudo.upper():
            raise ConsultaIndisponivel(
                "O serviço MNI retornou XML com declarações externas não aceitas."
            )
        try:
            raiz_resposta = ET.fromstring(conteudo)
        except ET.ParseError as exc:
            raise ConsultaIndisponivel("O serviço MNI retornou XML inválido.") from exc
        if raiz_resposta.tag != _qname(SOAP_NAMESPACE, "Envelope"):
            raise ConsultaIndisponivel("O serviço MNI retornou uma resposta SOAP inesperada.")
        corpo = raiz_resposta.find(_qname(SOAP_NAMESPACE, "Body"))
        if corpo is None or len(corpo) != 1:
            raise ConsultaIndisponivel("O serviço MNI retornou uma resposta SOAP inesperada.")
        elemento_resposta = corpo[0]
        if elemento_resposta.tag == _qname(SOAP_NAMESPACE, "Fault"):
            raise ConsultaIndisponivel("O serviço MNI retornou uma falha SOAP.")
        if elemento_resposta.tag != _qname(MNI_NAMESPACE, resposta_esperada):
            raise ConsultaIndisponivel(
                "O serviço MNI retornou uma operação diferente da solicitada."
            )
        return _elemento_para_valor(elemento_resposta)

    def _adicionar_consultante(self, requisicao: ET.Element) -> None:
        consultante = ET.SubElement(requisicao, _qname(TIPOS_NAMESPACE, "consultante"))
        if self.config.token:
            ET.SubElement(
                consultante, _qname(INTERCOMUNICACAO_NAMESPACE, "token")
            ).text = self.config.token
        else:
            autenticacao = ET.SubElement(
                consultante, _qname(INTERCOMUNICACAO_NAMESPACE, "autenticacaoSimples")
            )
            ET.SubElement(
                autenticacao, _qname(INTERCOMUNICACAO_NAMESPACE, "usuario")
            ).text = self.config.usuario
            ET.SubElement(
                autenticacao, _qname(INTERCOMUNICACAO_NAMESPACE, "senha")
            ).text = self.config.senha
        if self.config.pessoa_vinculada:
            ET.SubElement(
                consultante, _qname(INTERCOMUNICACAO_NAMESPACE, "pessoaVinculada")
            ).text = self.config.pessoa_vinculada


def _ler_resposta_limitada(resposta: requests.Response, limite: int) -> bytes:
    partes: list[bytes] = []
    total = 0
    for bloco in resposta.iter_content(chunk_size=64 * 1024):
        if not bloco:
            continue
        total += len(bloco)
        if total > limite:
            raise ConsultaIndisponivel("Resposta MNI excedeu o limite de tamanho configurado.")
        partes.append(bloco)
    return b"".join(partes)


def _elemento_para_valor(elemento: ET.Element) -> Any:
    atributos = {f"@{_local_name(chave)}": valor for chave, valor in elemento.attrib.items()}
    filhos: dict[str, Any] = {}
    for filho in elemento:
        nome = _local_name(filho.tag)
        valor = _elemento_para_valor(filho)
        if nome in filhos:
            atual = filhos[nome]
            filhos[nome] = [*atual, valor] if isinstance(atual, list) else [atual, valor]
        else:
            filhos[nome] = valor
    texto = (elemento.text or "").strip()
    if not atributos and not filhos:
        return texto or None
    resultado: dict[str, Any] = atributos
    resultado.update(filhos)
    if texto:
        resultado["#text"] = texto
    return resultado


def _bool_xml(valor: bool) -> str:
    return "true" if valor else "false"


def _local_name(nome: str) -> str:
    match = _LOCAL_NAME.fullmatch(nome)
    return match.group(1) if match else nome


def _qname(namespace: str, nome: str) -> str:
    return f"{{{namespace}}}{nome}"
