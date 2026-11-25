"""Interface de linha de comando para nanojud."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Iterator
from getpass import getpass
from pathlib import Path
from typing import Any, TextIO, TypeAlias, cast

from . import api, autenticacao, esaj, esaj_tjsp_2g, exports, formatacao
from .client import NanoJudClient
from .config import NanoJudConfig
from .exceptions import (
    AcessoRestrito,
    ArquivoInvalido,
    ConsultaIndisponivel,
    DestinoInvalido,
    EntradaLoteInvalida,
    FormatoCNJInvalido,
    NanoJudError,
    ProcessoNaoEncontrado,
)
from .sources import ALL_SOURCES, AVAILABLE_SOURCES, ESAJ_TJSP_2G
from .timeline import compactar_timeline, limite_movimentacoes_para
from .utils import salvar_pdf_atomico, validar_timeout
from .version import __version__

JsonPayload: TypeAlias = dict[str, Any] | list[Any]

EXEMPLO_NUMERO = "0015020-23.2010.8.26.0053"
EPILOGO = f"""\
exemplos:
  nanojud consultar {EXEMPLO_NUMERO}
  nanojud partes {EXEMPLO_NUMERO}
  nanojud linha-do-tempo {EXEMPLO_NUMERO} --recentes-primeiro --limite 20
  nanojud djen {EXEMPLO_NUMERO} --desde 2026-01-01
  nanojud extrato {EXEMPLO_NUMERO} --out extrato.json
  nanojud tabela extracao.json --out timeline.csv

Use "nanojud COMANDO --ajuda" para ver as opções de cada comando.
O CLI consulta sem login por padrão. Use --autenticar-advogado para abrir o login oficial e-SAJ.
A fonte continua validando a autorização de cada peça."""

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
    (DestinoInvalido, "Escolha um caminho de saída diferente do arquivo de entrada."),
    (EntradaLoteInvalida, "Salve a lista de processos em UTF-8 e execute o comando novamente."),
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


def _timeout_segundos(valor: str) -> float:
    try:
        return validar_timeout(float(valor))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _opcoes_autenticacao(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--autenticar-advogado",
        action="store_true",
        help="abrir o login oficial e-SAJ em navegador visível",
    )
    parser.add_argument(
        "--executavel-navegador",
        metavar="CAMINHO",
        help="caminho de Chromium, Chrome ou Edge instalado (para compatibilidade local)",
    )
    parser.add_argument(
        "--pedir-senha-processo",
        action="store_true",
        help="solicitar a senha do processo em entrada oculta",
    )


def _sessao_e_senha(args: argparse.Namespace) -> tuple[Any | None, str | None]:
    sessao = None
    if args.autenticar_advogado:
        _avisar("Complete o login no navegador oficial do e-SAJ...")
        sessao = autenticacao.autenticar_esaj_no_navegador(
            executable_path=args.executavel_navegador
        )
    elif args.pedir_senha_processo:
        sessao = esaj.criar_session()
    senha = getpass("Senha do processo (entrada oculta): ") if args.pedir_senha_processo else None
    return sessao, senha


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


def _ler_json(caminho: str) -> Any:
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArquivoInvalido(f"O arquivo '{caminho}' não existe.") from exc
    except OSError as exc:
        raise ArquivoInvalido(f"Não consegui ler o arquivo '{caminho}'.") from exc
    except json.JSONDecodeError as exc:
        raise ArquivoInvalido(f"O arquivo '{caminho}' não contém JSON válido.") from exc


def _registros_da_tabela(dados: Any, colecao: str) -> list[dict[str, Any]]:
    origem: dict[str, Any] = {}
    dados_basicos: dict[str, Any] = {}
    estados: dict[str, Any] = {}
    caminho = colecao
    if isinstance(dados, list):
        if colecao:
            raise ArquivoInvalido("Para um JSON que já é uma lista, omita --colecao.")
        registros = dados
    elif isinstance(dados, dict):
        if not caminho:
            caminho = next(
                (
                    chave
                    for chave in ("timeline", "movimentacoes", "comunicacoes", "records")
                    if isinstance(dados.get(chave), list)
                ),
                "",
            )
        if not caminho:
            raise ArquivoInvalido(
                "Não encontrei uma coleção de registros. Use --colecao CAMINHO, "
                "por exemplo timeline ou data.djen."
            )
        alvo: Any = dados
        for parte in caminho.split("."):
            if not isinstance(alvo, dict) or parte not in alvo:
                raise ArquivoInvalido(f"A coleção '{caminho}' não existe no JSON.")
            alvo = alvo[parte]
        if not isinstance(alvo, list):
            raise ArquivoInvalido(f"A coleção '{caminho}' precisa ser uma lista de registros.")
        registros = alvo
        origem_value = dados.get("origem")
        if isinstance(origem_value, dict):
            origem = origem_value
        dados_basicos_value = dados.get("dados_basicos")
        if isinstance(dados_basicos_value, dict):
            dados_basicos = dados_basicos_value
        estados_value = dados.get("source_status")
        if isinstance(estados_value, dict):
            estados = estados_value
    else:
        raise ArquivoInvalido("O JSON precisa conter uma lista ou um objeto com uma coleção.")

    numero = str(
        (dados.get("numero_cnj") if isinstance(dados, dict) else "")
        or dados_basicos.get("numero")
        or origem.get("entrada")
        or ""
    )
    fonte_contexto = str(origem.get("sistema") or "")
    tribunal = str(origem.get("tribunal") or "")
    grau = str(origem.get("grau") or "")
    if not fonte_contexto and caminho.startswith("data."):
        fonte_contexto = caminho.split(".", maxsplit=2)[1]
    elif not fonte_contexto and caminho == "comunicacoes":
        fonte_contexto = "djen"

    linhas: list[dict[str, Any]] = []
    for registro in registros:
        if not isinstance(registro, dict):
            raise ArquivoInvalido("Cada item da coleção precisa ser um objeto JSON.")
        linha = dict(registro)
        if numero and not linha.get("numero_cnj"):
            linha["numero_cnj"] = numero
        if fonte_contexto and not linha.get("fonte"):
            linha["fonte"] = fonte_contexto
        if tribunal and not linha.get("tribunal"):
            linha["tribunal"] = tribunal
        if not linha.get("tribunal") and linha.get("siglaTribunal"):
            linha["tribunal"] = linha["siglaTribunal"]
        if grau and not linha.get("grau"):
            linha["grau"] = grau
        fonte = str(linha.get("fonte") or "")
        estado = estados.get(fonte)
        if isinstance(estado, dict) and estado.get("status"):
            linha.setdefault("status_fonte", estado["status"])
        elif isinstance(dados, dict) and caminho == "comunicacoes" and dados.get("status"):
            linha.setdefault("status_fonte", dados["status"])
        elif isinstance(dados, dict) and origem and dados.get("status"):
            linha.setdefault("status_fonte", dados["status"])
        linhas.append(linha)
    return linhas


def _validar_saida_em_lote(arquivo_entrada: str, arquivo_saida: str) -> Path | None:
    """Valida a entrada e o destino sem criar nem truncar arquivos."""
    origem = Path(arquivo_entrada)
    try:
        origem_resolvida = origem.resolve(strict=True)
        if not origem_resolvida.is_file():
            raise ArquivoInvalido(f"O arquivo de entrada '{arquivo_entrada}' não é um arquivo.")
    except OSError as exc:
        raise ArquivoInvalido(
            f"O arquivo de entrada '{arquivo_entrada}' não existe ou não pode ser lido."
        ) from exc

    if arquivo_saida == "-":
        return None

    destino = Path(arquivo_saida)
    try:
        mesmo_arquivo = (
            os.path.samefile(origem_resolvida, destino)
            if destino.exists()
            else destino.resolve(strict=False) == origem_resolvida
        )
    except OSError as exc:
        raise DestinoInvalido(
            f"Não foi possível validar o arquivo de saída '{arquivo_saida}'."
        ) from exc
    if mesmo_arquivo:
        raise DestinoInvalido("O arquivo de saída deve ser diferente do arquivo de entrada.")
    if not destino.parent.is_dir():
        raise DestinoInvalido(f"A pasta de saída '{destino.parent}' não existe ou não é uma pasta.")
    return destino


def _abrir_saida_em_lote(arquivo_entrada: str, arquivo_saida: str) -> TextIO:
    """Valida entrada e destino antes de abrir o manifesto para escrita."""
    destino = _validar_saida_em_lote(arquivo_entrada, arquivo_saida)
    if destino is None:
        return sys.stdout
    try:
        return destino.open("w", encoding="utf-8", newline="\n")
    except OSError as exc:
        raise DestinoInvalido(
            f"Não foi possível criar o arquivo de saída '{arquivo_saida}'."
        ) from exc


def _numeros_do_arquivo(caminho: Path) -> Iterator[str]:
    """Lê CNJs em fluxo e converte erros de codificação para erro CLI legível."""
    try:
        with caminho.open("r", encoding="utf-8-sig") as entrada:
            for linha in entrada:
                numero = linha.strip()
                if numero and not numero.startswith("#"):
                    yield numero
    except UnicodeDecodeError as exc:
        raise EntradaLoteInvalida(
            f"O arquivo de entrada '{caminho}' contém bytes que não formam texto UTF-8 válido."
        ) from exc
    except OSError as exc:
        raise ArquivoInvalido(f"Não consegui ler o arquivo de entrada '{caminho}'.") from exc


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
        choices=AVAILABLE_SOURCES,
        help="fonte a consultar; repita para mais de uma (padrão: esaj, datajud, djen)",
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
            "Consulta processos judiciais em fontes como e-SAJ, eproc, DataJud, DJEN, PJe "
            "e MNI 3.0, conforme a instalação configurada."
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

    def timeout_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--timeout",
            type=_timeout_segundos,
            default=30.0,
            help="timeout por requisição em segundos",
        )

    p = comando("search", "resumo rápido do processo (apelido: consultar)", ["consultar"])
    _numero(p)
    _formato_arg(p)
    _out(p, "o resumo")

    p = comando("partes", "partes e advogados, por polo")
    _numero(p)
    _formato_arg(p)
    _out(p, "as partes")

    p = comando("esaj-2g", "capas e movimentações públicas no e-SAJ/TJSP de segundo grau")
    _numero(p)
    _out(p, "a consulta de segundo grau")
    timeout_arg(p)

    p = comando("esaj-2g-pdf", "baixa uma peça pública do e-SAJ/TJSP de segundo grau")
    _numero(p)
    p.add_argument("cd_documento", help="identificador listado nas movimentações do CNJ próprio")
    p.add_argument("--out", required=True, metavar="ARQUIVO", help="destino do PDF")
    p.add_argument(
        "--max-paginas",
        type=int,
        default=esaj_tjsp_2g.MAX_PAGINAS,
        help="páginas de movimentos para localizar o vínculo (padrão: %(default)s)",
    )
    timeout_arg(p)

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

    p = comando("tabela", "exporta registros JSON para CSV com proveniência", ["csv"])
    p.add_argument("arquivo", help="JSON gerado pela NanoJud ou lista JSON de registros")
    p.add_argument(
        "--colecao",
        default="",
        metavar="CAMINHO",
        help="caminho com pontos para a lista (padrão: timeline, movimentacoes ou comunicacoes)",
    )
    p.add_argument("--out", default="-", metavar="ARQUIVO", help="CSV de saída (padrão: stdout)")

    p = comando("datajud", "dados do processo no DataJud/CNJ (qualquer tribunal)")
    _numero(p)
    p.add_argument("--api-key", default=None, metavar="CHAVE", help="chave do DataJud")
    p.add_argument("--raw", action="store_true", help="incluir a resposta bruta da fonte")
    _out(p, "o resultado")

    p = comando("extrato", "extrato completo do processo no eSAJ (json)")
    _numero(p)
    timeout_arg(p)
    _opcoes_autenticacao(p)
    p.add_argument(
        "--inspecionar-pecas",
        action="store_true",
        help="verificar metadados das peças acessíveis",
    )
    p.add_argument("--baixar-pecas", action="store_true", help="baixar as peças acessíveis")
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
    timeout_arg(p)
    _fontes(p)
    _filtros_de_data(p)
    p.add_argument(
        "--djen-data-inicio", default="", metavar="AAAA-MM-DD", help="data inicial só para o DJEN"
    )
    p.add_argument("--datajud-api-key", default=None, metavar="CHAVE", help="chave do DataJud")
    p.add_argument("--raw", action="store_true", help="incluir as respostas brutas das fontes")
    _out(p, "o resultado")

    p = comando("batch", "consultar processos de um arquivo, produzindo JSONL incremental")
    p.add_argument(
        "arquivo", help="arquivo UTF-8 com um número CNJ por linha (# inicia comentário)"
    )
    _fontes(p)
    p.add_argument("--workers", type=int, default=1, help="consultas simultâneas (1 a 8; padrão 1)")
    p.add_argument(
        "--timeout", type=_timeout_segundos, default=30.0, help="timeout por fonte em segundos"
    )
    p.add_argument("--datajud-retries", type=int, default=3, help="tentativas DataJud por processo")
    p.add_argument(
        "--limite-movimentacoes",
        type=int,
        default=100,
        help="máximo de movimentações por processo (0 busca todas; padrão 100)",
    )
    p.add_argument("--datajud-api-key", default=None, metavar="CHAVE", help="chave do DataJud")
    p.add_argument("--djen-data-inicio", default="", metavar="AAAA-MM-DD")
    p.add_argument("--desde", default="", metavar="AAAA-MM-DD")
    p.add_argument("--raw", action="store_true", help="incluir dados brutos das fontes")
    p.add_argument(
        "--out",
        default="-",
        metavar="ARQUIVO",
        help="JSONL de saída (padrão: stdout; - também significa stdout)",
    )

    p = comando("autos", "consultar processos e obter peças acessíveis do eSAJ/TJSP em lote")
    p.add_argument("arquivo", help="arquivo UTF-8 com um número CNJ por linha")
    p.add_argument("--source", "--fonte", choices=[ESAJ_TJSP_2G], help="seleciona o CPoSG público")
    timeout_arg(p)
    _opcoes_autenticacao(p)
    p.add_argument(
        "--out-dir", required=True, metavar="PASTA", help="raiz para pastas por processo"
    )
    p.add_argument("--max-documentos", type=int, default=10, help="máximo por processo; 0 = todos")
    p.add_argument(
        "--ler-documentos",
        action="store_true",
        help="extrair texto em memória sem salvar PDFs",
    )
    p.add_argument("--max-chars", type=int, default=4000, help="máximo de caracteres por documento")
    p.add_argument("--desde", default="", metavar="AAAA-MM-DD")
    p.add_argument("--limite-movimentacoes", type=int, default=100, help="0 busca todas")
    p.add_argument(
        "--incluir-extrato", action="store_true", help="incluir o extrato completo no JSONL"
    )
    p.add_argument("--out", default="-", metavar="ARQUIVO", help="manifesto JSONL (padrão: stdout)")

    p = comando("ler-pecas", "ler o texto de peças acessíveis, sem salvar PDF")
    p.add_argument("extrato_json", help="arquivo gerado por: nanojud extrato NUMERO --out ARQUIVO")
    timeout_arg(p)
    _opcoes_autenticacao(p)
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

    p = comando("baixar", "baixar peças acessíveis em PDF")
    p.add_argument("extrato_json", help="arquivo gerado por: nanojud extrato NUMERO --out ARQUIVO")
    timeout_arg(p)
    _opcoes_autenticacao(p)
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
        saida_jsonl = (
            getattr(args, "command", None) in {"batch", "autos"}
            and getattr(args, "out", "-") == "-"
        )
        if saida_jsonl or _formato(args) == "texto" or _terminal():
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

    if comando == "esaj-2g":
        resultado_2g = api.consultar_esaj_tjsp_2g(args.numero, timeout=args.timeout)
        _emitir(resultado_2g, args.out, "Consulta e-SAJ/TJSP de segundo grau")
        return 2 if resultado_2g["status"] == "erro" else 0

    if comando == "esaj-2g-pdf":
        try:
            pdf = api.obter_pdf_esaj_tjsp_2g(
                args.numero,
                args.cd_documento,
                timeout=args.timeout,
                max_paginas=args.max_paginas,
            )
        except FormatoCNJInvalido:
            raise
        except ValueError as exc:
            parser.error(str(exc))
        salvar_pdf_atomico(pdf, Path(args.out))
        print(f"PDF salvo em: {args.out}")
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
        sessao, senha_processo = _sessao_e_senha(args)
        extrato_resultado = api.get_extrato(
            args.numero,
            baixar_pecas=args.baixar_pecas,
            limite_pecas=args.limite_pecas,
            inspecionar_pecas=args.inspecionar_pecas,
            salvar_html=args.salvar_html,
            limite_movimentacoes=args.limite_movimentacoes or None,
            session=sessao,
            senha_processo=senha_processo,
            timeout=args.timeout,
        )
        _emitir(cast(JsonPayload, extrato_resultado), args.out, "Extrato")
        return 0

    if comando == "baixar":
        _avisar("Baixando as peças acessíveis...")
        extrato_lido = cast(Any, _ler_extrato(args.extrato_json))
        sessao, senha_processo = _sessao_e_senha(args)
        if sessao is not None or senha_processo is not None:
            numero = str((extrato_lido.get("dados_basicos") or {}).get("numero") or "")
            extrato_lido = api.get_extrato(
                numero,
                limite_movimentacoes=None,
                session=sessao,
                senha_processo=senha_processo,
                timeout=args.timeout,
            )
        baixar_resultado = api.baixar_pecas(
            extrato_lido,
            Path(args.out),
            sobrescrever=args.sobrescrever,
            limite=args.limite,
            session=sessao,
            timeout=args.timeout,
        )
        _print_result(baixar_resultado)
        return 0

    if comando == "ler-pecas":
        _avisar("Lendo as peças acessíveis... (pode levar mais tempo em processos grandes)")
        extrato_lido = cast(Any, _ler_extrato(args.extrato_json))
        sessao, senha_processo = _sessao_e_senha(args)
        if sessao is not None or senha_processo is not None:
            numero = str((extrato_lido.get("dados_basicos") or {}).get("numero") or "")
            extrato_lido = api.get_extrato(
                numero,
                limite_movimentacoes=None,
                session=sessao,
                senha_processo=senha_processo,
                timeout=args.timeout,
            )
        leitura_resultado = api.ler_pecas(
            extrato_lido,
            limite=args.limite,
            max_chars=args.max_chars,
            session=sessao,
            timeout=args.timeout,
        )
        _emitir(leitura_resultado, args.out, "Leitura de peças")
        return 0

    if comando == "djen":
        _avisar("Consultando o DJEN...")
        djen_resultado = api.consultar_djen_detalhado(args.numero, data_inicio=args.data_inicio)
        payload = {
            **djen_resultado,
            "count": len(djen_resultado["comunicacoes"]),
        }
        _emitir(
            payload,
            args.out,
            "DJEN",
            (lambda: formatacao.texto_resultado_djen(payload)) if texto else None,
        )
        return 0 if djen_resultado["status"] == "ok" else 1

    if comando == "tabela":
        dados = _ler_json(args.arquivo)
        registros = _registros_da_tabela(dados, args.colecao)
        try:
            csv_resultado = exports.to_csv(registros)
        except (TypeError, ValueError) as exc:
            raise ArquivoInvalido(f"Não foi possível montar a tabela: {exc}") from exc
        destino = _validar_saida_em_lote(args.arquivo, args.out)
        if destino is None:
            sys.stdout.write(csv_resultado)
            return 0
        try:
            destino.write_text(csv_resultado, encoding="utf-8", newline="")
        except OSError as exc:
            raise DestinoInvalido(f"Não consegui gravar o CSV em '{destino}'.") from exc
        print(f"row_count={len(registros)}; CSV salvo em: {destino}")
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
        fontes = args.source or ALL_SOURCES
        _avisar(f"Consultando fontes selecionadas: {', '.join(fontes)}... (até 1 minuto)")
        extracao = api.extract_process(
            args.numero,
            sources=fontes,
            include_raw=args.raw,
            datajud_api_key=args.datajud_api_key,
            djen_data_inicio=args.djen_data_inicio,
            desde=args.desde,
            limite_movimentacoes=_limite(args.limite_movimentacoes),
            timeout=args.timeout,
        )
        _emitir(cast(JsonPayload, extracao), args.out, "Extração")
        return 0 if extracao.get("status") == "ok" else 1

    if comando == "batch":
        return _executar_batch(args)

    if comando == "autos":
        return _executar_autos(args)

    if comando == "timeline":
        return _linha_do_tempo(args, texto)

    parser.print_help()
    return 1


def _executar_batch(args: argparse.Namespace) -> int:
    destino = _abrir_saida_em_lote(args.arquivo, args.out)
    falhas = 0
    total = 0
    try:
        for item in api.iter_extract_processes(
            _numeros_do_arquivo(Path(args.arquivo)),
            sources=args.source or ALL_SOURCES,
            include_raw=args.raw,
            datajud_api_key=args.datajud_api_key,
            djen_data_inicio=args.djen_data_inicio,
            desde=args.desde,
            timeout=args.timeout,
            datajud_retry=args.datajud_retries,
            limite_movimentacoes=args.limite_movimentacoes or None,
            max_workers=args.workers,
        ):
            destino.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            destino.flush()
            total += 1
            falhas += item.get("status") != "ok"
            if sys.stderr.isatty():
                print(f"Processados: {total}; falhas: {falhas}", file=sys.stderr, flush=True)
    finally:
        if destino is not sys.stdout:
            destino.close()
    if args.out != "-":
        print(f"JSONL salvo em {args.out}; registros: {total}; falhas: {falhas}", file=sys.stderr)
    return 1 if falhas else 0


def _executar_autos(args: argparse.Namespace) -> int:
    if args.source == ESAJ_TJSP_2G and (args.autenticar_advogado or args.pedir_senha_processo):
        raise AcessoRestrito("As opções de autenticação de autos se aplicam ao CPoPG.")
    _validar_saida_em_lote(args.arquivo, args.out)
    total = 0
    parciais = 0
    falhas = 0
    sessao = None
    if args.autenticar_advogado:
        _avisar("Complete o login no navegador oficial do e-SAJ...")
        sessao = autenticacao.autenticar_esaj_no_navegador(
            executable_path=args.executavel_navegador
        )

    def provedor_senha(numero: str, documentos: list[Any]) -> str | None:
        if not args.pedir_senha_processo:
            return None
        return getpass(f"Senha do processo {numero} (entrada oculta): ")

    if args.autenticar_advogado or args.pedir_senha_processo:
        client = NanoJudClient(
            config=NanoJudConfig(timeout=args.timeout),
            session=sessao,
            senha_processo_provider=provedor_senha if args.pedir_senha_processo else None,
        )
        obter_autos = client.iter_extract_dockets
    else:
        obter_autos = api.iter_extract_dockets
    destino = _abrir_saida_em_lote(args.arquivo, args.out)
    try:
        for item in obter_autos(
            _numeros_do_arquivo(Path(args.arquivo)),
            destination=args.out_dir,
            max_documents_per_process=args.max_documentos,
            read_documents=args.ler_documentos,
            document_max_chars=args.max_chars,
            limite_movimentacoes=args.limite_movimentacoes or None,
            desde=args.desde,
            include_extract=args.incluir_extrato,
            timeout=args.timeout,
            source=args.source,
        ):
            destino.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            destino.flush()
            total += 1
            parciais += item.get("status") == "partial"
            falhas += item.get("status") in {"error", "unsupported"}
    finally:
        if destino is not sys.stdout:
            destino.close()
    if args.out != "-":
        print(
            f"Manifesto JSONL salvo em {args.out}; registros: {total}; "
            f"parciais: {parciais}; falhas: {falhas}",
            file=sys.stderr,
        )
    return 1 if parciais or falhas else 0


def _linha_do_tempo(args: argparse.Namespace, texto: bool) -> int:
    fontes = args.source or ("esaj", "datajud", "djen")
    _avisar(f"Consultando fontes selecionadas: {', '.join(fontes)}... (até 1 minuto)")
    extracao = cast(
        dict[str, Any],
        api.extract_process(
            args.numero,
            sources=fontes,
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
