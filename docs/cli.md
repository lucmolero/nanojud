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
| `search` | `consultar` | Resumo do processo com estado, fonte, grau e data da coleta |
| `partes` | | Partes e advogados por polo |
| `esaj-2g` | | Capas e movimentações dos resultados públicos do e-SAJ/TJSP de 2º grau |
| `esaj-2g-pdf` | | Baixa uma peça individual do e-SAJ/TJSP de 2º grau |
| `timeline` | `linha-do-tempo` | Andamentos de todas as fontes em ordem cronológica |
| `djen` | | Intimações e publicações do DJEN com estado de completude |
| `datajud` | | Dados do processo no DataJud (qualquer tribunal) |
| `extract` | `extrair` | Consulta agregada: e-SAJ, DataJud e DJEN por padrão; PJe/TJMG, e-SAJ 2G, eproc/TJSP, TJRJ 1G e MNI podem ser selecionados com `--source` |
| `extrato` | | Extrato completo do eSAJ em JSON |
| `tabela` | `csv` | Exporta uma coleção JSON para CSV, preservando proveniência |
| `ler-pecas` | | Texto de peças acessíveis, sem salvar PDF |
| `baixar` | | PDFs de peças acessíveis |

Opções da linha do tempo com nome em português: `--fonte` (`--source`), `--limite` (`--limit`), `--recentes-primeiro` (`--recent-first`), `--max-caracteres` (`--max-text-chars`).

`nanojud esaj-2g NUMERO` devolve JSON e pode listar vários recursos para o CNJ
de origem. Use `--timeout` para ajustar o limite por requisição. Confira
`status` e `movimentacoes_completas` antes de interpretar a coleta.

Para baixar uma peça, use o CNJ próprio do resultado e o `cd_documento`
listado em uma movimentação. A CLI só substitui o arquivo de saída após
receber um PDF válido.

```bash
nanojud esaj-2g-pdf NUMERO CD_DOCUMENTO --out peca.pdf
```

`--max-paginas` ajusta o limite da busca pelo vínculo, que termina assim
que a movimentação com a peça é encontrada.

## Exportar tabela CSV

Use uma saída de `extract` para exportar a timeline unificada:

```bash
nanojud extract 0015020-23.2010.8.26.0053 --out extracao.json
nanojud tabela extracao.json --out timeline.csv
```

O comando escolhe `timeline`, `movimentacoes` ou `comunicacoes` quando encontra
uma dessas coleções no JSON. Para escolher uma coleção aninhada, informe seu
caminho com pontos, como `--colecao data.djen`. Cada linha mantém a proveniência
disponível (`numero_cnj`, fonte, grau, tribunal e status por fonte). O comando
não executa uma nova consulta; transforma os registros já salvos. Para enviar
CSV ao pipe, omita `--out` ou use `--out -`.

O CSV neutraliza textos que poderiam ser interpretados como fórmulas por
planilhas. O JSON de origem e os dados estruturados da API permanecem intactos.

O comando `djen` devolve `status`, `completo`, `paginas`, `comunicacoes` e
`avisos`. Quando uma página posterior falha, preserva o que foi obtido, informa
`partial` no JSON ou no texto e termina com código de saída `1`; erros de
consulta que impedem qualquer resultado continuam usando o código `2`.

Para incluir o CPoSG na extração única ou em lote, selecione
`--source esaj_tjsp_2g`. Exemplo com lista de CNJs em arquivo
`nanojud batch processos.txt --source esaj_tjsp_2g --out lote.jsonl`.

Para obter em lote as peças vinculadas aos movimentos de segundo grau:

```bash
nanojud autos processos.txt --source esaj_tjsp_2g --out-dir peças --out manifesto.jsonl
```

O manifesto associa cada peça ao CNJ do recurso e indica a decisão de acesso.
O escopo é `vinculos_movimentacoes`. `--ler-documentos` extrai texto em memória.

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

Mostra classe, assunto, situação, última movimentação, estado de completude, fonte, grau e data da coleta. Para números do TJSP, usa o e-SAJ de primeiro grau; para outros tribunais, consulta o DataJud (`fonte: datajud`), sem partes nem juiz. O DataJud pode apresentar o órgão julgador no campo de vara. Quando a fonte não informa algum metadado, o campo correspondente fica vazio ou é indicado como não informado.

## Extrato completo

```bash
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
```

Salva o extrato completo em um arquivo JSON.

Sem `--out`, os comandos `extrato`, `datajud`, `djen`, `extract`, `timeline` e `ler-pecas` imprimem o JSON na tela; com `--out`, gravam o arquivo e informam o caminho.

`extrato`, `extract`, `baixar` e `ler-pecas` aceitam `--timeout SEGUNDOS` (padrão 30) para limitar cada requisição de rede. Esse valor não é um prazo total da operação; no `extract`, o limite total das fontes continua sendo controlado pelo prazo interno da API.

Flags úteis:

- `--inspecionar-pecas`: tenta obter metadados de peças acessíveis à sessão.
- `--baixar-pecas`: tenta baixar peças acessíveis à sessão quando tecnicamente possível.
- `--limite-pecas 3`: limita a quantidade de peças que a NanoJud tenta baixar.
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

## Consultar o PJe/TJMG

O primeiro grau do PJe/TJMG está disponível como fonte opt-in na extração agregada:

```bash
nanojud extract 5060583-19.2021.8.13.0024 --source pje_tjmg --out pje-tjmg.json
```

A consulta percorre as páginas públicas observadas de movimentos e documentos, até 100 páginas por tabela. Quando uma página falha, o limite é excedido ou a paginação não pode ser verificada, o resultado é marcado `partial`. A ferramenta não acessa documentos protegidos. Use a API Python `baixar_documento_pje_tjmg` para salvar um PDF cujo botão oficial esteja disponível publicamente.

O comando `extract` sempre emite o envelope JSON, inclusive quando uma fonte falha. Seu código de saída é `0` quando o envelope tem `status=ok` e `1` quando tem `status=partial` ou `status=error`; scripts e agentes podem usar o código para detectar resultados incompletos sem perder o envelope gravado.

## Extração Agregada

```bash
nanojud extract 0015020-23.2010.8.26.0053 --source datajud --source djen --out extraction.json
```

## Consulta em lote (JSONL)

Prepare um arquivo UTF-8 com um CNJ por linha. Linhas vazias e comentários iniciados por `#` são ignorados. O comando grava uma linha JSON por processo e faz flush após cada resultado; se a execução for interrompida, os registros já gravados permanecem disponíveis.

```bash
nanojud batch processos.txt --source datajud --out resultados.jsonl
```

O perfil padrão do lote consulta e-SAJ, DataJud e DJEN. PJe/TJMG, TJRJ 1G, eproc/TJSP e MNI permanecem opt-in também no lote; selecione `tjrj_1g` para incluir o TJRJ de primeiro grau. Para MNI, configure endpoint, versão e credencial nas variáveis `NANOJUD_MNI_*` descritas na [referência da API](api-reference.md#cliente-generico-mni-soap-30-e-222); a credencial não deve ser passada como argumento de linha de comando. `extract` e `batch` aceitam a seleção explícita `mni`.

Por padrão, as consultas são sequenciais (`--workers 1`) para reduzir pressão sobre os portais. É possível usar até 8 trabalhadores com `--workers N`; respeite as políticas e limites publicados por cada tribunal. `--timeout` define o timeout por fonte, `--datajud-retries` define tentativas por processo (3 por padrão) e `--limite-movimentacoes 0` solicita o histórico completo do eSAJ. O código de saída é 1 se algum item tiver falha ou resultado parcial. A saída padrão é stdout em JSONL; mensagens de progresso vão para stderr. Com `--workers` maior que 1, uma interrupção cancela tarefas ainda não iniciadas e aguarda as que já estão ativas; o tempo de espera pode chegar a `prazo_total` (60 s por processo por padrão).

Se a entrada não for UTF-8 válido, o comando informa o erro em stderr quando a saída é JSONL em stdout, sem misturar texto de erro com os registros. Registros já gravados permanecem; confira o código de saída `2` e corrija o arquivo antes de continuar.

## Consultar processos e obter autos acessíveis

O fluxo de autos em lote roteia processos eSAJ/TJSP e PJe/TJMG pelo CNJ. Ele cria uma subpasta por CNJ e grava um manifesto JSONL incremental:

```bash
nanojud autos processos.txt --out-dir autos --max-documentos 10 --out manifesto.jsonl
```

`autos` aceita `--timeout SEGUNDOS` (padrão 30), aplicado a cada requisição e validado antes de abrir o manifesto. `Ctrl+C` interrompe o fluxo entre operações; uma requisição já iniciada pode levar até o timeout para retornar. As linhas já gravadas no JSONL são preservadas.

O caminho de `--out` precisa ser diferente do arquivo de entrada; a CLI recusa a colisão antes de iniciar a consulta para preservar a lista de processos.

Para uma carteira em que você tenha autorização, instale `nanojud[autenticacao]` e use `--autenticar-advogado`; `--pedir-senha-processo` pede uma senha localmente para cada processo que a exigir:

```bash
nanojud autos processos.txt --out-dir autos --max-documentos 0 --limite-movimentacoes 0 --autenticar-advogado --pedir-senha-processo --out manifesto.jsonl
```

Use `--ler-documentos` para extrair texto em memória sem salvar PDFs, `--max-chars` para limitar o texto de cada documento e `--incluir-extrato` para incluir o extrato integral no manifesto. No PJe/TJMG, o lote percorre até 100 páginas por tabela e marca o item `partial` quando restam páginas ou ocorre uma falha. O modo padrão consulta sem login; o portal decide quais documentos serão liberados. Os estados `no_documents`, `partial` e `unsupported` são distintos de uma consulta bem-sucedida com documentos. Outros tribunais ainda não têm adaptador de autos em lote.

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

## Baixar peças acessíveis à sessão

```bash
nanojud baixar extrato.json --out pecas --limite 3
```

Usa um extrato já gerado para tentar baixar documentos acessíveis. Para autenticar ou fornecer senha processual, passe `--autenticar-advogado` e/ou `--pedir-senha-processo`; a CLI reconsulta o processo para manter a sessão.

## Ler peças sem salvar PDF

```bash
nanojud ler-pecas extrato.json --limite 3 --max-chars 4000 --out pecas_texto.json
```

Lê documentos acessíveis pela sessão em memória. Ela não grava PDFs em disco; quando o conteúdo é PDF, extrai texto com `pypdf` se o parser estiver instalado. Pode-se usar a autenticação oficial e a senha processual com as opções descritas em `nanojud ler-pecas --ajuda`.

## Boas práticas

- Evite automações agressivas.
- Salve saídas em ambiente protegido.
- Não publique JSONs reais com dados pessoais em issues ou exemplos.
