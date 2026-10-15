import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def sem_ritmo_do_esaj(monkeypatch):
    """Os testes não esperam o intervalo mínimo entre consultas ao eSAJ."""
    monkeypatch.setattr("nanojud.esaj.INTERVALO_CONSULTAS", 0.0)
    monkeypatch.setattr("nanojud.esaj.ESPERA_BLOQUEIO", 0.0)
