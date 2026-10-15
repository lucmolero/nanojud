"""Saída em texto legível para o terminal, sem interpretação dos dados."""

from __future__ import annotations

import textwrap
from typing import Any

LARGURA = 100
NOMES_FONTES = {"esaj": "eSAJ", "datajud": "DataJud", "djen": "DJEN"}
ROTULOS_POLOS = (
    ("polo_ativo", "POLO ATIVO"),
    ("polo_passivo", "POLO PASSIVO"),
    ("polo_desconhecido", "OUTRAS PARTES"),
)


def _linha(rotulo: str, valor: Any) -> str | None:
    valor = str(valor or "").strip()
    return f"{rotulo + ':':<22}{valor}" if valor else None


def _data_br(data: Any) -> str:
    """AAAA-MM-DD vira DD/MM/AAAA; outros formatos ficam como vieram."""
    texto = str(data or "").strip()
    partes = texto[:10].split("-")
    if len(partes) == 3 and len(partes[0]) == 4 and all(p.isdigit() for p in partes):
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return texto or "(sem data)"


def _cortar(texto: Any, limite: int) -> str:
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _quebrar(texto: str, recuo: int) -> str:
    return textwrap.fill(
        texto, width=LARGURA, initial_indent=" " * recuo, subsequent_indent=" " * recuo
    )


def texto_resumo(resumo: dict[str, Any]) -> str:
    """Resumo de um processo (resultado de ``search``)."""
    origem = "DataJud (processo fora do TJSP)" if resumo.get("fonte") == "datajud" else "eSAJ/TJSP"
    linhas = [
        f"Processo {resumo.get('numero', '')}",
        "-" * 60,
        _linha("Classe", resumo.get("classe")),
        _linha("Assunto", resumo.get("assunto")),
        _linha("Situação", resumo.get("situacao")),
        _linha("Foro", resumo.get("foro")),
        _linha("Vara / órgão", resumo.get("vara")),
        _linha("Juiz", resumo.get("juiz")),
        _linha("Última movimentação", resumo.get("ultima_data")),
    ]
    if resumo.get("ultima_movimentacao"):
        linhas.append(_quebrar(str(resumo["ultima_movimentacao"]), 22).rstrip())
    linhas += [_linha("Fonte", origem), _linha("Link", resumo.get("url"))]
    return "\n".join(linha for linha in linhas if linha)


def texto_partes(partes: dict[str, Any]) -> str:
    """Partes e advogados agrupados por polo."""
    blocos = []
    for chave, titulo in ROTULOS_POLOS:
        itens = partes.get(chave) or []
        if not itens:
            continue
        linhas = [titulo]
        for parte in itens:
            nomes = "; ".join(parte.get("nomes") or []) or "(sem nome informado)"
            linhas.append(f"  {parte.get('tipo') or 'Parte'}: {nomes}")
            for advogado in parte.get("advogados") or []:
                linhas.append(f"      Advogado(a): {advogado}")
        blocos.append("\n".join(linhas))
    return "\n\n".join(blocos) if blocos else "Nenhuma parte encontrada para este processo."


def texto_timeline(registros: list[dict[str, Any]]) -> str:
    """Linha do tempo, uma linha por evento, com fonte e grau quando houver."""
    if not registros:
        return "Nenhum evento encontrado para os filtros informados."
    linhas = []
    for r in registros:
        fonte = NOMES_FONTES.get(str(r.get("fonte")), str(r.get("fonte") or ""))
        fonte += f" {r['grau']}" if r.get("grau") else ""
        cabecalho = f"{_data_br(r.get('data')):<11} {fonte:<11} {r.get('titulo') or ''}"
        linhas.append(cabecalho.rstrip())
        texto = _cortar(r.get("texto"), 220)
        if texto:
            linhas.append(_quebrar(texto, 24))
    linhas.append("")
    linhas.append(f"{len(registros)} evento(s). Use --formato json para ver todos os campos.")
    return "\n".join(linhas)


def texto_comunicacoes(comunicacoes: list[dict[str, Any]]) -> str:
    """Comunicações e publicações do DJEN."""
    if not comunicacoes:
        return "Nenhuma comunicação encontrada no DJEN para este processo."
    linhas = []
    for c in comunicacoes:
        incidente = f" (incidente /{c['incidente']})" if c.get("incidente") else ""
        linhas.append(
            f"{_data_br(c.get('dataDisponibilizacao')):<11} "
            f"{c.get('tipoComunicacao') or ''}{incidente}".rstrip()
        )
        if c.get("nomeOrgao"):
            linhas.append(f"{'':<12}{c['nomeOrgao']}")
        texto = _cortar(c.get("texto"), 260)
        if texto:
            linhas.append(_quebrar(texto, 12))
    linhas.append("")
    linhas.append(
        f"{len(comunicacoes)} comunicação(ões). Use --formato json para ver todos os campos."
    )
    return "\n".join(linhas)
