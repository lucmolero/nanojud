# CLI

A CLI `nanojud` consulta processos pelo terminal, em português, sem escrever código. Se você nunca usou terminal, comece pelo [Guia do advogado](guia-do-advogado.md).

## Ajuda e versão

```bash
nanojud --ajuda
nanojud consultar --ajuda
nanojud --versao
```

A ajuda lista os comandos, tem exemplos e explica cada opção. `python -m nanojud ...` funciona no lugar de `nanojud ...`.

## Comandos e apelidos

Os nomes em inglês continuam valendo; os apelidos em português fazem o mesmo.

| Comando | Apelido | O que faz |
| ------- | ------- | --------- |
| `search` | `consultar` | Resumo do processo: classe, vara, situação e última movimentação |
| `partes` | | Partes e advogados por polo |
| `timeline` | `linha-do-tempo` | Andamentos de todas as fontes em ordem cronológica |
| `djen` | | Intimações e publicações do DJEN |
| `datajud` | | Dados do processo no DataJud (qualquer tribunal) |
| `extrato` | | Extrato completo do eSAJ em JSON |
| `extract` | `extrair` | Todas as fontes em um envelope JSON |
| `ler-pecas` | | Texto de peças públicas, sem salvar PDF |
| `baixar` | | PDFs de peças públicas |

Opções da linha do tempo com nome em português: `--fonte` (`--source`), `--limite` (`--limit`), `--recentes-primeiro` (`--recent-first`), `--max-caracteres` (`--max-text-chars`).

## Formato de saída: texto ou JSON

`consultar`, `partes`, `linha-do-tempo` e `djen` aceitam `--formato`:

- `texto`: leitura no terminal, com datas em dia/mês/ano.
- `json`: todos os campos, para planilhas, sistemas e IA.
- `auto` (padrão): texto quando a saída é o terminal, JSON quando é redirecionada (`> arquivo`, `|`) ou quando você usa `--out`.

Os demais comandos sempre geram JSON. Qualquer comando aceita `--out ARQUIVO` para gravar o resultado e informar o caminho.

## Andamento e erros

Em terminal, os comandos avisam no `stderr` o que estão consultando (por exemplo, "Consultando eSAJ, DataJud e DJEN em paralelo... (até 1 minuto)"), porque algumas consultas levam vários segundos. Esse aviso não aparece quando a saída é redirecionada.

Erros previstos retornam código `2`. No terminal vêm em texto, com **o que fazer**:

```text
Erro: Número CNJ deve ter 20 dígitos.
O que fazer: Confira o número do processo. O padrão CNJ tem 20 dígitos, por exemplo 0015020-23.2010.8.26.0053.
```

Com a saída redirecionada, o erro é um JSON com `status`, `erro`, `mensagem` e `dica`. Ctrl+C interrompe a consulta (código `130`).

## Resumo do processo

```bash
nanojud consultar 0015020-23.2010.8.26.0053
```

Mostra classe, assunto, situação, foro, vara, juiz e a última movimentação. Fora do TJSP o resumo vem do DataJud (`fonte: datajud`), sem partes, foro nem juiz.

## Extrato completo

```bash
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
```

Salva o extrato completo em um arquivo JSON.

Sem `--out`, os comandos `extrato`, `datajud`, `djen`, `extract`, `timeline` e `ler-pecas` imprimem o JSON na tela; com `--out`, gravam o arquivo e informam o caminho.

Flags úteis:

- `--inspecionar-pecas`: tenta obter metadados de peças públicas candidatas.
- `--baixar-pecas`: tenta baixar peças públicas candidatas quando tecnicamente possível.
- `--limite-pecas 3`: limita a quantidade de peças baixadas.
- `--salvar-html`: salva HTML bruto da consulta para auditoria local.
- `--limite-movimentacoes 100`: máximo de movimentações buscadas no eSAJ (`0` busca todas). O eSAJ entrega 5 por requisição, com pausa entre páginas; processos grandes levam mais tempo. Quando há corte, `origem.movimentacoes_completas` fica `false` e `origem.aviso_movimentacoes` explica.

## Novidades desde uma data e timeline dos eventos recentes

```bash
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --desde 2026-08-01
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --recentes-primeiro --limite 20
nanojud extract 0015020-23.2010.8.26.0053 --limite-movimentacoes 0
```

- `--desde AAAA-MM-DD`: só movimentações e comunicações a partir da data; a paginação do eSAJ para ao chegar em dados mais antigos.
- `--recentes-primeiro --limite N`: busca no eSAJ só as N movimentações mais recentes, o que é bem mais rápido que a timeline completa.
- `--limite-movimentacoes`: máximo de movimentações do eSAJ (`0` busca todas; padrão 100).

## Listar partes

```bash
nanojud partes 0015020-23.2010.8.26.0053
```

Imprime as partes classificadas por polo quando a estrutura da página permite.

## Consultar DJEN

```bash
nanojud djen 0015020-23.2010.8.26.0053 --data-inicio 2026-01-01 --out djen.json
```

Salva comunicações encontradas no DJEN em JSON.

## Consultar DataJud

```bash
nanojud datajud 0015020-23.2010.8.26.0053 --out datajud.json
```

Salva dados processuais estruturados da API pública DataJud/CNJ em JSON.

A biblioteca usa a chave pública vigente documentada na Wiki oficial do DataJud/CNJ como fallback. Use `--api-key` apenas se o CNJ rotacionar a chave ou se você quiser informar outra explicitamente.

## Extração Agregada

```bash
nanojud extract 0015020-23.2010.8.26.0053 --source datajud --source djen --out extraction.json
```

Gera envelope versionado por fonte.

## Timeline

```bash
nanojud timeline 0015020-23.2010.8.26.0053 --source esaj --source djen --source datajud --out timeline.json
```

Gera timeline cronológica de registros extraídos, sem classificação de fase, risco ou relevância.

Flags úteis para agentes de IA:

- `--recent-first`: retorna eventos mais recentes primeiro.
- `--limit 20`: limita a quantidade de eventos retornados.
- `--sem-texto`: remove textos longos dos eventos.
- `--max-text-chars 500`: trunca textos longos por evento.
- `--envelope`: salva o envelope completo, incluindo `warnings`, `errors` e `source_status`.

## Baixar peças públicas candidatas

```bash
nanojud baixar extrato.json --out pecas --limite 3
```

Usa um extrato já gerado para tentar baixar documentos públicos candidatos.

## Ler peças públicas sem salvar PDF

```bash
nanojud ler-pecas extrato.json --limite 3 --max-chars 4000 --out pecas_texto.json
```

Lê documentos públicos candidatos em memória. A ferramenta reabre o processo na sessão e carrega as movimentações até o documento, o que leva cerca de 10 segundos. Ela não grava PDFs em disco; quando o conteúdo é PDF público, extrai texto com `pypdf` se o parser estiver instalado. Documentos restritos por senha, captcha ou sigilo não são acessados.

## Boas práticas

- Evite automações agressivas.
- Salve saídas em ambiente protegido.
- Não publique JSONs reais com dados pessoais em issues ou exemplos.
