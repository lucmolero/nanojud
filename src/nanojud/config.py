"""Configuração de clientes nanojud."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NanoJudConfig:
    """Configuração operacional para uso corporativo e automações recorrentes."""

    timeout: float = 30.0
    rate_limit_interval: float = 0.0
    cache_enabled: bool = False
    cache_dir: Path = Path(".nanojud_cache")
    cache_ttl_seconds: int = 24 * 60 * 60
    salvar_html: bool = False
    limite_movimentacoes: int | None = 100
    pausa_paginas: float = 0.5
    datajud_api_key: str | None = None
    user_agent: str = (
        "Mozilla/5.0 (compatible; nanojud/{version}; +https://github.com/lucmolero/nanojud)"
    )

    def resolved_user_agent(self, version: str) -> str:
        return self.user_agent.format(version=version)
