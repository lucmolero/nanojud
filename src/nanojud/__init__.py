"""nanojud package

Expose main modules:
- `api` : highest-level operations for lawyers and systems
- `esaj` : eSAJ extraction helpers
- `datajud` : DataJud/CNJ structured process data helpers
- `djen` : DJEN communication helpers
- `utils`: helper utilities
"""

from . import (
    api,
    autenticacao,
    batch,
    cache,
    client,
    config,
    datajud,
    djen,
    eproc_tjsp,
    esaj,
    exceptions,
    exports,
    extraction,
    mni,
    mni_222,
    models,
    normalization,
    pje_tjmg,
    schemas,
    sources,
    timeline,
    tjmg_legado,
    tjrj,
    utils,
)
from .client import NanoJudClient
from .config import NanoJudConfig
from .mni import MNI3Client, MNI3Config
from .mni_222 import MNI222Client, MNI222Config, MNIConfig
from .mni_normalizacao import normalizar_resposta_processo_mni
from .version import __version__

__all__ = [
    "NanoJudClient",
    "NanoJudConfig",
    "api",
    "autenticacao",
    "batch",
    "cache",
    "client",
    "config",
    "datajud",
    "djen",
    "eproc_tjsp",
    "esaj",
    "exceptions",
    "extraction",
    "exports",
    "models",
    "mni",
    "mni_222",
    "MNI3Client",
    "MNI3Config",
    "MNI222Client",
    "MNI222Config",
    "MNIConfig",
    "normalizar_resposta_processo_mni",
    "normalization",
    "pje_tjmg",
    "schemas",
    "sources",
    "timeline",
    "tjrj",
    "tjmg_legado",
    "utils",
    "__version__",
]
