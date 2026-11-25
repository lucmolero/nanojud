import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nanojud import cli

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"


def test_cli_help():
    env = os.environ.copy()
    anterior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(SRC), anterior)))
    result = subprocess.run(
        [sys.executable, "-m", "nanojud.cli", "--help"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "datajud" in result.stdout
    assert "timeline" in result.stdout


def test_cli_extract_aceita_fonte_mni_sem_chamar_portal():
    args = cli._montar_parser().parse_args(
        ["extract", "1001194-30.2024.8.26.0114", "--source", "mni"]
    )

    assert args.command == "extract"
    assert args.source == ["mni"]


def test_cli_search_imprime_json(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api,
        "search_processo",
        lambda numero: {"status": "ok", "numero": numero},
    )

    status = cli.main(["search", "1076539-20.2019.8.26.0100"])

    assert status == 0
    assert '"status": "ok"' in capsys.readouterr().out


@pytest.mark.parametrize(("status", "codigo"), [("ok", 0), ("partial", 1), ("error", 1)])
def test_cli_extract_reflete_status_no_codigo_de_saida(monkeypatch, capsys, status, codigo):
    avisos = []
    monkeypatch.setattr(cli, "_avisar", avisos.append)
    monkeypatch.setattr(
        cli.api,
        "extract_process",
        lambda *args, **kwargs: {"status": status, "source_status": {}, "data": {}},
    )

    resultado = cli.main(["extract", "5060583-19.2021.8.13.0024", "--source", "pje_tjmg"])

    assert resultado == codigo
    assert f'"status": "{status}"' in capsys.readouterr().out
    assert avisos == ["Consultando fontes selecionadas: pje_tjmg... (até 1 minuto)"]


def test_cli_extract_repassa_timeout_por_fonte(monkeypatch, capsys):
    chamadas = {}

    def extrair(numero, **kwargs):
        chamadas.update(kwargs)
        return {"status": "ok", "source_status": {}, "data": {}}

    monkeypatch.setattr(cli.api, "extract_process", extrair)
    assert (
        cli.main(["extract", "5060583-19.2021.8.13.0024", "--source", "pje_tjmg", "--timeout", "9"])
        == 0
    )
    capsys.readouterr()
    assert chamadas["timeout"] == 9


def test_comando_sem_out_imprime_json_na_tela(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli.api,
        "consultar_djen_detalhado",
        lambda numero, data_inicio="": {
            "status": "ok",
            "completo": True,
            "paginas": 1,
            "comunicacoes": [{"id": 1}],
            "avisos": [],
        },
    )

    codigo = cli.main(["djen", "1076539-20.2019.8.26.0100"])

    assert codigo == 0
    assert json.loads(capsys.readouterr().out)["comunicacoes"] == [{"id": 1}]
    assert list(tmp_path.iterdir()) == []


def test_comando_com_out_grava_arquivo(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        cli.api,
        "consultar_djen_detalhado",
        lambda numero, data_inicio="": {
            "status": "ok",
            "completo": True,
            "paginas": 1,
            "comunicacoes": [{"id": 1}],
            "avisos": [],
        },
    )
    destino = tmp_path / "djen.json"

    cli.main(["djen", "1076539-20.2019.8.26.0100", "--out", str(destino)])

    assert json.loads(destino.read_text(encoding="utf-8"))["comunicacoes"] == [{"id": 1}]
    assert "DJEN salvo em" in capsys.readouterr().out


def test_cli_djen_exibe_estado_parcial_preservando_comunicacoes(monkeypatch, capsys):
    resultado = {
        "status": "partial",
        "completo": False,
        "paginas": 1,
        "comunicacoes": [{"id": "1", "texto": "comunicação preservada"}],
        "avisos": ["A página seguinte falhou."],
    }
    monkeypatch.setattr(cli.api, "consultar_djen_detalhado", lambda *args, **kwargs: resultado)

    codigo = cli.main(["djen", "1076539-20.2019.8.26.0100", "--formato", "json"])

    saida = json.loads(capsys.readouterr().out)
    assert codigo == 1
    assert saida["status"] == "partial"
    assert saida["comunicacoes"] == resultado["comunicacoes"]
    assert saida["avisos"] == resultado["avisos"]


def test_cli_djen_em_texto_exibe_status_parcial_e_aviso(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api,
        "consultar_djen_detalhado",
        lambda *args, **kwargs: {
            "status": "partial",
            "completo": False,
            "paginas": 1,
            "comunicacoes": [{"id": "1", "texto": "comunicação preservada"}],
            "avisos": ["A página seguinte falhou."],
        },
    )

    codigo = cli.main(["djen", "1076539-20.2019.8.26.0100", "--formato", "texto"])

    saida = capsys.readouterr().out
    assert codigo == 1
    assert "DJEN: partial" in saida
    assert "A página seguinte falhou." in saida
    assert "comunicação preservada" in saida


def test_cli_tabela_exporta_timeline_com_proveniencia(tmp_path, capsys):
    entrada = tmp_path / "extracao.json"
    saida = tmp_path / "timeline.csv"
    entrada.write_text(
        json.dumps(
            {
                "status": "partial",
                "numero_cnj": "1076539-20.2019.8.26.0100",
                "timeline": [
                    {
                        "id": "evt-1",
                        "numero_cnj": "1076539-20.2019.8.26.0100",
                        "fonte": "djen",
                        "data": "2026-01-02",
                        "titulo": "Intimação",
                    }
                ],
                "source_status": {"djen": {"status": "partial"}},
            }
        ),
        encoding="utf-8",
    )

    codigo = cli.main(["tabela", str(entrada), "--out", str(saida)])

    assert codigo == 0
    assert "row_count=1" in capsys.readouterr().out
    csv_text = saida.read_text(encoding="utf-8")
    assert "numero_cnj" in csv_text
    assert "fonte" in csv_text
    assert "status_fonte" in csv_text
    assert "partial" in csv_text
    assert "1076539-20.2019.8.26.0100" in csv_text


def test_batch_cli_usa_tres_tentativas_datajud_por_padrao():
    args = cli._montar_parser().parse_args(["batch", "processos.txt"])

    assert args.datajud_retries == 3


def test_batch_cli_persiste_jsonl_e_retorna_codigo_de_saida(monkeypatch, tmp_path, capsys):
    from nanojud import api

    entrada = tmp_path / "cnjs.txt"
    entrada.write_text("1076539-20.2019.8.26.0100\n# comentario\ninvalido\n", encoding="utf-8")
    saida = tmp_path / "resultados.jsonl"
    monkeypatch.setattr(
        api,
        "iter_extract_processes",
        lambda numeros, **kwargs: iter(
            [
                {"index": 0, "input": "cnj", "status": "ok"},
                {"index": 1, "input": "invalido", "status": "error"},
            ]
        ),
    )

    codigo = cli.main(["batch", str(entrada), "--out", str(saida)])

    assert codigo == 1
    linhas = saida.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2
    assert '"status":"error"' in linhas[1]
    assert "registros: 2; falhas: 1" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("opcoes", "esperadas"),
    [([], ("esaj", "datajud", "djen")), (["--source", "pje_tjmg"], ("pje_tjmg",))],
)
def test_batch_cli_mantem_pje_optin_por_padrao(monkeypatch, tmp_path, opcoes, esperadas):
    from nanojud import api

    entrada = tmp_path / "processos.txt"
    entrada.write_text("5060583-19.2021.8.13.0024\n", encoding="utf-8")
    chamadas = {}

    def extrair(numeros, **kwargs):
        chamadas.update(kwargs)
        return iter([])

    monkeypatch.setattr(api, "iter_extract_processes", extrair)

    assert cli.main(["batch", str(entrada), *opcoes]) == 0
    assert tuple(chamadas["sources"]) == esperadas


def test_autos_cli_grava_manifesto_incremental(monkeypatch, tmp_path):
    from nanojud import api

    entrada = tmp_path / "cnjs.txt"
    entrada.write_text("1076539-20.2019.8.26.0100\n", encoding="utf-8")
    manifesto = tmp_path / "manifesto.jsonl"
    chamados = {}

    def consultar(numeros, **kwargs):
        chamados.update(kwargs)
        return iter([{"index": 0, "input": next(iter(numeros)), "status": "no_documents"}])

    monkeypatch.setattr(api, "iter_extract_dockets", consultar)
    codigo = cli.main(
        ["autos", str(entrada), "--out-dir", str(tmp_path / "autos"), "--out", str(manifesto)]
    )

    assert codigo == 0
    assert '"status":"no_documents"' in manifesto.read_text(encoding="utf-8")
    assert chamados["destination"] == str(tmp_path / "autos")


def test_autos_cli_repassa_timeout_por_requisicao(monkeypatch, tmp_path):
    from nanojud import api

    entrada = tmp_path / "cnjs.txt"
    entrada.write_text("1076539-20.2019.8.26.0100\n", encoding="utf-8")
    chamados = {}

    def consultar(numeros, **kwargs):
        chamados.update(kwargs)
        return iter([])

    monkeypatch.setattr(api, "iter_extract_dockets", consultar)
    assert (
        cli.main(["autos", str(entrada), "--out-dir", str(tmp_path / "autos"), "--timeout", "9"])
        == 0
    )
    assert chamados["timeout"] == 9


@pytest.mark.parametrize("timeout", ["0", "nan", "inf", "86401"])
def test_cli_rejeita_timeout_invalido_antes_de_executar(monkeypatch, tmp_path, timeout):
    from nanojud import api

    monkeypatch.setattr(api, "iter_extract_dockets", lambda *args, **kwargs: pytest.fail())
    with pytest.raises(SystemExit) as erro:
        cli.main(
            ["autos", "entrada.txt", "--out-dir", str(tmp_path / "autos"), "--timeout", timeout]
        )
    assert erro.value.code == 2


def test_autos_cli_preserva_manifesto_se_login_assistido_falhar(monkeypatch, tmp_path):
    from nanojud import autenticacao
    from nanojud.exceptions import AcessoRestrito

    entrada = tmp_path / "cnjs.txt"
    entrada.write_text("1076539-20.2019.8.26.0100\n", encoding="utf-8")
    manifesto = tmp_path / "manifesto.jsonl"
    manifesto.write_text("resultado anterior\n", encoding="utf-8")

    def falhar_login(**kwargs):
        raise AcessoRestrito("Login não concluído.")

    monkeypatch.setattr(autenticacao, "autenticar_esaj_no_navegador", falhar_login)

    codigo = cli.main(
        [
            "autos",
            str(entrada),
            "--out-dir",
            str(tmp_path / "autos"),
            "--out",
            str(manifesto),
            "--autenticar-advogado",
        ]
    )

    assert codigo == 2
    assert manifesto.read_text(encoding="utf-8") == "resultado anterior\n"


@pytest.mark.parametrize("comando", ["batch", "autos"])
def test_lotes_nao_truncam_arquivo_de_entrada_usado_como_saida(
    monkeypatch, tmp_path, capsys, comando
):
    from nanojud import api

    entrada = tmp_path / "processos.txt"
    conteudo = "1076539-20.2019.8.26.0100\n"
    entrada.write_text(conteudo, encoding="utf-8")
    monkeypatch.setattr(
        api,
        "iter_extract_processes",
        lambda *args, **kwargs: pytest.fail("não deve iniciar consulta"),
    )
    monkeypatch.setattr(
        api,
        "iter_extract_dockets",
        lambda *args, **kwargs: pytest.fail("não deve iniciar consulta"),
    )
    argumentos = [comando, str(entrada)]
    if comando == "autos":
        argumentos.extend(["--out-dir", str(tmp_path / "autos")])
    argumentos.extend(["--out", str(entrada)])

    codigo = cli.main(argumentos)

    assert codigo == 2
    assert entrada.read_text(encoding="utf-8") == conteudo
    assert "arquivo de saída" in capsys.readouterr().out


@pytest.mark.parametrize("comando", ["batch", "autos"])
def test_erro_utf8_em_lote_preserva_jsonl_e_vai_para_stderr(monkeypatch, tmp_path, capsys, comando):
    from nanojud import api

    entrada = tmp_path / "processos.txt"
    entrada.write_bytes(b"1076539-20.2019.8.26.0100\n#" + b"x" * 9000 + b"\n\xff\n")

    def consumir(numeros, **kwargs):
        return (
            {"index": index, "input": numero, "status": "ok"}
            for index, numero in enumerate(numeros)
        )

    monkeypatch.setattr(api, "iter_extract_processes", consumir)
    monkeypatch.setattr(api, "iter_extract_dockets", consumir)
    argumentos = [comando, str(entrada)]
    if comando == "autos":
        argumentos.extend(["--out-dir", str(tmp_path / "autos")])

    codigo = cli.main(argumentos)

    saida = capsys.readouterr()
    linhas = saida.out.splitlines()
    assert codigo == 2
    assert len(linhas) == 1
    assert json.loads(linhas[0])["status"] == "ok"
    assert "UTF-8" in saida.err
