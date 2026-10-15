# Release v0.5.2

Esta release torna a consulta mais rapida e mais confiavel, e corrige dados que a lib perdia ou reportava errado. Nao ha funcoes de interpretacao: continua sendo uma lib de consulta processual.

## Destaques

- eSAJ: consultas em sequencia muito rapida recebiam o aviso de "multiplas consultas simultaneas" no lugar do processo, e a lib reportava isso como "processo nao encontrado". Agora ha nova tentativa apos pausa e, se o bloqueio persistir, o erro e de indisponibilidade com mensagem clara.
- `search` ficou bem mais rapido: busca so uma pagina de movimentacoes (cerca de 11 s para 1 s no processo de demonstracao).
- Fontes em paralelo: `extract_process` consulta eSAJ, DataJud e DJEN ao mesmo tempo, com `prazo_total` (padrao 60 s). Uma fonte lenta vira erro isolado e as demais voltam.
- `desde` (AAAA-MM-DD): restringe movimentacoes e comunicacoes e interrompe a paginacao do eSAJ ao chegar em dados antigos.

## Correcoes de dados

- `partes.todas` vinha vazio em processos que so trazem a tabela de partes principais; agora repete as principais.
- `dados_basicos` ganha `situacao` (ex.: Extinto) e `etiquetas` do cabecalho do processo no eSAJ.
- Fora do TJSP, o eSAJ aparece como `nao_aplicavel` em `source_status`, sem gerar erro.

## Novos recursos

- `desde` em `api.get_extrato`, `api.extract_process`, CLI (`extract`, `timeline`) e MCP.
- `timeline --recent-first --limit N` (e `gerar_timeline` no MCP) busca no eSAJ so as N movimentacoes mais recentes.
- CLI `--limite-movimentacoes` em `extract` e `timeline` (`0` busca todas).
- MCP: `consultar_esaj` e `extrair_processo` aceitam `compacto`, que remove dados repetidos.

## Mudanca de comportamento

No MCP, `consultar_esaj` e `extrair_processo` passam a devolver por padrao a versao compacta (`compacto=true`): `extrair_processo` mantem so a timeline unificada, sem repetir movimentacoes e comunicacoes em `data`, e `consultar_esaj` omite texto repetido e documentos por movimentacao (a lista de documentos continua em `documentos`). Use `compacto=false` para o formato anterior.

Quando o limite de movimentacoes e pedido de proposito, o aviso de corte continua deixando o status do envelope como `partial`.

## Validacao

Suite offline com 174 testes, ruff, mypy e cobertura minima de 90%. Medido ao vivo no processo de demonstracao: `search` de 11,6 s para 0,8 s, e duas consultas seguidas na mesma sessao funcionando.
