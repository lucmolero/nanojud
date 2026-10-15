# Contratos de Dados

Os retornos da API são dicionários Python simples, documentados por `TypedDict` em `nanojud.models`.

Contratos de extração agregada ficam em `nanojud.schemas`.

## `api.search_processo`

Retorna `ResumoProcesso`:

```json
{
  "numero": "0015020-23.2010.8.26.0053",
  "classe": "Ação Civil Pública",
  "assunto": "Meio Ambiente",
  "foro": "Foro Central Cível",
  "vara": "2ª Vara Cível",
  "juiz": "Dr. Juiz Exemplo",
  "ultima_movimentacao": "Conclusos para decisão",
  "ultima_data": "30/07/2026",
  "url": "https://esaj.tjsp.jus.br/cpopg/show.do?...",
  "status": "ok",
  "mensagem": "Processo consultado com sucesso"
}
```

## `api.get_extrato`

Retorna `Extrato` com:

- `origem`: fonte, tribunal, URL final e data da coleta, além de `movimentacoes_completas` e `aviso_movimentacoes` (corte por limite ou falha parcial na paginação).
- `dados_basicos`: número, classe, assunto, foro, vara, juiz e campos auxiliares.
- `partes`: partes principais, todas as partes e polos classificados.
- `movimentacoes`: data, título, teor, metadados e documentos vinculados.
- `documentos`: candidatos públicos e restritos por senha.
- `peticoes_diversas`, `audiencias`, `relacionados`: tabelas complementares quando presentes.

## Estabilidade

Campos novos podem ser adicionados em versões minor. Campos existentes só devem mudar formato em versão major ou com aviso explícito no changelog.

## `api.extract_process`

Retorna envelope versionado com dados separados por fonte:

```json
{
  "schema_version": "1.0",
  "package_version": "0.4.0",
  "status": "ok",
  "numero_cnj": "0015020-23.2010.8.26.0053",
  "sources": ["esaj", "datajud", "djen"],
  "data": {
    "esaj": {},
    "datajud": {},
    "djen": []
  },
  "timeline": [],
  "warnings": [],
  "errors": [],
  "divergencias": []
}
```

`timeline` é cronológica e não inclui fase, relevância, risco ou interpretação jurídica.
