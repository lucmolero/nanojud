from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from nanojud import normalizar_resposta_processo_mni
from nanojud.exceptions import AcessoRestrito, ConsultaIndisponivel, ProcessoNaoEncontrado
from nanojud.mni import MNI3Client, MNI3Config

CNJ = "1001194-30.2024.8.26.0114"
CNJ_DIGITOS = "10011943020248260114"
RESPOSTA = {
    "recibo": {
        "sucesso": "true",
        "mensagens": [{"descritivo": "Consulta concluída", "codigo": "0", "tipo": "INFORMACAO"}],
    },
    "processo": {
        "numeroProcesso": CNJ_DIGITOS,
        "dadosBasicos": {
            "dadosBasicos": {
                "numero": CNJ_DIGITOS,
                "classeProcessual": "7",
                "orgaoJulgador": {
                    "codigo": "1001",
                    "nome": "1ª Vara Cível",
                    "instancia": "ORIG",
                },
            },
            "classeProcessual": "7",
            "dataAjuizamento": "2024-01-15T10:30:00-03:00",
            "nivelSigilo": "0",
            "polo": [
                {
                    "@polo": "AT",
                    "parte": {
                        "pessoa": {
                            "dadosBasicos": {
                                "nome": "Parte autora",
                                "qualificacaoPessoa": "FIS",
                            }
                        },
                        "advogado": {
                            "@nome": "Advogada Exemplo",
                            "@inscricao": "12345/SP",
                            "@intimacao": "true",
                            "@tipoRepresentante": "A",
                        },
                    },
                },
                {
                    "@polo": "PA",
                    "parte": {
                        "pessoa": {
                            "dadosBasicos": {
                                "nome": "Parte ré",
                                "qualificacaoPessoa": "JUR",
                            }
                        }
                    },
                },
            ],
            "assunto": {"@principal": "true", "codigoNacional": "14918"},
            "valorCausa": "10000.00",
            "orgaoJulgador": {
                "codigo": "1001",
                "nome": "1ª Vara Cível",
                "instancia": "ORIG",
            },
            "outroParametro": [
                {"@nome": "situacao", "@valor": "MOVIMENTO"},
                {"@nome": "dataAutuacao", "@valor": "20240115103000"},
                {"@nome": "chave", "@valor": "SEGREDO-SENTINELA"},
            ],
        },
        "movimento": [
            {
                "@dataHora": "2026-11-12T10:00:00-03:00",
                "@nivelSigilo": "0",
                "movimentoNacional": {"@codigoNacional": "12345"},
                "complemento": "Petição juntada",
                "idDocumentoVinculado": "doc-1",
            },
            {
                "@dataHora": "2026-11-13T11:00:00-03:00",
                "movimentoLocal": {
                    "@codigoMovimento": "99",
                    "@codigoPaiNacional": "12345",
                    "@descricao": "Conclusos para decisão",
                },
            },
        ],
        "documento": {
            "idDocumento": "doc-1",
            "codigoTipoDocumento": "95",
            "dataHora": "2026-11-12T09:59:00-03:00",
            "nivelSigilo": "0",
            "descricao": "Petição inicial",
            "conteudo": {
                "idDocumento": "doc-1",
                "mimetype": "application/pdf",
                "encoding": "base64",
                "hash": {"hash": "abc123", "algoritmo": "SHA-256"},
                "conteudo": "UEZERi1TSU5URVRJQw==",
            },
        },
    },
}


def test_normaliza_resposta_mni_para_extrato_sem_inventar_rotulos():
    extrato = normalizar_resposta_processo_mni(
        CNJ,
        RESPOSTA,
        endpoint="https://mni.example.org/Servico.svc",
        tribunal="TJSP",
        grau="1G",
        incluir_documentos=True,
        movimentacoes_completas=True,
    )

    assert extrato["status"] == "ok"
    assert extrato["dados_basicos"]["numero"] == CNJ
    assert extrato["dados_basicos"]["classe_codigo"] == "7"
    assert extrato["dados_basicos"]["assunto_codigo"] == "14918"
    assert extrato["dados_basicos"]["vara"] == "1ª Vara Cível"
    assert extrato["dados_basicos"]["situacao"] == "MOVIMENTO"
    assert extrato["partes"]["polo_ativo"][0]["nomes"] == ["Parte autora"]
    assert extrato["partes"]["polo_passivo"][0]["nomes"] == ["Parte ré"]
    assert extrato["partes"]["polo_ativo"][0]["advogados"] == ["Advogada Exemplo"]
    assert extrato["movimentacoes"][0]["titulo"] == "Movimento CNJ 12345"
    assert extrato["movimentacoes"][0]["teor"] == "Petição juntada"
    assert extrato["movimentacoes"][0]["data"] == "2026-11-12"
    assert extrato["movimentacoes"][1]["titulo"] == "Conclusos para decisão"
    assert extrato["movimentacoes"][0]["documentos"][0]["id_documento"] == "doc-1"
    documento = extrato["documentos"]["publicos_candidatos_unicos"][0]
    assert documento["titulo"] == "Petição inicial"
    assert documento["mimetype"] == "application/pdf"
    assert "UEZERi1TSU5URVRJQw==" not in repr(extrato)
    assert "SEGREDO-SENTINELA" not in repr(extrato)
    assert extrato["origem"]["endpoint_host"] == "mni.example.org"
    assert extrato["origem"]["tribunal"] == "TJSP"
    assert extrato["origem"]["movimentacoes_completas"] is True


def test_normaliza_resposta_mni_com_estado_parcial_sem_garantia_de_completude():
    extrato = normalizar_resposta_processo_mni(CNJ, RESPOSTA, endpoint="https://mni.example.org/s")

    assert extrato["status"] == "partial"
    assert extrato["origem"]["movimentacoes_completas"] is False
    assert extrato["origem"]["aviso_movimentacoes"]
    assert extrato["origem"]["aviso_documentos"]


def test_rejeita_numero_de_processo_mni_divergente():
    resposta = deepcopy(RESPOSTA)
    resposta["processo"]["numeroProcesso"] = "41675175420268260000"

    with pytest.raises(ConsultaIndisponivel, match="diferente"):
        normalizar_resposta_processo_mni(CNJ, resposta, endpoint="https://mni.example.org/s")


def test_nao_classifica_ausencia_de_elemento_processo_como_nao_encontrado():
    resposta = {"recibo": {"sucesso": "true", "mensagens": []}}

    with pytest.raises(ConsultaIndisponivel, match="não incluiu os dados do processo"):
        normalizar_resposta_processo_mni(CNJ, resposta, endpoint="https://mni.example.org/s")


def test_classifica_mensagem_explicita_de_nao_encontrado():
    resposta = {
        "recibo": {
            "sucesso": "false",
            "mensagens": [{"descritivo": "Processo não encontrado", "tipo": "ERRO"}],
        }
    }

    with pytest.raises(ProcessoNaoEncontrado):
        normalizar_resposta_processo_mni(CNJ, resposta, endpoint="https://mni.example.org/s")


def test_classifica_resposta_mni_restrita_por_sigilo():
    resposta = {
        "recibo": {
            "sucesso": "false",
            "mensagens": [{"descritivo": "Processo com segredo de justiça", "tipo": "ERRO"}],
        }
    }

    with pytest.raises(AcessoRestrito):
        normalizar_resposta_processo_mni(CNJ, resposta, endpoint="https://mni.example.org/s")


def test_rejeita_recibo_sem_indicador_de_sucesso():
    resposta = {"recibo": {"mensagens": []}, "processo": RESPOSTA["processo"]}

    with pytest.raises(ConsultaIndisponivel, match="recibo MNI inválido"):
        normalizar_resposta_processo_mni(CNJ, resposta, endpoint="https://mni.example.org/s")


def test_consultar_extrato_client_conecta_soap_ao_contrato_normalizado():
    soap = f"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:mni="http://www.cnj.jus.br/mni/v300/"
        xmlns:tipo="http://www.cnj.jus.br/mni/v300/tipos-servico-intercomunicacao"
        xmlns:inter="http://www.cnj.jus.br/mni/v300/intercomunicacao">
      <soap:Body><mni:respostaConsultarProcesso>
        <tipo:recibo><inter:sucesso>true</inter:sucesso><inter:mensagens>
          <inter:descritivo>Consulta concluída</inter:descritivo><inter:codigo>0</inter:codigo>
          <inter:codigoUnico/><inter:tipo>INFORMACAO</inter:tipo>
        </inter:mensagens></tipo:recibo>
        <tipo:processo><inter:numeroProcesso>{CNJ_DIGITOS}</inter:numeroProcesso>
          <inter:dadosBasicos><inter:dadosBasicos><inter:numero>{CNJ_DIGITOS}</inter:numero>
            <inter:classeProcessual>7</inter:classeProcessual>
            <inter:orgaoJulgador><inter:codigo>1</inter:codigo><inter:nome>Vara Cível</inter:nome>
              <inter:instancia>ORIG</inter:instancia></inter:orgaoJulgador>
          </inter:dadosBasicos><inter:classeProcessual>7</inter:classeProcessual>
          <inter:nivelSigilo>0</inter:nivelSigilo>
          <inter:dataAjuizamento>2024-01-15T10:30:00-03:00</inter:dataAjuizamento>
        </inter:dadosBasicos><inter:movimento dataHora="2026-11-12T10:00:00-03:00">
          <inter:movimentoLocal codigoMovimento="99" codigoPaiNacional="123"
            descricao="Conclusos para decisão"/>
        </inter:movimento></tipo:processo>
      </mni:respostaConsultarProcesso></soap:Body></soap:Envelope>""".encode()

    class Response:
        status_code = 200

        def iter_content(self, chunk_size):
            assert chunk_size > 0
            yield soap

        def close(self):
            return None

    class Session:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return Response()

    session = Session()
    client = MNI3Client(
        MNI3Config(endpoint="https://mni.example.org/Servico.svc", token="token"),
        session=session,  # type: ignore[arg-type]
    )

    extrato = client.consultar_extrato(CNJ, tribunal="TJSP", grau="1G")

    assert extrato["status"] == "partial"
    assert extrato["origem"]["tribunal"] == "TJSP"
    assert extrato["origem"]["grau"] == "1G"
    assert extrato["dados_basicos"]["numero"] == CNJ
    assert extrato["movimentacoes"][0]["titulo"] == "Conclusos para decisão"
    request = session.calls[0]["data"]
    assert isinstance(request, bytes)
    request_root = ET.fromstring(request)
    movimentos = [
        element for element in request_root.iter() if element.tag.endswith("}incluirMovimentos")
    ]
    assert len(movimentos) == 1
    assert movimentos[0].text == "true"
