"""Configuração de clientes nanojud."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mni_222 import MNIConfig
from .utils import validar_timeout, validar_ttl_cache


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
    mni_config: MNIConfig | None = None
    user_agent: str = (
        "Mozilla/5.0 (compatible; nanojud/{version}; +https://github.com/lucmolero/nanojud)"
    )

    def __post_init__(self) -> None:
        validar_timeout(self.timeout)
        validar_ttl_cache(self.cache_ttl_seconds)
        if self.mni_config is not None and not isinstance(self.mni_config, MNIConfig):
            raise ValueError("mni_config deve ser MNI3Config, MNI222Config ou None.")

    def resolved_user_agent(self, version: str) -> str:
        return self.user_agent.format(version=version)
