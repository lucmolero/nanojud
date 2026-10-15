import subprocess
import sys

import pytest

from nanojud import cli, formatacao
from nanojud.exceptions import ConsultaIndisponivel, FormatoCNJInvalido, ProcessoNaoEncontrado

TJSP = "1076539-20.2019.8.26.0100"


def _rodar(*args):
    return subprocess.run(
        [sys.executable, "-m", "nanojud", *args], capture_output=True, text=True, encoding="utf-8"
    )


# --- ajuda e erros de uso em português ------------------------------------------------------


def test_python_m_nanojud_funciona_e_mostra_versao():
    resultado = _rodar("--versao")

    assert resultado.returncode == 0
    assert resultado.stdout.startswith("nanojud ")


def test_ajuda_em_portugues_com_exemplos():
    resultado = _rodar("--ajuda")

    assert resultado.returncode == 0
    saida = resultado.stdout
    assert "uso: nanojud" in saida and "uso: uso:" not in saida
    assert "comandos" in saida and "opções" in saida
    assert "exemplos:" in saida and "nanojud consultar" in saida
    for ingles in ("usage:", "options:", "positional arguments"):
        assert ingles not in saida


def test_comando_sem_numero_explica_o_que_faltou():
    resultado = _rodar("consultar")

    assert resultado.returncode == 2
    assert "erro: faltou informar: numero" in resultado.stderr
    assert "the following arguments" not in resultado.stderr


def test_comando_inexistente_lista_os_validos():
    resultado = _rodar("pesquisar")

    assert resultado.returncode == 2
    assert "valor inválido 'pesquisar'" in resultado.stderr
    assert "consultar" in resultado.stderr


def test_valor_nao_inteiro_e_traduzido():
    resultado = _rodar("linha-do-tempo", TJSP, "--limite", "muitos")

    assert resultado.returncode == 2
    assert "não é um número inteiro" in resultado.stderr


@pytest.mark.parametrize(
    "apelido, original",
    [
        (["consultar", TJSP], "search"),
        (["linha-do-tempo", TJSP], "timeline"),
        (["extrair", TJSP], "extract"),
    ],
)
def test_apelidos_em_portugues_chamam_o_mesmo_comando(apelido, original):
    args = cli._montar_parser().parse_args(apelido)

    assert args.command == original


def test_opcoes_em_portugues_da_linha_do_tempo():
    args = cli._montar_parser().parse_args(
        ["linha-do-tempo", TJSP, "--fonte", "djen", "--limite", "7", "--recentes-primeiro"]
    )

    assert (args.source, args.limit, args.recent_first) == (["djen"], 7, True)


# --- formato texto e json ---------------------------------------------------------------------


def _resumo():
    return {
        "numero": TJSP,
        "classe": "Procedimento Comum",
        "assunto": "Contratos",
        "foro": "Foro Central",
        "vara": "2ª Vara Cível",
        "juiz": "Dr. Exemplo",
        "situacao": "Extinto",
        "ultima_movimentacao": "Juntada de petição",
        "ultima_data": "10/01/2026",
        "url": "https://esaj.tjsp.jus.br/x",
        "fonte": "esaj",
    }


def test_search_em_texto_e_legivel(monkeypatch, capsys):
    monkeypatch.setattr(cli.api, "search_processo", lambda numero: _resumo())

    cli.main(["consultar", TJSP, "--formato", "texto"])
    saida = capsys.readouterr().out

    assert "Processo 1076539-20.2019.8.26.0100" in saida
    assert "Situação:" in saida and "Extinto" in saida
    assert "Última movimentação:" in saida and "10/01/2026" in saida
    assert "{" not in saida  # nada de JSON


def test_search_redirecionado_continua_json(monkeypatch, capsys):
    monkeypatch.setattr(cli.api, "search_processo", lambda numero: _resumo())

    cli.main(["consultar", TJSP])  # pytest captura a saída: não é terminal

    assert '"classe": "Procedimento Comum"' in capsys.readouterr().out


def test_formato_auto_usa_texto_no_terminal(monkeypatch, capsys):
    monkeypatch.setattr(cli.api, "search_processo", lambda numero: _resumo())
    monkeypatch.setattr(cli, "_terminal", lambda: True)

    cli.main(["consultar", TJSP])

    assert "Classe:" in capsys.readouterr().out


def test_texto_com_out_grava_o_arquivo_legivel(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.api, "search_processo", lambda numero: _resumo())
    destino = tmp_path / "resumo.txt"

    cli.main(["consultar", TJSP, "--formato", "texto", "--out", str(destino)])

    assert "Classe:" in destino.read_text(encoding="utf-8")
    assert "salvo em" in capsys.readouterr().out


def test_partes_agrupa_por_polo_com_advogados():
    texto = formatacao.texto_partes(
        {
            "polo_ativo": [{"tipo": "Reqte", "nomes": ["Ana"], "advogados": ["Dr. Bruno"]}],
            "polo_passivo": [{"tipo": "Reqdo", "nomes": ["Município"], "advogados": []}],
        }
    )

    assert texto.index("POLO ATIVO") < texto.index("POLO PASSIVO")
    assert "Advogado(a): Dr. Bruno" in texto


def test_partes_vazias_dizem_que_nao_ha_partes():
    assert "Nenhuma parte" in formatacao.texto_partes({})


def test_timeline_em_texto_usa_data_brasileira_e_fonte():
    texto = formatacao.texto_timeline(
        [
            {"data": "2026-08-23", "fonte": "esaj", "titulo": "Certidão", "texto": "Detalhe"},
            {"data": "2026-08-18", "fonte": "datajud", "grau": "G1", "titulo": "Remessa"},
        ]
    )

    assert "23/08/2026" in texto and "eSAJ" in texto
    assert "DataJud G1" in texto
    assert "2 evento(s)" in texto


def test_timeline_vazia_explica():
    assert "Nenhum evento" in formatacao.texto_timeline([])


def test_djen_em_texto_destaca_incidente():
    texto = formatacao.texto_comunicacoes(
        [
            {
                "dataDisponibilizacao": "2026-08-18",
                "tipoComunicacao": "Intimação",
                "incidente": "47",
                "nomeOrgao": "7ª Vara",
                "texto": "Processo X " * 60,
            }
        ]
    )

    assert "18/08/2026" in texto and "incidente /47" in texto
    assert "…" in texto  # texto longo é cortado


# --- erros com dica ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "erro, trecho",
    [
        (FormatoCNJInvalido("Número CNJ deve ter 20 dígitos."), "20 dígitos"),
        (ProcessoNaoEncontrado("x"), "sigiloso"),
        (ConsultaIndisponivel("x"), "Aguarde alguns minutos"),
    ],
)
def test_erro_em_texto_traz_o_que_fazer(monkeypatch, capsys, erro, trecho):
    def falha(numero):
        raise erro

    monkeypatch.setattr(cli.api, "search_processo", falha)

    codigo = cli.main(["consultar", TJSP, "--formato", "texto"])
    saida = capsys.readouterr()

    assert codigo == 2
    assert "Erro:" in saida.err and "O que fazer:" in saida.err and trecho in saida.err


def test_erro_redirecionado_continua_json_com_dica(monkeypatch, capsys):
    def falha(numero):
        raise ProcessoNaoEncontrado("x")

    monkeypatch.setattr(cli.api, "search_processo", falha)

    cli.main(["consultar", TJSP])

    assert '"dica"' in capsys.readouterr().out


def test_arquivo_de_extrato_inexistente_tem_mensagem_em_portugues(capsys):
    codigo = cli.main(["ler-pecas", "nao_existe.json"])

    assert codigo == 2
    saida = capsys.readouterr().out
    assert "não existe" in saida and "No such file" not in saida


def test_arquivo_de_extrato_invalido(tmp_path, capsys):
    arquivo = tmp_path / "ruim.json"
    arquivo.write_text("isto nao e json", encoding="utf-8")

    codigo = cli.main(["ler-pecas", str(arquivo)])

    assert codigo == 2
    assert "JSON válido" in capsys.readouterr().out


def test_ctrl_c_encerra_com_mensagem(monkeypatch, capsys):
    def interrompe(numero):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.api, "search_processo", interrompe)

    assert cli.main(["consultar", TJSP]) == 130
    assert "interrompida" in capsys.readouterr().err


def test_linha_do_tempo_nao_avisa_do_corte_que_a_propria_cli_escolheu(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api,
        "extract_process",
        lambda numero, **kw: {
            "timeline": [{"data": "2026-01-01", "fonte": "esaj", "titulo": "Juntada"}],
            "warnings": ["eSAJ: Movimentações limitadas a 5; o eSAJ tem mais registros."],
            "errors": [],
        },
    )

    cli.main(["linha-do-tempo", TJSP, "--recentes-primeiro", "--limite", "3", "--formato", "texto"])

    assert "Movimentações limitadas" not in capsys.readouterr().out


def test_mensagens_de_arquivo_gravado_concordam_em_genero(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.api, "get_partes", lambda numero: {})
    destino = tmp_path / "partes.txt"

    cli.main(["partes", TJSP, "--out", str(destino)])

    assert "Partes salvas em:" in capsys.readouterr().out


def test_ler_pecas_sem_leitor_de_pdf_diz_como_instalar(monkeypatch):
    from nanojud import esaj

    monkeypatch.setattr(
        esaj, "extrair_texto_pdf_bytes", lambda c, max_chars=0: ("", "pdf_parser_indisponivel")
    )

    class Sessao:
        def get(self, url, **kwargs):
            class R:
                content = b"%PDF-1.4 ..."
                text = ""
                headers = {"Content-Type": "application/pdf"}
                status_code = 200

            return R()

    doc = {
        "cd_documento": "1",
        "titulo": "Sentença",
        "status_acesso": "publico_candidato",
        "pasta_digital": {"status": "ok", "paginas": [{"parametros_pdf": "a=1"}]},
    }

    leitura = esaj.ler_pecas_publicas(Sessao(), [{"documentos": [doc]}])

    assert leitura[0]["status"] == "pdf_parser_indisponivel"
    assert "nanojud[pdf]" in leitura[0]["mensagem"]
