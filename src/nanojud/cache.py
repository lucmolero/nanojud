"""Cache local simples, explícito e seguro por padrão."""

from __future__ import annotations

import json
import math
import tempfile
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

from .utils import validar_ttl_cache


class JsonFileCache:
    """Cache JSON em disco para respostas já estruturadas.

    O cache é opt-in e deve ser usado com cuidado quando os dados contêm
    informações pessoais ou sensíveis.
    """

    def __init__(self, directory: str | Path, ttl_seconds: int) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = validar_ttl_cache(ttl_seconds)

    def get(self, namespace: str, key: str) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            created_at = float(payload.get("created_at", 0))
        except (OverflowError, TypeError, ValueError):
            return None
        if not math.isfinite(created_at):
            return None
        if self.ttl_seconds > 0 and time.time() - created_at > self.ttl_seconds:
            return None
        return payload.get("value")

    def set(self, namespace: str, key: str, value: Any) -> Path:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"created_at": time.time(), "value": value}
        conteudo = json.dumps(payload, ensure_ascii=False, indent=2)
        caminho_temporario: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporario:
                caminho_temporario = Path(temporario.name)
                temporario.write(conteudo)
            caminho_temporario.replace(path)
        finally:
            if caminho_temporario is not None:
                caminho_temporario.unlink(missing_ok=True)
        return path

    def _path(self, namespace: str, key: str) -> Path:
        digest = sha256(key.encode("utf-8")).hexdigest()
        safe_namespace = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in namespace)
        if safe_namespace in {".", ".."}:
            safe_namespace = "_"
        return self.directory / safe_namespace / f"{digest}.json"
