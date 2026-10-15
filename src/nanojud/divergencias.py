"""Comparacao objetiva entre fontes, sem interpretacao juridica."""

from __future__ import annotations

from typing import Any, TypedDict

from .normalization import normalizar_data
from .sources import DATAJUD, DJEN, ESAJ
from .utils import normalizar_chave


class Divergencia(TypedDict):
    campo: str
    severidade: str
    mensagem: str
    valores: dict[str, str]


def detectar_divergencias(data: dict[str, Any]) -> list[Divergencia]:
    """Compara eSAJ, DataJud e DJEN e lista diferencas que o usuario deve conferir.

    ``divergencia`` indica valores que deveriam coincidir; ``informacao`` indica
    contexto que muda a leitura dos dados (varios graus, incidentes no DJEN).
    """
    esaj = data.get(ESAJ) or {}
    datajud = data.get(DATAJUD) or {}
    saida: list[Divergencia] = []
    if esaj and datajud.get("status") == "ok":
        saida.extend(_comparar_esaj_datajud(esaj, datajud))
    graus = datajud.get("graus") or []
    if len(graus) > 1:
        resumo = ", ".join(f"{g['grau']} ({g['total_movimentos']} mov.)" for g in graus)
        saida.append(
            {
                "campo": "graus",
                "severidade": "informacao",
                "mensagem": "DataJud tem mais de um grau; os dados principais são do menor grau.",
                "valores": {DATAJUD: resumo},
            }
        )
    saida.extend(_incidentes_no_djen(data.get(DJEN) or []))
    return saida


def _comparar_esaj_datajud(esaj: dict[str, Any], datajud: dict[str, Any]) -> list[Divergencia]:
    saida: list[Divergencia] = []
    basicos = esaj.get("dados_basicos") or {}

    classe_esaj = str(basicos.get("classe") or "")
    classe_datajud = str(datajud.get("classe") or "")
    if classe_esaj and classe_datajud and not _mesma_classe(classe_esaj, classe_datajud):
        saida.append(
            {
                "campo": "classe",
                "severidade": "divergencia",
                "mensagem": "Classe processual diferente entre eSAJ e DataJud.",
                "valores": {ESAJ: classe_esaj, DATAJUD: classe_datajud},
            }
        )

    distribuicao = normalizar_data(basicos.get("distribuicao"))["iso"]
    graus = datajud.get("graus") or []
    ajuizamento = normalizar_data(graus[0].get("data_ajuizamento") if graus else "")["iso"]
    if distribuicao and ajuizamento and distribuicao != ajuizamento:
        saida.append(
            {
                "campo": "data_distribuicao",
                "severidade": "divergencia",
                "mensagem": "Data de distribuição (eSAJ) difere da data de ajuizamento (DataJud).",
                "valores": {ESAJ: distribuicao, DATAJUD: ajuizamento},
            }
        )

    ultima_esaj = _ultima_data(esaj.get("movimentacoes"), "data")
    ultima_datajud = _ultima_data(datajud.get("movimentos"), "data")
    if ultima_esaj and ultima_datajud and ultima_esaj != ultima_datajud:
        saida.append(
            {
                "campo": "ultima_movimentacao",
                "severidade": "divergencia",
                "mensagem": "Data da última movimentação difere entre eSAJ e DataJud.",
                "valores": {ESAJ: ultima_esaj, DATAJUD: ultima_datajud},
            }
        )
    return saida


def _incidentes_no_djen(comunicacoes: list[dict[str, Any]]) -> list[Divergencia]:
    de_incidente = [c for c in comunicacoes if c.get("incidente")]
    if not de_incidente:
        return []
    return [
        {
            "campo": "djen_incidentes",
            "severidade": "informacao",
            "mensagem": "Parte das comunicações do DJEN é de incidentes, não do principal.",
            "valores": {DJEN: f"{len(de_incidente)} de {len(comunicacoes)}"},
        }
    ]


def _mesma_classe(a: str, b: str) -> bool:
    chave_a, chave_b = normalizar_chave(a), normalizar_chave(b)
    return chave_a == chave_b or chave_a in chave_b or chave_b in chave_a


def _ultima_data(movimentos: list[dict[str, Any]] | None, campo: str) -> str:
    datas = [normalizar_data(m.get(campo))["iso"] for m in movimentos or []]
    return max((d for d in datas if d), default="")
