# Extração Agregada

A API de extração agregada combina eSAJ, DataJud e DJEN em um envelope versionado. PJe/TJMG, TJRJ 1G, eproc/TJSP e MNI são fontes opt-in. A seleção é normalizada e cada fonte aparece uma vez, na ordem da primeira ocorrência.

```python
from nanojud import api

resultado = api.extract_process(
    "0015020-23.2010.8.26.0053",
    sources=("datajud", "djen"),
    timeout=10,
    datajud_retry=1,
    prazo_total=20,
)

print("status:", resultado["status"])
print("source_status:", resultado["source_status"])
print("timeline_count:", len(resultado["timeline"]))
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

Para e-SAJ/TJSP, `source_status.esaj.status` fica `partial` quando a fonte não confirma a paginação completa das movimentações; o envelope também fica `partial` e preserva o aviso em `warnings`. O `get_extrato` direto usa `status="partial"` para a mesma condição, e o resumo rápido mantém esse estado e a mensagem. A ausência do indicador de completude também é tratada como não confirmada na extração agregada.

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

## Fontes em paralelo e prazo total

`extract_process` consulta eSAJ, DataJud, DJEN e, quando selecionado, PJe/TJMG ao mesmo tempo. `timeout` precisa ser positivo e finito, com máximo de 86.400 segundos (24 horas); ele limita cada operação de rede. `prazo_total` (padrão 60 s) limita a espera pelo envelope e aceita `None` para aguardar sem prazo total, mas isso não remove os timeouts de rede. O tempo restante é propagado para DataJud e PJe/TJMG; no PJe, se o prazo vence na paginação, dados já coletados são preservados como `partial`. Uma fonte que estoura o prazo vira erro isolado em `errors` e `source_status`, e as demais voltam normalmente. O executor de fontes é compartilhado pelo processo e limita a 32 tarefas submetidas (em execução ou aguardando vaga); tarefas ainda não iniciadas são canceladas quando a chamada vence. Python não interrompe à força uma requisição que já começou, então uma fonte vencida pode continuar até sua operação de rede/paginação terminar, ocupando uma vaga desse limite. `prazo_total` limita a resposta da biblioteca, não é cancelamento imediato da conexão. Fora do TJSP, o eSAJ aparece como `nao_aplicavel`, sem erro.

Omitir `sources` aplica esse padrão de três fontes. Para consultar apenas algumas, informe uma sequência não vazia, como `("datajud", "djen")`. Uma seleção vazia é rejeitada antes de iniciar qualquer fonte; ela não equivale ao padrão.

`desde` (AAAA-MM-DD) restringe movimentações e comunicações e reduz a paginação do eSAJ.

### PJe/TJMG (opt-in)

O adaptador de primeiro grau do TJMG pode ser selecionado como `pje_tjmg` em `sources`. Ele consulta a busca pública e percorre as páginas públicas de movimentações e documentos até 100 páginas por tabela. A resposta fica `partial` quando a paginação não é verificável, uma página falha ou o limite é excedido. A lista contém documentos que a tela oferece para visualização pública; isso não comprova cobertura completa dos autos.

O eproc/TJSP pode ser selecionado por grau com `sources=("eproc_tjsp_1g",)` ou `sources=("eproc_tjsp_2g",)`. Instale o extra `nanojud[autenticacao]` e o Chromium do Playwright (`python -m playwright install chromium`). Os adaptadores usam a Consulta Unificada; a operação ponta a ponta ainda não foi validada em consulta positiva. Não há download de peças e ambos permanecem fora do perfil padrão. Uma exigência de verificação interativa é retornada como estado de acesso, sem dados processuais inventados.

### MNI SOAP 3.0 e 2.2.2 (opt-in)

Selecione `mni` para consultar uma instalação MNI explicitamente configurada. Em Python, passe `MNI3Config` ou `MNI222Config` por `NanoJudConfig(mni_config=...)`. CLI, MCP local e lotes selecionam o contrato pelo ambiente `NANOJUD_MNI_VERSION` (`3.0` padrão legado ou `2.2.2`). MNI 3.0 aceita token ou usuário/senha; MNI 2.2.2 exige `NANOJUD_MNI_USERNAME` + `NANOJUD_MNI_PASSWORD` e não aceita token. Ambos requerem `NANOJUD_MNI_ENDPOINT`; `TRIBUNAL`, `GRAU` e `MOVIMENTACOES_COMPLETAS` são opcionais. `PESSOA_VINCULADA` aplica-se ao 3.0. Movimentos completos ficam falsos por padrão; marque true somente quando a instalação garantir histórico integral. Não há endpoint padrão nem fallback para tribunal presumido. Sem configuração, a fonte MNI retorna `ConsultaIndisponivel` no envelope, sem impedir resultados das demais.

```python
from nanojud import MNI3Config, NanoJudConfig, NanoJudClient

config = MNI3Config(
    endpoint="https://ENDPOINT-FORNECIDO-PELO-TRIBUNAL/Servico.svc",
    token="TOKEN-FORNECIDO-PELO-TRIBUNAL",
    tribunal="TJSP",
    grau="1G",
)
cliente = NanoJudClient(NanoJudConfig(mni_config=config))
resultado = cliente.extract_process(
    "1001194-30.2024.8.26.0114",
    sources=("mni",),
)
```

Essa integração exercita o contrato genérico por meio dos mesmos envelopes e timeline usados pelas outras fontes. Ela não comprova disponibilidade do endpoint TJSP; cada consulta cria sessão isolada e o lote sequencial é o padrão. Confirme os limites operacionais da instalação antes de aumentar concorrência.

Uma configuração `mni` representa uma instalação por chamada, de qualquer tribunal que exponha o contrato configurado. A fonte agregada solicita capa, partes e movimentos, mas ainda não solicita o índice documental. Para metadados de peças, use `consultar_extrato(..., incluir_documentos=True)`; no MNI 2.2.2, `consultar_documentos_processo(...)` consulta documentos inline pela operação `consultarProcesso`, enquanto no 3.0 usa a operação separada. A disponibilidade de MNI não decorre do número CNJ nem do suporte da biblioteca ao protocolo. Os contratos foram testados offline; ainda não existe consulta autenticada live nesta instalação NanoJud.

```python
from nanojud import api

resultado = api.extract_process(
    "5060583-19.2021.8.13.0024",
    sources=("pje_tjmg",),
)
```

Para uma peça cujo botão oficial “Gerar PDF” esteja disponível publicamente, `api.ler_documento_pje_tjmg(url)` extrai texto em memória e `api.baixar_documento_pje_tjmg(url, destino)` grava o PDF escolhido pelo chamador. Esses métodos não desbloqueiam documentos protegidos. No CLI, selecione a fonte com `nanojud extract CNJ --source pje_tjmg --out resultado.json`.

### e-SAJ/TJSP de segundo grau (opt-in)

Selecione `esaj_tjsp_2g` para consultar o CPoSG pela API, CLI ou MCP. A
fonte `esaj` consulta o CPoPG de primeiro grau. O perfil padrão usa
`esaj`, `datajud` e `djen`.

```python
from nanojud import api

numero = "2034550-16.2025.8.26.0000"
resultado = api.extract_process(
    numero,
    sources=("esaj_tjsp_2g", "datajud"),
    timeout=10,
    datajud_retry=1,
    prazo_total=20,
)
```

O envelope guarda os recursos em `data.esaj_tjsp_2g.resultados`. A
linha do tempo preserva o CNJ próprio, o grau e a URL de cada resultado.
`source_status` indica coleta parcial e os resultados guardam os avisos
individuais. O adaptador usa sessão pública independente e até dez páginas
de movimentos por resultado. O filtro `desde` aplica-se à linha do tempo
unificada.

## DataJud com mais de um grau

O DataJud pode guardar vários registros por grau (G1, TR, G2...) para o mesmo número CNJ. A consulta solicita dez por página e usa `search_after` para percorrer até dez páginas quando o total exato excede a primeira. O menor grau retornado define `classe`, `orgao_julgador` e `grau`; `graus` resume cada registro (classe, órgão, data de ajuizamento e total de movimentos); e cada movimento traz o `grau` de origem. `metadata.records_pages` e `records_returned` mostram o volume percorrido. Falha de página, total não exato, cursor ausente/repetido ou limite excedido mantém `status=partial` e os registros já obtidos; não se declara completude sem total exato reconciliado.

## Divergências entre fontes

O envelope inclui `divergencias`, calculado só quando as fontes envolvidas retornaram dados:

- `severidade: "divergencia"`: classe, data de distribuição (eSAJ) x ajuizamento (DataJud) e data da última movimentação diferentes.
- `severidade: "informacao"`: DataJud com mais de um grau e comunicações do DJEN que são de incidentes (`incidente` preenchido, ex.: `/47`).

Cada item traz `campo`, `mensagem` e `valores` por fonte. A lib aponta a diferença; quem decide qual fonte está certa é você, conferindo no sistema oficial.

## CLI

```bash
nanojud datajud 0015020-23.2010.8.26.0053 --out datajud.json
nanojud extract 0015020-23.2010.8.26.0053 --source datajud --source djen --out extraction.json
nanojud extract 5060583-19.2021.8.13.0024 --source pje_tjmg --out pje-tjmg.json
nanojud timeline 0015020-23.2010.8.26.0053 --source esaj --source djen --source datajud --out timeline.json
```
