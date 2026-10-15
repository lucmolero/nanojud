"""Normalizacao tecnica de dados extraidos de fontes judiciais."""

from __future__ import annotations

import re
from datetime import datetime

from .utils import limpar, normalizar_numero_cnj, validar_numero_cnj


def somente_digitos(valor: str) -> str:
    """Remove tudo que nao for digito."""
    return re.sub(r"\D", "", valor or "")


def extrair_numeros_cnj(texto: str, *, validar: bool = True) -> list[str]:
    """Extrai numeros CNJ de um texto e retorna valores normalizados e unicos."""
    candidatos = re.findall(
        r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}",
        texto or "",
    )
    vistos: set[str] = set()
    saida: list[str] = []
    for candidato in candidatos:
        try:
            numero = (
                validar_numero_cnj(candidato, segmento=None, tribunal=None)
                if validar
                else normalizar_numero_cnj(candidato)
            )
        except ValueError:
            continue
        if numero not in vistos:
            vistos.add(numero)
            saida.append(numero)
    return saida


def normalizar_data(valor: object) -> dict[str, str]:
    """Normaliza datas frequentes nas fontes, preservando o valor original."""
    original = "" if valor is None else str(valor).strip()
    if not original:
        return {"original": "", "iso": ""}

    if re.match(r"^\d{4}-\d{2}-\d{2}", original):
        return {"original": original, "iso": original[:10]}

    compacta = re.match(r"^(\d{4})(\d{2})(\d{2})\d{6}$", original)  # ex.: 20120910171334
    if compacta:
        ano, mes, dia = compacta.groups()
        return {"original": original, "iso": f"{ano}-{mes}-{dia}"}

    match_br = re.search(r"(\d{2})/(\d{2})/(\d{4})", original)
    if match_br:
        dia, mes, ano = match_br.groups()
        return {"original": original, "iso": f"{ano}-{mes}-{dia}"}

    try:
        parsed = datetime.fromisoformat(original.replace("Z", "+00:00"))
    except ValueError:
        return {"original": original, "iso": ""}
    return {"original": original, "iso": parsed.date().isoformat()}


def normalizar_texto_extraido(texto: str) -> str:
    """Limpa espacos e quebras duplicadas sem resumir ou interpretar o conteudo."""
    return limpar(texto)


def normalizar_oab(texto: str) -> str:
    """Normaliza uma OAB preservando apenas componentes tecnicos reconheciveis."""
    valor = limpar(texto).upper()
    valor = re.sub(r"\bOAB\b[:\s-]*", "", valor)
    return re.sub(r"\s+", " ", valor).strip()
