"""Interface de linha de comando para nanojud."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias, cast

from . import api, formatacao
from .exceptions import (
    AcessoRestrito,
    ArquivoInvalido,
    ConsultaIndisponivel,
    FormatoCNJInvalido,
    NanoJudError,
    ProcessoNaoEncontrado,
)
from .timeline import compactar_timeline, limite_movimentacoes_para
from .version import __version__

JsonPayload: TypeAlias = dict[str, Any] | list[Any]

EXEMPLO_NUMERO = "0015020-23.2010.8.26.0053"
FONTES = ["esaj", "datajud", "djen"]
EPILOGO = f"""\
exemplos:
  nanojud consultar {EXEMPLO_NUMERO}
  nanojud partes {EXEMPLO_NUMERO}
  nanojud linha-do-tempo {EXEMPLO_NUMERO} --recentes-primeiro --limite 20
  nanojud djen {EXEMPLO_NUMERO} --desde 2026-01-01
  nanojud extrato {EXEMPLO_NUMERO} --out extrato.json

Use "nanojud COMANDO --ajuda" para ver as opções de cada comando.
Só consulta dados públicos; não acessa processos sigilosos nem protegidos por senha."""

DICAS = (
    (
        FormatoCNJInvalido,
        f"Confira o número do processo. O padrão CNJ tem 20 dígitos, por exemplo {EXEMPLO_NUMERO}.",
    ),
    (
        ProcessoNaoEncontrado,
        "Confira o número. Se estiver certo, o processo pode ser sigiloso, de outro sistema "
        "ou de outro tribunal (fora do TJSP, tente o comando datajud).",
    ),
    (
        AcessoRestrito,
        "O processo ou documento exige senha, login ou é sigiloso. A biblioteca só consulta "
        "dados públicos; consulte direto no site do tribunal.",
    ),
    (
        ConsultaIndisponivel,
        "A fonte não respondeu ou recusou a consulta. Aguarde alguns minutos e tente de novo; "
        "o DataJud do CNJ costuma ficar instável em horários de pico.",
    ),
    (ArquivoInvalido, "Gere o arquivo antes com: nanojud extrato NUMERO --out extrato.json"),
)


# --- argparse em português


class _Formatador(argparse.HelpFormatter):
    def add_usage(self, usage: Any, actions: Any, groups: Any, prefix: Any = None) -> None:
        super().add_usage(usage, actions, groups, "uso: " if prefix is None else prefix)


_TRADUCOES = (
    (r"the following arguments are required: (.+)", r"faltou informar: \1"),
    (r"unrecognized arguments: (.+)", r"opção ou argumento não reconhecido: \1"),
    (
        r"argument (.+): invalid choice: '?([^']*)'? \(choose from (.+)\)",
        r"\1: valor inválido '\2'. Use um de: \3",
    ),
    (r"argument (.+): invalid int value: '(.*)'", r"\1: '\2' não é um número inteiro"),
    (r"argument (.+): expected one argument", r"\1: a opção precisa de um valor"),
    (r"expected one argument", "a opção precisa de um valor"),
)


def _traduzir(mensagem: str) -> str:
    for padrao, troca in _TRADUCOES:
        if re.search(padrao, mensagem):
            return re.sub(padrao, troca, mensagem)
    return mensagem


class _Parser(argparse.ArgumentParser):
    """ArgumentParser com textos de ajuda e de erro em português."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", _Formatador)
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self._positionals.title = "argumentos"
        self._optionals.title = "opções"
        self.add_argument(
            "-h",
            "--ajuda",
            "--help",
            action="help",
            default=argparse.SUPPRESS,
            help="mostrar esta ajuda e sair",
        )

    def error(self, message: str) -> Any:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: erro: {_traduzir(message)}\n")


# --- saída


def _format_json(data: JsonPayload) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _print_result(result: JsonPayload) -> None:
    print(_format_json(result))


def _terminal() -> bool:
    return sys.stdout.isatty()


def _formato(args: argparse.Namespace) -> str:
    """Resolve --formato: ``auto`` vira texto no terminal e JSON ao redirecionar ou usar --out."""
    escolhido = getattr(args, "formato", "auto")
    if escolhido != "auto":
        return str(escolhido)
    return "texto" if _terminal() and getattr(args, "out", None) is None else "json"


_SALVO = {"Partes": "salvas", "Timeline": "salva", "Extração": "salva", "Leitura de peças": "salva"}


def _emitir(
    payload: JsonPayload,
    out: str | None,
    rotulo: str,
    texto: Callable[[], str] | None = None,
) -> None:
    """Imprime na tela ou grava em arquivo; ``texto`` é o renderizador do modo legível."""
    conteudo = texto() if texto is not None else _format_json(payload)
    if out is None:
        print(conteudo)
        return
    Path(out).write_text(conteudo, encoding="utf-8")
    print(f"{rotulo} {_SALVO.get(rotulo, 'salvo')} em: {out}")


def _avisar(mensagem: str) -> None:
    """Aviso de andamento no stderr, só quando há uma pessoa olhando o terminal."""
    if sys.stderr.isatty():
        print(mensagem, file=sys.stderr, flush=True)


def _limite(valor: int | None, padrao: int | None = 100) -> int | None:
    """Traduz --limite-movimentacoes: ausente usa o padrão; 0 busca todas."""
    return padrao if valor is None else (valor or None)


def _dica(exc: Exception) -> str:
    for tipo, dica in DICAS:
        if isinstance(exc, tipo):
            return dica
    return ""


def _erro_json(exc: Exception) -> str:
    dados = {"status": "erro", "erro": exc.__class__.__name__, "mensagem": str(exc)}
    if dica := _dica(exc):
        dados["dica"] = dica
    return _format_json(dados)


def _erro_legivel(exc: Exception) -> str:
    linhas = [f"Erro: {exc}"]
    if dica := _dica(exc):
        linhas.append(f"O que fazer: {dica}")
    return "\n".join(linhas)


def _ler_extrato(caminho: str) -> dict[str, Any]:
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArquivoInvalido(
            f"O arquivo '{caminho}' não existe. Confira o nome e a pasta em que você está."
        ) from exc
    except OSError as exc:
        raise ArquivoInvalido(f"Não consegui ler o arquivo '{caminho}'.") from exc
    except json.JSONDecodeError as exc:
        raise ArquivoInvalido(f"O arquivo '{caminho}' não é um JSON válido de extrato.") from exc
    if not isinstance(dados, dict):
        raise ArquivoInvalido(f"O arquivo '{caminho}' não parece ser um extrato do nanojud.")
    return dados


# --- definição dos comandos


def _numero(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "numero",
        help=f"número do processo no padrão CNJ, ex.: {EXEMPLO_NUMERO} (aceita sem pontuação)",
    )


def _out(p: argparse.ArgumentParser, o_que: str = "o resultado") -> None:
    p.add_argument(
        "--out",
        default=None,
        metavar="ARQUIVO",
        help=f"gravar {o_que} neste arquivo (sem ele, mostra na tela)",
    )


def _formato_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--formato",
        choices=["auto", "texto", "json"],
        default="auto",
        help="texto = leitura no terminal; json = todos os campos; "
        "auto (padrão) = texto no terminal e json ao redirecionar a saída",
    )


def _fontes(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--source",
        "--fonte",
        dest="source",
        action="append",
        choices=FONTES,
        help="fonte a consultar; repita para mais de uma (padrão: todas)",
    )


def _filtros_de_data(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--desde",
        default="",
        metavar="AAAA-MM-DD",
        help="só dados a partir desta data, ex.: 2026-01-01",
    )
    p.add_argument(
        "--limite-movimentacoes",
        type=int,
        default=None,
        metavar="N",
        help="máximo de movimentações do eSAJ (0 busca todas; padrão 100)",
    )


def _montar_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="nanojud",
        description=(
            "Consulta processos judiciais públicos no eSAJ/TJSP, no DataJud/CNJ e no DJEN, "
            "e organiza os dados."
        ),
        epilog=EPILOGO,
        formatter_class=lambda prog: _Formatador(prog, max_help_position=30),
    )
    parser.add_argument("--versao", "--version", action="version", version=f"nanojud {__version__}")
    sub = parser.add_subparsers(dest="_nome", title="comandos", metavar="COMANDO")

    def comando(nome: str, ajuda: str, aliases: list[str] | None = None) -> argparse.ArgumentParser:
        p = sub.add_parser(nome, aliases=aliases or [], help=ajuda, description=ajuda)
        p.set_defaults(command=nome)
        return p

    p = comando("search", "resumo rápido do processo (apelido: consultar)", ["consultar"])
    _numero(p)
    _formato_arg(p)
    _out(p, "o resumo")

    p = comando("partes", "partes e advogados, por polo")
    _numero(p)
    _formato_arg(p)
    _out(p, "as partes")

    p = comando(
        "timeline", "linha do tempo dos andamentos (apelido: linha-do-tempo)", ["linha-do-tempo"]
    )
    _numero(p)
    _fontes(p)
    _filtros_de_data(p)
    p.add_argument(
        "--limit",
        "--limite",
        dest="limit",
        type=int,
        default=0,
        metavar="N",
        help="mostrar só N eventos",
    )
    p.add_argument(
        "--recent-first",
        "--recentes-primeiro",
        dest="recent_first",
        action="store_true",
        help="começar pelos eventos mais recentes",
    )
    p.add_argument("--sem-texto", action="store_true", help="omitir o texto de cada evento")
    p.add_argument(
        "--max-text-chars",
        "--max-caracteres",
        dest="max_text_chars",
        type=int,
        default=0,
        metavar="N",
        help="cortar o texto de cada evento em N caracteres",
    )
    p.add_argument("--envelope", action="store_true", help="incluir o envelope completo (json)")
    p.add_argument(
        "--djen-data-inicio", default="", metavar="AAAA-MM-DD", help="data inicial só para o DJEN"
    )
    p.add_argument("--datajud-api-key", default=None, metavar="CHAVE", help="chave do DataJud")
    _formato_arg(p)
    _out(p, "a linha do tempo")

    p = comando("djen", "comunicações e publicações do DJEN")
    _numero(p)
    p.add_argument(
        "--data-inicio",
        "--desde",
        dest="data_inicio",
        default="",
        metavar="AAAA-MM-DD",
        help="só comunicações a partir desta data",
    )
    _formato_arg(p)
    _out(p, "as comunicações")

    p = comando("datajud", "dados do processo no DataJud/CNJ (qualquer tribunal)")
    _numero(p)
    p.add_argument("--api-key", default=None, metavar="CHAVE", help="chave do DataJud")
    p.add_argument("--raw", action="store_true", help="incluir a resposta bruta da fonte")
    _out(p, "o resultado")

    p = comando("extrato", "extrato completo do processo no eSAJ (json)")
    _numero(p)
    p.add_argument(
        "--inspecionar-pecas",
        action="store_true",
        help="verificar quais peças públicas podem ser lidas",
    )
    p.add_argument("--baixar-pecas", action="store_true", help="baixar as peças públicas")
    p.add_argument(
        "--limite-pecas",
        type=int,
        default=3,
        metavar="N",
        help="máximo de peças a baixar (padrão 3)",
    )
    p.add_argument("--salvar-html", action="store_true", help="guardar o HTML original (auditoria)")
    p.add_argument(
        "--limite-movimentacoes",
        type=int,
        default=100,
        metavar="N",
        help="máximo de movimentações (0 busca todas; padrão 100)",
    )
    _out(p, "o extrato")

    p = comando("extract", "todas as fontes num envelope só, json (apelido: extrair)", ["extrair"])
    _numero(p)
    _fontes(p)
    _filtros_de_data(p)
    p.add_argument(
        "--djen-data-inicio", default="", metavar="AAAA-MM-DD", help="data inicial só para o DJEN"
    )
    p.add_argument("--datajud-api-key", default=None, metavar="CHAVE", help="chave do DataJud")
    p.add_argument("--raw", action="store_true", help="incluir as respostas brutas das fontes")
    _out(p, "o resultado")

    p = comando("ler-pecas", "ler o texto de peças públicas, sem salvar PDF")
    p.add_argument("extrato_json", help="arquivo gerado por: nanojud extrato NUMERO --out ARQUIVO")
    p.add_argument(
        "--limite", type=int, default=3, metavar="N", help="quantas peças ler (padrão 3)"
    )
    p.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        metavar="N",
        help="máximo de caracteres por peça (padrão 4000)",
    )
    _out(p, "a leitura")

    p = comando("baixar", "baixar peças públicas em PDF")
    p.add_argument("extrato_json", help="arquivo gerado por: nanojud extrato NUMERO --out ARQUIVO")
    p.add_argument(
        "--out", default="pecas", metavar="PASTA", help="pasta de destino (padrão: pecas)"
    )
    p.add_argument(
        "--limite", type=int, default=0, metavar="N", help="quantas peças baixar (0 = todas)"
    )
    p.add_argument("--sobrescrever", action="store_true", help="substituir arquivos que já existem")
    return parser


# --- execução


def main(argv: list[str] | None = None) -> int:
    # consoles Windows em cp1252 quebram com acentos fora do charset ao imprimir
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = _montar_parser()
    args = parser.parse_args(argv)
    try:
        return _executar(args, parser)
    except NanoJudError as exc:
        if _formato(args) == "texto" or _terminal():
            print(_erro_legivel(exc), file=sys.stderr)
        else:
            print(_erro_json(exc))
        return 2
    except KeyboardInterrupt:
        print("Consulta interrompida.", file=sys.stderr)
        return 130


def _executar(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    comando = getattr(args, "command", None)
    texto = _formato(args) == "texto"

    if comando == "search":
        _avisar("Consultando o processo... (cerca de 1 a 15 segundos)")
        resumo = api.search_processo(args.numero)
        _emitir(
            cast(JsonPayload, resumo),
            args.out,
            "Resumo",
            (lambda: formatacao.texto_resumo(cast(dict[str, Any], resumo))) if texto else None,
        )
        return 0

    if comando == "partes":
        _avisar("Consultando as partes no eSAJ...")
        partes = api.get_partes(args.numero)
        _emitir(
            partes, args.out, "Partes", (lambda: formatacao.texto_partes(partes)) if texto else None
        )
        return 0

    if comando == "extrato":
        _avisar("Consultando o eSAJ... (processos grandes levam mais tempo)")
        extrato_resultado = api.get_extrato(
            args.numero,
            baixar_pecas=args.baixar_pecas,
            limite_pecas=args.limite_pecas,
            inspecionar_pecas=args.inspecionar_pecas,
            salvar_html=args.salvar_html,
            limite_movimentacoes=args.limite_movimentacoes or None,
        )
        _emitir(cast(JsonPayload, extrato_resultado), args.out, "Extrato")
        return 0

    if comando == "baixar":
        _avisar("Baixando as peças públicas...")
        baixar_resultado = api.baixar_pecas(
            _ler_extrato(args.extrato_json),
            Path(args.out),
            sobrescrever=args.sobrescrever,
            limite=args.limite,
        )
        _print_result(baixar_resultado)
        return 0

    if comando == "ler-pecas":
        _avisar("Lendo as peças públicas... (pode levar cerca de 10 segundos)")
        leitura_resultado = api.ler_pecas(
            _ler_extrato(args.extrato_json),
            limite=args.limite,
            max_chars=args.max_chars,
        )
        _emitir(leitura_resultado, args.out, "Leitura de peças")
        return 0

    if comando == "djen":
        _avisar("Consultando o DJEN...")
        djen_resultado = api.consultar_djen(args.numero, data_inicio=args.data_inicio)
        _emitir(
            djen_resultado,
            args.out,
            "DJEN",
            (lambda: formatacao.texto_comunicacoes(djen_resultado)) if texto else None,
        )
        return 0

    if comando == "datajud":
        _avisar("Consultando o DataJud/CNJ...")
        datajud_resultado = api.consultar_datajud(
            args.numero,
            api_key=args.api_key,
            include_raw=args.raw,
        )
        _emitir(cast(JsonPayload, datajud_resultado), args.out, "DataJud")
        return 0

    if comando == "extract":
        _avisar("Consultando eSAJ, DataJud e DJEN em paralelo... (até 1 minuto)")
        extracao = api.extract_process(
            args.numero,
            sources=args.source or ("esaj", "datajud", "djen"),
            include_raw=args.raw,
            datajud_api_key=args.datajud_api_key,
            djen_data_inicio=args.djen_data_inicio,
            desde=args.desde,
            limite_movimentacoes=_limite(args.limite_movimentacoes),
        )
        _emitir(cast(JsonPayload, extracao), args.out, "Extração")
        return 0

    if comando == "timeline":
        return _linha_do_tempo(args, texto)

    parser.print_help()
    return 1


def _linha_do_tempo(args: argparse.Namespace, texto: bool) -> int:
    _avisar("Consultando eSAJ, DataJud e DJEN em paralelo... (até 1 minuto)")
    extracao = cast(
        dict[str, Any],
        api.extract_process(
            args.numero,
            sources=args.source or ("esaj", "datajud", "djen"),
            datajud_api_key=args.datajud_api_key,
            djen_data_inicio=args.djen_data_inicio,
            desde=args.desde,
            limite_movimentacoes=_limite(
                args.limite_movimentacoes,
                padrao=limite_movimentacoes_para(args.limit, args.recent_first, 100),
            ),
        ),
    )
    registros = compactar_timeline(
        cast(list[Any], extracao.get("timeline", [])),
        limit=args.limit,
        recent_first=args.recent_first,
        include_text=not args.sem_texto,
        max_text_chars=args.max_text_chars,
    )
    avisos = list(extracao.get("warnings", [])) + [
        f"{e['source']}: {e['message']}" for e in extracao.get("errors", [])
    ]
    if args.recent_first and args.limit and args.limite_movimentacoes is None:
        # o corte do eSAJ foi escolhido pela própria CLI para trazer só os mais recentes
        avisos = [a for a in avisos if "Movimentações limitadas" not in a]
    if args.envelope:
        extracao["timeline"] = registros
        _emitir(extracao, args.out, "Timeline")
        return 0

    def renderizar() -> str:
        return formatacao.texto_timeline(cast(list[dict[str, Any]], registros)) + "".join(
            f"\nAviso: {a}" for a in avisos
        )

    _emitir(cast(JsonPayload, registros), args.out, "Timeline", renderizar if texto else None)
    if not texto:
        for aviso in avisos:
            print(f"Aviso: {aviso}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
