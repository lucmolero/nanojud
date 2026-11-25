"""Gera resposta factual citada e tabela a partir de uma consulta NanoJud."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from nanojud import api, exports
from nanojud.timeline import compactar_timeline


def _registros_com_estado(
    timeline: list[dict[str, Any]], source_status: dict[str, Any]
) -> list[dict[str, Any]]:
    registros = []
    for movimento in timeline:
        registro = dict(movimento)
        fonte = registro.get("fonte")
        estado = source_status.get(fonte) if isinstance(fonte, str) else None
        if isinstance(estado, dict) and isinstance(estado.get("status"), str):
            registro.setdefault("status_fonte", estado["status"])
        registros.append(registro)
    return registros


def _resposta_factual(registros: list[dict[str, Any]], limite: int) -> str:
    if not registros:
        return (
            "Nenhum evento foi retornado pelas fontes selecionadas. "
            "Isso não confirma que o processo inexista."
        )

    linhas = [f"Eventos mais recentes observados (até {limite}); sem interpretação jurídica:"]
    for registro in registros[:5]:
        data = registro.get("data") or "data não informada"
        texto = registro.get("titulo") or registro.get("texto") or "descrição ausente"
        texto = _escapar_markdown(" ".join(str(texto).split()))
        origem = registro.get("fonte") or "fonte não informada"
        identificador = registro.get("id") or "ID ausente"
        referencia = f"[{origem}:{identificador}]"
        linhas.append(f"- {data}: {texto} {referencia}")
    return "\n".join(linhas)


def _escapar_markdown(texto: str) -> str:
    """Evita que texto do processo crie links ou estrutura Markdown no exemplo."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", texto)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numero", help="número CNJ")
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="fonte a consultar; repita para incluir outras (padrão: esaj, datajud, djen)",
    )
    parser.add_argument("--limit", type=int, default=20, help="eventos recentes na resposta")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit deve ser positivo")

    envelope = api.extract_process(
        args.numero,
        sources=args.sources or ("esaj", "datajud", "djen"),
        limite_movimentacoes=args.limit,
    )
    timeline = compactar_timeline(
        envelope.get("timeline", []),
        limit=args.limit,
        recent_first=True,
        include_text=True,
        max_text_chars=500,
    )
    source_status = envelope.get("source_status", {})
    registros = _registros_com_estado(timeline, source_status)
    tabela = exports.to_table(registros)
    saida = {
        "numero_cnj": envelope.get("numero_cnj"),
        "status": envelope.get("status"),
        "source_status": source_status,
        "resposta_factual": _resposta_factual(registros, args.limit),
        "tabela": tabela,
        "avisos": envelope.get("warnings", []),
        "erros": envelope.get("errors", []),
    }
    print(json.dumps(saida, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
