"""Identificacao padronizada das fontes de extracao."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

SourceName = Literal[
    "esaj",
    "datajud",
    "djen",
    "pje_tjmg",
    "esaj_tjsp_2g",
    "eproc_tjsp_1g",
    "eproc_tjsp_2g",
    "mni",
    "tjrj_1g",
]

ESAJ: SourceName = "esaj"
DATAJUD: SourceName = "datajud"
DJEN: SourceName = "djen"
PJE_TJMG: SourceName = "pje_tjmg"
ESAJ_TJSP_2G: SourceName = "esaj_tjsp_2g"
EPROC_TJSP_1G: SourceName = "eproc_tjsp_1g"
EPROC_TJSP_2G: SourceName = "eproc_tjsp_2g"
MNI: SourceName = "mni"
TJRJ_1G: SourceName = "tjrj_1g"

# Keep newly discovered court portals opt-in until their pagination and document
# coverage is verified. ALL_SOURCES is the stable, default extraction profile.
ALL_SOURCES: tuple[SourceName, ...] = (ESAJ, DATAJUD, DJEN)
AVAILABLE_SOURCES: tuple[SourceName, ...] = (
    *ALL_SOURCES,
    PJE_TJMG,
    ESAJ_TJSP_2G,
    EPROC_TJSP_1G,
    EPROC_TJSP_2G,
    MNI,
    TJRJ_1G,
)

SOURCE_DESCRIPTIONS: dict[SourceName, str] = {
    ESAJ: "e-SAJ/TJSP: consulta processual de primeiro grau (CPoPG).",
    ESAJ_TJSP_2G: "e-SAJ/TJSP: consulta processual de segundo grau (CPoSG), sob seleção explícita.",
    DATAJUD: "DataJud/CNJ: API nacional de metadados por alias oficial de tribunal.",
    DJEN: "DJEN/CNJ: publicações nacionais, sem acesso aos autos.",
    PJE_TJMG: ("PJe/TJMG: consulta pública de primeiro grau; percorre até 100 páginas por tabela."),
    EPROC_TJSP_1G: "eproc/TJSP: consulta pública de primeiro grau pela interface oficial.",
    EPROC_TJSP_2G: "eproc/TJSP: consulta pública de segundo grau pela Consulta Unificada.",
    MNI: "MNI 3.0: protocolo geral; consulta remota de uma instalação configurada.",
    TJRJ_1G: "TJRJ: consulta pública de primeiro grau pela SPA oficial.",
}


def normalizar_fonte(fonte: str) -> SourceName:
    """Normaliza e valida uma fonte conhecida pela biblioteca."""
    valor = fonte.strip().lower()
    if valor not in AVAILABLE_SOURCES:
        permitidas = ", ".join(AVAILABLE_SOURCES)
        raise ValueError(f"Fonte desconhecida: {fonte!r}. Use uma de: {permitidas}.")
    return valor  # type: ignore[return-value]


def normalizar_fontes(fontes: Iterable[str] | None = None) -> tuple[SourceName, ...]:
    """Aplica o padrão apenas quando fontes foram omitidas e rejeita seleção vazia."""
    if fontes is None:
        return ALL_SOURCES
    normalizadas = tuple(dict.fromkeys(normalizar_fonte(fonte) for fonte in fontes))
    if not normalizadas:
        raise ValueError("Selecione ao menos uma fonte para consultar.")
    return normalizadas
