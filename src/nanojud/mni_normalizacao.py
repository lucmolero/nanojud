"""Normalização de respostas MNI 3.0 para o contrato de extrato NanoJud."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from .exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado
from .normalization import normalizar_data
from .utils import validar_numero_cnj

_PARAMETROS_SEGUROS = frozenset(
    {
        "antecipacaoTutela",
        "assuntoPrincipal",
        "dataAutuacao",
        "orgaoJulgador",
        "rito",
        "ritoProcessual",
        "situacao",
    }
)


def normalizar_resposta_processo_mni(
    numero_consultado: str,
    resposta: Mapping[str, Any],
    *,
    endpoint: str,
    tribunal: str = "",
    grau: str = "",
    incluir_movimentos: bool = True,
    incluir_documentos: bool = False,
    movimentacoes_completas: bool = False,
    versao: str = "3.0",
) -> dict[str, Any]:
    """Converte uma resposta ``respostaConsultarProcesso`` em extrato.

    A completude do histórico é uma garantia operacional da instalação MNI, não
    algo que o XML da resposta prove sozinho. Por isso, ``movimentacoes_completas``
    é falso por padrão e só deve ser habilitado quando o contrato do serviço
    confirmar que a consulta cobre todo o histórico.
    """
    if not isinstance(resposta, Mapping):
        raise ConsultaIndisponivel("O serviço MNI retornou uma resposta sem objeto raiz.")
    if not isinstance(incluir_movimentos, bool) or not isinstance(incluir_documentos, bool):
        raise ValueError("As opções incluir_movimentos/incluir_documentos devem ser booleanas.")
    if not isinstance(movimentacoes_completas, bool):
        raise ValueError("movimentacoes_completas deve ser booleano.")
    if versao not in {"2.2.2", "3.0"}:
        raise ValueError("versao deve ser 2.2.2 ou 3.0.")

    numero = _validar_numero(numero_consultado, "número consultado")
    recibo = resposta.get("recibo")
    if not isinstance(recibo, Mapping):
        raise ConsultaIndisponivel("O serviço MNI não retornou um recibo válido.")
    validar_recibo_mni(recibo)

    processo = resposta.get("processo")
    if not isinstance(processo, Mapping):
        raise ConsultaIndisponivel("O serviço MNI não incluiu os dados do processo.")
    cabecalho = _mapping(processo.get("dadosBasicos"))
    cabecalho_simples = _mapping(cabecalho.get("dadosBasicos"))
    numero_retorno = (
        _texto(processo.get("numeroProcesso"))
        or _texto(_campo(cabecalho, "numero"))
        or _texto(_campo(cabecalho_simples, "numero"))
    )
    if not numero_retorno:
        raise ConsultaIndisponivel("A resposta MNI não identificou o número do processo.")
    numero_retorno_normalizado = _validar_numero(numero_retorno, "número retornado")
    if numero_retorno_normalizado != numero:
        raise ConsultaIndisponivel("O serviço MNI retornou um processo diferente do consultado.")

    movimentos = _normalizar_movimentos(
        _lista(processo.get("movimento")),
        incluir_movimentos=incluir_movimentos,
        documentos=_lista(processo.get("documento")) if incluir_documentos else [],
    )
    documentos = _normalizar_documentos(_lista(processo.get("documento")))
    polo_partes = _normalizar_partes(_lista(cabecalho.get("polo")))
    basicos = _normalizar_dados_basicos(cabecalho, cabecalho_simples, numero)

    sigilo = _texto(_campo(cabecalho, "nivelSigilo"))
    garantia_completude = incluir_movimentos and movimentacoes_completas
    avisos: list[str] = []
    if not incluir_movimentos:
        avisos.append("A consulta MNI não solicitou movimentos do processo.")
    elif not garantia_completude:
        avisos.append(
            "A completude dos movimentos não foi confirmada pelo contrato desta instalação MNI."
        )
    if sigilo and sigilo != "0":
        garantia_completude = False
        avisos.append(
            "O cabeçalho MNI indica nível de sigilo diferente de zero; "
            "a cobertura pode ser restrita."
        )
    aviso_documentos = (
        "A consulta MNI não solicitou o índice de documentos." if not incluir_documentos else ""
    )

    host = urlsplit(endpoint).hostname
    if urlsplit(endpoint).scheme.casefold() != "https" or not host:
        raise ValueError("endpoint deve ser uma URL HTTPS válida para registrar a origem MNI.")
    origem: dict[str, Any] = {
        "sistema": f"MNI {versao}",
        "consulta": "SOAP consultarProcesso",
        "entrada": numero,
        "endpoint_host": host,
        "data_coleta": datetime.now(UTC).isoformat(),
        "movimentacoes_completas": garantia_completude,
    }
    if tribunal.strip():
        origem["tribunal"] = tribunal.strip().upper()
    if grau.strip():
        origem["grau"] = grau.strip()
    if avisos:
        origem["aviso_movimentacoes"] = " ".join(dict.fromkeys(avisos))
    if aviso_documentos:
        origem["aviso_documentos"] = aviso_documentos

    resultado: dict[str, Any] = {
        "status": "ok" if garantia_completude else "partial",
        "mensagem": (
            f"Consulta MNI {versao} normalizada."
            if garantia_completude
            else f"Consulta MNI {versao} normalizada com cobertura parcial ou não confirmada."
        ),
        "origem": origem,
        "dados_basicos": basicos,
        "partes": polo_partes,
        "movimentacoes": movimentos,
    }
    if incluir_documentos:
        resultado["documentos"] = documentos
    return resultado


def _validar_numero(valor: str, descricao: str) -> str:
    try:
        return validar_numero_cnj(valor, segmento=None, tribunal=None)
    except (TypeError, ValueError) as exc:
        raise ConsultaIndisponivel(f"A resposta MNI contém {descricao} inválido.") from exc


def validar_recibo_mni(recibo: Mapping[str, Any]) -> None:
    """Valida o sucesso MNI e classifica falhas pelo recibo da operação."""
    sucesso = _booleano_mni(_campo(recibo, "sucesso"))
    if sucesso is None:
        raise ConsultaIndisponivel("O serviço MNI retornou um recibo MNI inválido.")
    if not sucesso:
        _classificar_falha_recibo(recibo)


def _classificar_falha_recibo(recibo: Mapping[str, Any]) -> None:
    mensagens = " ".join(
        _texto(_mapping(item).get("descritivo") or _mapping(item).get("mensagem"))
        for item in _lista(recibo.get("mensagens") or recibo.get("mensagem"))
    ).casefold()
    if any(
        chave in mensagens
        for chave in ("captcha", "autentica", "acesso negado", "não autorizado", "nao autorizado")
    ):
        raise AcessoRestrito("O serviço MNI recusou a autenticação ou o acesso solicitado.")
    if any(chave in mensagens for chave in ("segredo de justiça", "segredo de justica", "sigilo")):
        raise AcessoRestrito("O serviço MNI informou restrição de acesso ao processo.")
    if any(chave in mensagens for chave in ("não encontrado", "nao encontrado")):
        raise ProcessoNaoEncontrado("O serviço MNI informou que não encontrou o processo.")
    raise ConsultaIndisponivel("O serviço MNI não concluiu a consulta processual.")


def _normalizar_dados_basicos(
    cabecalho: Mapping[str, Any], cabecalho_simples: Mapping[str, Any], numero: str
) -> dict[str, Any]:
    orgao = _mapping(_campo(cabecalho, "orgaoJulgador")) or _mapping(
        _campo(cabecalho_simples, "orgaoJulgador")
    )
    classe_codigo = _texto(_campo(cabecalho, "classeProcessual")) or _texto(
        _campo(cabecalho_simples, "classeProcessual")
    )
    assuntos = _lista(_campo(cabecalho, "assunto"))
    assunto = next(
        (item for item in assuntos if _booleano_mni(_mapping(item).get("@principal")) is True),
        assuntos[0] if assuntos else {},
    )
    assunto_codigo = _texto(_campo(_mapping(assunto), "codigoNacional"))
    ajuizamento = _texto(_campo(cabecalho, "dataAjuizamento"))
    parametros = _parametros(_campo(cabecalho, "outroParametro"))
    dados: dict[str, Any] = {"numero": numero}
    if classe_codigo:
        dados["classe_codigo"] = classe_codigo
    if assunto_codigo:
        dados["assunto_codigo"] = assunto_codigo
    if nome_orgao := _texto(_campo(orgao, "nome")):
        dados["vara"] = nome_orgao
    if ajuizamento:
        dados["distribuicao"] = normalizar_data(ajuizamento)["iso"] or ajuizamento
    if situacao := parametros.get("situacao"):
        dados["situacao"] = situacao
    if valor_causa := _texto(_campo(cabecalho, "valorCausa")):
        dados["valor_acao"] = valor_causa

    rotulados = {
        "mni_classe_processual_codigo": classe_codigo,
        "mni_assunto_codigo": assunto_codigo,
        "mni_orgao_julgador_codigo": _texto(_campo(orgao, "codigo")),
        "mni_orgao_julgador_instancia": _texto(_campo(orgao, "instancia")),
        "mni_codigo_localidade": _texto(_campo(cabecalho, "codigoLocalidade")),
        "mni_nivel_sigilo": _texto(_campo(cabecalho, "nivelSigilo")),
        "mni_competencia_codigo": _texto(_campo(cabecalho, "competencia")),
        "mni_data_ajuizamento": ajuizamento,
        "mni_data_autuacao": parametros.get("dataAutuacao", ""),
    }
    rotulados.update(
        {
            f"mni_parametro_{nome}": valor
            for nome, valor in parametros.items()
            if nome in _PARAMETROS_SEGUROS
        }
    )
    dados["campos_rotulados"] = {chave: valor for chave, valor in rotulados.items() if valor}
    return dados


def _parametros(valor: Any) -> dict[str, str]:
    resultado: dict[str, str] = {}
    for item in _lista(valor):
        parametro = _mapping(item)
        nome = _texto(parametro.get("@nome") or parametro.get("nome"))
        conteudo = _texto(parametro.get("@valor") or parametro.get("valor"))
        if nome and conteudo:
            resultado[nome] = conteudo
    return resultado


def _normalizar_partes(polos: list[Any]) -> dict[str, list[dict[str, Any]]]:
    todas: list[dict[str, Any]] = []
    ativos: list[dict[str, Any]] = []
    passivos: list[dict[str, Any]] = []
    desconhecidos: list[dict[str, Any]] = []
    for item in polos:
        polo = _mapping(item)
        codigo_polo = _texto(polo.get("@polo"))
        for parte_item in _lista(polo.get("parte")):
            parte = _mapping(parte_item)
            pessoa = _mapping(parte.get("pessoa"))
            pessoa_basica = _mapping(pessoa.get("dadosBasicos"))
            nomes = [_texto(pessoa_basica.get("nome"))]
            if _booleano_mni(parte.get("interessePublico")) is True:
                nomes = ["Interesse público"]
            nomes = [nome for nome in nomes if nome]
            advogados = []
            representantes = []
            for representante_item in _lista(parte.get("advogado")):
                representante = _mapping(representante_item)
                nome = _texto(representante.get("@nome") or representante.get("nome"))
                inscricao = _texto(
                    representante.get("@inscricao") or representante.get("inscricao")
                )
                if nome:
                    advogados.append(nome)
                if nome or inscricao:
                    representantes.append({"nome": nome, "inscricao": inscricao})
            if not nomes and not advogados:
                continue
            registro: dict[str, Any] = {
                "tipo": codigo_polo,
                "nomes": nomes,
                "advogados": list(dict.fromkeys(advogados)),
                "metadados": {
                    "codigo_polo_mni": codigo_polo,
                    "situacao_mni": _texto(parte.get("situacao")),
                    "qualificacao_pessoa_mni": _texto(pessoa_basica.get("qualificacaoPessoa")),
                    "representantes_mni": representantes,
                },
            }
            todas.append(registro)
            if codigo_polo == "AT":
                ativos.append(registro)
            elif codigo_polo == "PA":
                passivos.append(registro)
            else:
                desconhecidos.append(registro)
    principais = [*ativos, *passivos]
    return {
        "principais": principais,
        "todas": todas,
        "polo_ativo": ativos,
        "polo_passivo": passivos,
        "polo_desconhecido": desconhecidos,
    }


def _normalizar_movimentos(
    movimentos_mni: list[Any], *, incluir_movimentos: bool, documentos: list[Any]
) -> list[dict[str, Any]]:
    if not incluir_movimentos:
        return []
    docs = {doc["id_documento"]: doc for doc in _normalizar_documentos(documentos)["todos_mni"]}
    movimentos: list[dict[str, Any]] = []
    for indice, movimento_item in enumerate(movimentos_mni, start=1):
        movimento = _mapping(movimento_item)
        local = _mapping(movimento.get("movimentoLocal"))
        nacional = _mapping(movimento.get("movimentoNacional"))
        codigo_nacional = _texto(nacional.get("@codigoNacional"))
        codigo_local = _texto(local.get("@codigoMovimento"))
        titulo = _texto(local.get("@descricao"))
        if not titulo and codigo_nacional:
            titulo = f"Movimento CNJ {codigo_nacional}"
        if not titulo and codigo_local:
            titulo = f"Movimento local {codigo_local}"
        data_original = _texto(movimento.get("@dataHora"))
        data = normalizar_data(data_original)
        complementos = [
            _texto(item) for item in _lista(movimento.get("complemento")) if _texto(item)
        ]
        ids_documentos = [
            _texto(item) for item in _lista(movimento.get("idDocumentoVinculado")) if _texto(item)
        ]
        documentos_movimento = []
        for identificador in dict.fromkeys(ids_documentos):
            documento = docs.get(identificador)
            if documento is None:
                documento = {"id_documento": identificador, "status_acesso": "outro"}
            documentos_movimento.append(dict(documento))
        metadados: dict[str, Any] = {
            "indice_resposta_mni": indice,
            "codigo_nacional": codigo_nacional,
            "codigo_local": codigo_local,
            "codigo_pai_nacional": _texto(local.get("@codigoPaiNacional")),
            "id_movimento": _texto(movimento.get("@idMovimento")),
            "nivel_sigilo": _texto(movimento.get("@nivelSigilo")),
        }
        complementos_nacionais = _lista(nacional.get("complemento"))
        if complementos:
            metadados["complementos"] = complementos
        if complementos_nacionais:
            metadados["complementos_nacionais_mni"] = complementos_nacionais
        if movimento.get("movimentoNacional") is not None:
            metadados["movimento_nacional_mni"] = nacional
        if movimento.get("movimentoLocal") is not None:
            metadados["movimento_local_mni"] = local
        registro: dict[str, Any] = {
            "titulo": titulo,
            "teor": " ".join(complementos),
            "data": data["iso"],
            "data_original": data_original,
            "metadados": {
                chave: valor for chave, valor in metadados.items() if valor not in ("", None, [])
            },
        }
        if documentos_movimento:
            registro["documentos"] = documentos_movimento
        movimentos.append(registro)
    return movimentos


def _normalizar_documentos(documentos_mni: list[Any]) -> dict[str, list[dict[str, Any]]]:
    todos: list[dict[str, Any]] = []
    publicos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for item in documentos_mni:
        documento = _mapping(item)
        identificador = _texto(documento.get("idDocumento"))
        if not identificador or identificador in vistos:
            continue
        vistos.add(identificador)
        nivel_sigilo = _texto(documento.get("nivelSigilo"))
        conteudo = _mapping(documento.get("conteudo"))
        metadados: dict[str, Any] = {
            "nivel_sigilo_mni": nivel_sigilo,
            "codigo_tipo_documento_mni": _texto(documento.get("codigoTipoDocumento")),
            "hash_mni": _mapping(conteudo.get("hash")),
            "conteudo_binario_presente": bool(_texto(conteudo.get("conteudo"))),
        }
        registro: dict[str, Any] = {
            "id_documento": identificador,
            "titulo": _texto(documento.get("descricao")),
            "data_documento": normalizar_data(_texto(documento.get("dataHora")))["iso"],
            "mimetype": _texto(conteudo.get("mimetype")),
            "nivel_sigilo": nivel_sigilo,
            "codigo_tipo_documento": _texto(documento.get("codigoTipoDocumento")),
            "status_acesso": "publico_candidato" if nivel_sigilo == "0" else "outro",
            "metadados": {
                chave: valor for chave, valor in metadados.items() if valor not in ("", None, [])
            },
        }
        todos.append(registro)
        if nivel_sigilo == "0":
            publicos.append(registro)
    return {"todos_mni": todos, "publicos_candidatos_unicos": publicos}


def _mapping(valor: Any) -> Mapping[str, Any]:
    return valor if isinstance(valor, Mapping) else {}


def _campo(mapping: Mapping[str, Any], nome: str) -> Any:
    """Lê atributos XML como ``@numero`` e elementos como ``numero``."""
    return mapping.get(nome, mapping.get(f"@{nome}"))


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


def _booleano_mni(valor: Any) -> bool | None:
    texto = _texto(valor).casefold()
    if texto in {"true", "1"}:
        return True
    if texto in {"false", "0"}:
        return False
    return None
