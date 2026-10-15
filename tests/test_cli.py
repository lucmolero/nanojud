import os
import subprocess
import sys
from pathlib import Path

from nanojud import cli

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"


def test_cli_help():
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(SRC))
    result = subprocess.run(
        [sys.executable, "-m", "nanojud.cli", "--help"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "datajud" in result.stdout
    assert "timeline" in result.stdout


def test_cli_search_imprime_json(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.api,
        "search_processo",
        lambda numero: {"status": "ok", "numero": numero},
    )

    status = cli.main(["search", "1076539-20.2019.8.26.0100"])

    assert status == 0
    assert '"status": "ok"' in capsys.readouterr().out


def test_comando_sem_out_imprime_json_na_tela(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.api, "consultar_djen", lambda numero, data_inicio="": [{"id": 1}])

    codigo = cli.main(["djen", "1076539-20.2019.8.26.0100"])

    assert codigo == 0
    assert '"id": 1' in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_comando_com_out_grava_arquivo(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.api, "consultar_djen", lambda numero, data_inicio="": [{"id": 1}])
    destino = tmp_path / "djen.json"

    cli.main(["djen", "1076539-20.2019.8.26.0100", "--out", str(destino)])

    assert '"id": 1' in destino.read_text(encoding="utf-8")
    assert "DJEN salvo em" in capsys.readouterr().out
