"""Formatação de resumos compartilhada pela API funcional e pelo cliente."""

from __future__ import annotations

from typing import Any

from .models import Extrato, Movimentacao, ResumoProcesso
from .normalization import normalizar_data


def resumo_do_extrato(extrato: Extrato) -> ResumoProcesso:
    basicos = extrato.get("dados_basicos", {})
    origem = extrato.get("origem", {})
    movimentos = extrato.get("movimentacoes", [])
    ultima = ultima_movimentacao(movimentos)
    parcial = extrato.get("status") == "partial" or origem.get("movimentacoes_completas") is False
    mensagem = (
        origem.get("aviso_movimentacoes") or "A lista de movimentações está incompleta."
        if parcial
        else "Processo consultado com sucesso"
    )
    return {
        "numero": basicos.get("numero", ""),
        "classe": basicos.get("classe", ""),
        "assunto": basicos.get("assunto", ""),
        "foro": basicos.get("foro", ""),
        "vara": basicos.get("vara", ""),
        "juiz": basicos.get("juiz", ""),
        "ultima_movimentacao": ultima.get("titulo") or ultima.get("texto", ""),
        "ultima_data": ultima.get("data", ""),
        "url": origem.get("url_final", ""),
        "status": "partial" if parcial else extrato.get("status", "ok"),
        "mensagem": mensagem,
        "fonte": "esaj",
        "grau": str(origem.get("grau") or ""),
        "data_coleta": str(origem.get("data_coleta") or ""),
        "coleta_completa": origem.get("movimentacoes_completas"),
        "situacao": basicos.get("situacao", ""),
    }


def ultima_movimentacao(
    movimentos: list[Movimentacao],
) -> Movimentacao | dict[str, Any]:
    if not movimentos:
        return {}
    com_data = []
    for indice, movimento in enumerate(movimentos):
        data_iso = normalizar_data(movimento.get("data"))["iso"]
        if data_iso:
            com_data.append((data_iso, -indice, movimento))
    if com_data:
        return max(com_data, key=lambda item: (item[0], item[1]))[2]
    return movimentos[0]
