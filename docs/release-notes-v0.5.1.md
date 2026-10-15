# Release v0.5.1

Esta release corrige a extracao de movimentacoes do eSAJ, que havia quebrado, e traz varias correcoes de dados e seguranca encontradas em testes de uso real.

## Destaques

- eSAJ: as movimentacoes voltam a ser extraidas. O eSAJ passou a carregar a lista sob demanda (`carregarMovimentacoesAjax.do`); a lib agora pagina por cursor, com limite configuravel e pausa entre paginas.
- DataJud: consulta todos os graus do numero CNJ em vez de um registro arbitrario.
- Envelope de `extract_process` ganha `divergencias`, que aponta diferencas entre eSAJ e DataJud e contexto de incidentes e graus.
- Seguranca: o `href` de documentos lido de um extrato JSON externo so e aceito se for do eSAJ.

## Correcoes

- `search`, `extrato` e a timeline voltam a trazer movimentacoes e ultima movimentacao do eSAJ.
- `partes` preenche `polo_ativo` e `polo_passivo` com as abreviaturas do eSAJ (`Imptte`, `Imptdo` etc.).
- `relacionados.incidentes` nao traz mais a linha vazia de espacamento.
- DJEN preserva `numero_processo`, `incidente`, status e cancelamento, `hash`, `numero_comunicacao` e advogados.
- Timeline com ids unicos para movimentos repetidos; eventos DJEN passam a ter `numero_cnj`.

## Novos recursos

- `limite_movimentacoes` (padrao 100; `0` ou `None` busca todas) em `api.get_extrato`, `NanoJudConfig`, CLI `extrato --limite-movimentacoes` e MCP `consultar_esaj`. Quando ha corte ou falha parcial, `origem.movimentacoes_completas` fica `false` e `origem.aviso_movimentacoes` explica; o envelope agregado registra um warning.
- DataJud: `graus` resume cada registro e cada movimento traz o `grau` de origem.
- Workflow semanal `Live smoke` e testes live de DataJud e DJEN.

## Mudanca de comportamento

Os comandos `extrato`, `datajud`, `djen`, `extract`, `timeline` e `ler-pecas` agora imprimem o JSON na tela quando `--out` nao e informado. Antes gravavam um arquivo no diretorio atual (`extrato.json`, `datajud.json` etc.). Scripts que dependiam desse arquivo devem passar `--out`.

## Observacao sobre as fontes

No processo de demonstracao, o DataJud indexa so o registro de um incidente (Requisicao de Pequeno Valor) sob o mesmo numero, e por isso `divergencias` aponta diferencas em relacao ao eSAJ. Isso vem das fontes, nao da biblioteca.

## Validacao

Suite offline com 155 testes, ruff, mypy e cobertura minima de 90%. Testes live validados contra eSAJ, DataJud e DJEN reais.
