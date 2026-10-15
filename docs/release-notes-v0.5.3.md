# Release v0.5.3

Esta release torna a CLI utilizavel por quem nao programa: comandos, ajuda e erros em portugues, saida legivel no terminal e um guia passo a passo para advogados. Nao ha mudanca nas consultas nem nos dados; continua sendo uma lib de consulta processual.

## Destaques

- CLI em portugues: ajuda, mensagens de uso e de erro, e apelidos para os comandos. Os nomes em ingles continuam valendo.
- Saida em texto legivel no terminal, com datas em dia/mes/ano. Ao redirecionar a saida ou usar `--out`, continua JSON, entao scripts existentes nao quebram.
- Erros com "O que fazer" e avisos de andamento durante consultas demoradas.
- Novo Guia do advogado (`docs/guia-do-advogado.md`): da instalacao do Python no Windows a primeira consulta, com tarefas do dia a dia, tabela de erros e glossario.

## CLI

- Apelidos: `consultar` (`search`), `linha-do-tempo` (`timeline`) e `extrair` (`extract`).
- Opcoes em portugues: `--fonte`, `--limite`, `--recentes-primeiro`, `--max-caracteres`, `--ajuda` e `--versao`.
- `--formato auto|texto|json` em `consultar`, `partes`, `linha-do-tempo` e `djen`. O padrao `auto` usa texto no terminal e JSON ao redirecionar a saida ou usar `--out`.
- `--out` tambem em `consultar` e `partes`.
- `python -m nanojud` funciona, e o resumo do `search` traz `situacao`.
- Erros previstos mostram "O que fazer" no terminal e o campo `dica` no JSON; arquivo de extrato ausente ou invalido tem mensagem clara; Ctrl+C encerra com mensagem.
- Sem o leitor de PDF, `ler-pecas` informa como instalar (`python -m pip install "nanojud[pdf]"`).
- `linha-do-tempo --recentes-primeiro --limite N` nao avisa mais do corte de movimentacoes que a propria CLI escolhe.

## Documentacao

- Guia do advogado, com instalacao no Windows, tarefas do dia a dia, como ler o resultado, solucao de problemas e glossario.
- README com "Primeiros passos em 2 minutos", quickstart que comeca pelo terminal, guia da CLI reescrito e pagina "Para advogados" apontando para o guia.

## Compatibilidade

Os comandos e opcoes em ingles continuam funcionando. A unica diferenca de comportamento e visivel so em terminal interativo: `consultar`, `partes`, `linha-do-tempo` e `djen` mostram texto em vez de JSON. Use `--formato json` para manter o JSON no terminal.

## Validacao

Suite offline com 226 testes, ruff, mypy, cobertura minima de 90% e `mkdocs build --strict` sem avisos. Instalacao limpa e comandos do guia verificados contra eSAJ, DataJud e DJEN reais.
