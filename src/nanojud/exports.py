"""Exportadores tecnicos para dados extraidos."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any


def to_json(data: Any) -> str:
    """Serializa dados em JSON UTF-8 amigavel."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def write_json(data: Any, path: str | Path) -> Path:
    """Grava dados em arquivo JSON."""
    destino = Path(path)
    destino.write_text(to_json(data), encoding="utf-8")
    return destino


def to_jsonl(records: Iterable[Mapping[str, Any]]) -> str:
    """Serializa registros em JSON Lines."""
    return "\n".join(json.dumps(record, ensure_ascii=False, default=str) for record in records)


def write_jsonl(records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    """Grava registros em JSON Lines."""
    destino = Path(path)
    conteudo = to_jsonl(records)
    destino.write_text(conteudo + ("\n" if conteudo else ""), encoding="utf-8")
    return destino


def write_csv(records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    """Grava registros achatados em CSV."""
    destino = Path(path)
    destino.write_text(to_csv(records), encoding="utf-8", newline="")
    return destino


def to_csv(
    records: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
    max_chars: int | None = None,
) -> str:
    """Serializa registros em CSV determinístico e neutro a fórmulas de planilha."""
    if max_chars is not None:
        _validate_limit(max_chars, "max_chars")
    rows = _records(records)
    fieldnames = _columns(rows, columns)
    if not rows and not fieldnames:
        return ""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    if max_chars is not None and output.tell() > max_chars:
        raise ValueError(f"A tabela excede o limite de {max_chars} caracteres.")
    for row in rows:
        writer.writerow({key: _csv_value(row.get(key, "")) for key in fieldnames})
        if max_chars is not None and output.tell() > max_chars:
            raise ValueError(f"A tabela excede o limite de {max_chars} caracteres.")
    return output.getvalue()


def to_table(
    records: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
    max_rows: int | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """Forma uma tabela estruturada e CSV, preservando colunas de proveniência."""
    if max_rows is not None:
        _validate_limit(max_rows, "max_rows")
    if max_chars is not None:
        _validate_limit(max_chars, "max_chars")
    rows = _records(records, max_rows=max_rows)
    fieldnames = _columns(rows, columns)
    if columns is not None:
        ausentes = [key for key in fieldnames if rows and not any(key in row for row in rows)]
        if ausentes:
            raise ValueError("Colunas não encontradas nos registros: " + ", ".join(ausentes))
    linhas = [{key: row.get(key) for key in fieldnames} for row in rows]
    conteudo_csv = to_csv(linhas, columns=fieldnames, max_chars=max_chars)
    return {
        "status": "ok" if linhas else "empty",
        "row_count": len(linhas),
        "columns": fieldnames,
        "rows": linhas,
        "csv": conteudo_csv,
    }


def _records(
    records: Iterable[Mapping[str, Any]], *, max_rows: int | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if max_rows is not None and len(rows) >= max_rows:
            raise ValueError(f"A tabela excede o limite de {max_rows} registros.")
        if not isinstance(record, Mapping):
            raise TypeError("Cada registro deve ser um mapeamento de colunas e valores.")
        if any(not isinstance(key, str) or not key for key in record):
            raise ValueError("Os nomes das colunas devem ser textos não vazios.")
        rows.append(dict(record))
    return rows


def _columns(rows: list[dict[str, Any]], columns: Sequence[str] | None) -> list[str]:
    if columns is None:
        return sorted({key for row in rows for key in row})
    fieldnames = list(columns)
    if any(not isinstance(key, str) or not key for key in fieldnames):
        raise ValueError("Os nomes das colunas devem ser textos não vazios.")
    if len(set(fieldnames)) != len(fieldnames):
        raise ValueError("A lista de colunas não pode conter duplicatas.")
    if rows and not fieldnames:
        raise ValueError("Uma tabela com registros precisa de ao menos uma coluna.")
    return fieldnames


def _validate_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} deve ser um inteiro positivo.")


def write_sqlite(
    records: Iterable[Mapping[str, Any]],
    path: str | Path,
    *,
    table: str = "records",
) -> Path:
    """Grava registros em SQLite usando colunas TEXT para portabilidade."""
    rows = [dict(record) for record in records]
    destino = Path(path)
    fieldnames = sorted({key for row in rows for key in row}) or ["empty"]
    columns = ", ".join(f'"{name}" TEXT' for name in fieldnames)
    placeholders = ", ".join("?" for _ in fieldnames)
    with closing(sqlite3.connect(destino)) as conn:
        with conn:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            conn.execute(f'CREATE TABLE "{table}" ({columns})')
            for row in rows:
                conn.execute(
                    f'INSERT INTO "{table}" VALUES ({placeholders})',
                    [_csv_value(row.get(key, "")) for key in fieldnames],
                )
    return destino


def _csv_value(value: Any) -> str:
    if isinstance(value, str):
        text = value
    elif value is None:
        return ""
    elif isinstance(value, int | float | bool):
        text = str(value)
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, str) and text.lstrip(" \t\r\n\v\f").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
