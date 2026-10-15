# Extração Agregada

A API de extração agregada combina eSAJ, DataJud e DJEN em um envelope versionado.

```python
from nanojud import api

resultado = api.extract_process(
    "0015020-23.2010.8.26.0053",
    sources=("datajud", "djen"),
)

print(resultado["status"])
print(resultado["timeline"])
```

## Envelope

O retorno contém:

- `schema_version`: versão do contrato de extração.
- `package_version`: versão da biblioteca.
- `status`: `ok`, `partial` ou `error`.
- `numero_cnj`: número normalizado.
- `sources`: fontes solicitadas.
- `extracted_at`: data técnica da extração.
- `data`: resultado por fonte.
- `timeline`: registros cronológicos.
- `warnings`: avisos técnicos.
- `errors`: falhas isoladas por fonte.

## Timeline Cronológica

A timeline é apenas uma ordenação temporal dos registros extraídos.

Ela não contém:

- fase;
- risco;
- relevância;
- evento-chave;
- opinião jurídica.

Cada registro preserva:

- `fonte`;
- `tipo_registro`;
- `data`;
- `data_original`;
- `codigo_original`;
- `titulo`;
- `texto`;
- `documentos`;
- `payload_origem`, quando `include_raw=True`.

## DataJud com mais de um grau

O DataJud guarda um registro por grau (G1, TR, G2...) para o mesmo número CNJ. O resultado consolida todos: o menor grau define `classe`, `orgao_julgador` e `grau`; `graus` resume cada registro (classe, órgão, data de ajuizamento e total de movimentos); e cada movimento traz o `grau` de origem.

## Divergências entre fontes

O envelope inclui `divergencias`, calculado só quando as fontes envolvidas retornaram dados:

- `severidade: "divergencia"`: classe, data de distribuição (eSAJ) x ajuizamento (DataJud) e data da última movimentação diferentes.
- `severidade: "informacao"`: DataJud com mais de um grau e comunicações do DJEN que são de incidentes (`incidente` preenchido, ex.: `/47`).

Cada item traz `campo`, `mensagem` e `valores` por fonte. A lib aponta a diferença; quem decide qual fonte está certa é você, conferindo no sistema oficial.

## CLI

```bash
nanojud datajud 0015020-23.2010.8.26.0053 --out datajud.json
nanojud extract 0015020-23.2010.8.26.0053 --source datajud --source djen --out extraction.json
nanojud timeline 0015020-23.2010.8.26.0053 --source esaj --source djen --source datajud --out timeline.json
```
