# Release v0.5.3

Esta release torna a CLI utilizavel por quem nao programa: comandos, ajuda e erros em portugues, saida legivel no terminal e um guia passo a passo para advogados. Tambem endurece as dependencias e a publicacao. Nao ha mudanca nas consultas nem nos dados; continua sendo uma lib de consulta processual.

A 0.5.3 inclui tudo da 0.5.2 (tag e release no GitHub, nao publicada no PyPI): correcao da leitura de pecas, ritmo minimo de consultas ao eSAJ, `search` fora do TJSP via DataJud, fontes em paralelo, `desde`, situacao e etiquetas. Veja as [notas da 0.5.2](release-notes-v0.5.2.md).

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

## Seguranca e confiabilidade

- Pisos de dependencia sem vulnerabilidades conhecidas (`pip-audit`): `requests>=2.33.0`, `pypdf>=6.19.0,<7` e `mcp>=1.30.0,<2`. Os pisos anteriores permitiam versoes com dezenas de avisos.
- `mcp>=1.0` estava errado: o servidor usa `FastMCP`, disponivel a partir do mcp 1.2.
- Links relativos do README quebravam na pagina do PyPI; agora apontam para o site da documentacao e para o GitHub.
- MCP: `consultar_datajud` aceita `compacto` (padrao `true`), que omite o `payload_origem` repetido; processos grandes passavam de 150 KB.
- Workflows de publicacao so rodam a partir de uma tag `vX.Y.Z` igual a versao do pacote.

## Compatibilidade

Os comandos e opcoes em ingles continuam funcionando. A unica diferenca de comportamento e visivel so em terminal interativo: `consultar`, `partes`, `linha-do-tempo` e `djen` mostram texto em vez de JSON. Use `--formato json` para manter o JSON no terminal.

## Validacao

Suite offline com 228 testes, ruff, mypy, cobertura minima de 90% e `mkdocs build --strict` sem avisos. Instalacao limpa (base, `[pdf]` e `[mcp]`), suite contra o wheel instalado com as versoes minimas e mais novas das dependencias, `pip-audit` limpo nos pisos, upgrade a partir da 0.5.1 e servidor MCP real por stdio, com comandos do guia verificados contra eSAJ, DataJud e DJEN reais. Obs.: o teste live do DataJud falhou na auditoria porque o indice do TJSP do CNJ estava fora do ar (outros indices respondiam lentos).
