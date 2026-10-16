"""Versões enxutas das respostas, sem interpretação: só removem dados repetidos."""

from __future__ import annotations

from typing import Any

from .sources import DATAJUD, DJEN, ESAJ


def compactar_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Remove do envelope o que a timeline já traz, mantendo cabeçalhos e contagens.

    Movimentações e comunicações aparecem duas vezes no envelope completo (em ``data`` e
    em ``timeline``); a versão compacta mantém só a timeline unificada.
    """
    saida = dict(envelope)
    data = dict(saida.get("data") or {})
    if isinstance(data.get(ESAJ), dict):
        data[ESAJ] = {k: v for k, v in data[ESAJ].items() if k != "movimentacoes"}
    if isinstance(data.get(DATAJUD), dict):
        data[DATAJUD] = {k: v for k, v in data[DATAJUD].items() if k not in ("movimentos", "raw")}
    data.pop(DJEN, None)
    saida["data"] = data
    saida["compacto"] = True
    return saida


def compactar_datajud(extracao: dict[str, Any]) -> dict[str, Any]:
    """DataJud sem o ``payload_origem`` de cada movimento e parte (o dado já está normalizado)."""
    saida = dict(extracao)
    for chave in ("movimentos", "partes"):
        saida[chave] = [
            {k: v for k, v in item.items() if k != "payload_origem"}
            for item in extracao.get(chave) or []
        ]
    saida["compacto"] = True
    return saida


def compactar_extrato(extrato: dict[str, Any]) -> dict[str, Any]:
    """Versão enxuta do extrato eSAJ: movimentações sem texto repetido nem documentos."""
    saida = dict(extrato)
    saida["movimentacoes"] = [
        {k: m[k] for k in ("ordem", "data", "titulo", "teor") if m.get(k) not in (None, "")}
        for m in extrato.get("movimentacoes") or []
    ]
    saida["compacto"] = True
    return saida
