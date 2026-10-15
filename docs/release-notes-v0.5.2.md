# Release v0.5.2

Esta release torna a consulta mais rapida e mais confiavel, e corrige dados que a lib perdia ou reportava errado. Nao ha funcoes de interpretacao: continua sendo uma lib de consulta processual.

## Destaques

- eSAJ: consultas em sequencia muito rapida recebiam o aviso de "multiplas consultas simultaneas" no lugar do processo, e a lib reportava isso como "processo nao encontrado". Agora ha nova tentativa apos pausa e, se o bloqueio persistir, o erro e de indisponibilidade com mensagem clara.
- `search` ficou bem mais rapido: busca so uma pagina de movimentacoes (cerca de 11 s para 1 s no processo de demonstracao).
- Fontes em paralelo: `extract_process` consulta eSAJ, DataJud e DJEN ao mesmo tempo, com `prazo_total` (padrao 60 s). Uma fonte lenta vira erro isolado e as demais voltam.
- `desde` (AAAA-MM-DD): restringe movimentacoes e comunicacoes e interrompe a paginacao do eSAJ ao chegar em dados antigos.
- Leitura de pecas corrigida: a pasta digital so abre na sessao que consultou o processo, e a lib devolvia a tela "Sua sessao expirou" como se fosse o texto do documento ao ler a partir de um extrato salvo (JSON). Agora a sessao e preparada e a tela de erro vira `status: sessao_expirada`.
- Ritmo minimo de 1,1 s entre consultas de processo ao eSAJ (o eSAJ recusa intervalos menores por IP): um lote de 4 processos passou de cerca de 13 s para cerca de 6 s.

## Correcoes de dados

- `partes.todas` vinha vazio em processos que so trazem a tabela de partes principais; agora repete as principais.
- `dados_basicos` ganha `situacao` (ex.: Extinto) e `etiquetas` do cabecalho do processo no eSAJ.
- Fora do TJSP, o eSAJ aparece como `nao_aplicavel` em `source_status`, sem gerar erro.
- A saida de `ler_pecas` traz `pasta_digital` resumida (`status` e `paginas`), sem a URL com ticket.
- "Processo nao encontrado" do eSAJ passa a dizer que pode ser processo sigiloso, de outro sistema ou numero inexistente.
- `normalizar_oab` devolve `NUMERO/UF` (`140969/SP`; suplementar `12345A/RJ`); antes `OAB/SP 140.969` virava `/SP 140.969`.

## Novos recursos

- `desde` em `api.get_extrato`, `api.extract_process`, CLI (`extract`, `timeline`) e MCP.
- `timeline --recent-first --limit N` (e `gerar_timeline` no MCP) busca no eSAJ so as N movimentacoes mais recentes.
- CLI `--limite-movimentacoes` em `extract` e `timeline` (`0` busca todas).
- MCP: `consultar_esaj` e `extrair_processo` aceitam `compacto`, que remove dados repetidos.
- `search` (API, cliente e CLI) funciona fora do TJSP usando o DataJud, sem partes, foro e juiz (`fonte: datajud`).
- `NanoJudClient.search_processo` reaproveita o extrato ja buscado pelo mesmo cliente.
- CLI `djen --desde` (mesmo que `--data-inicio`).

## Mudanca de comportamento

No MCP, `consultar_esaj` e `extrair_processo` passam a devolver por padrao a versao compacta (`compacto=true`): `extrair_processo` mantem so a timeline unificada, sem repetir movimentacoes e comunicacoes em `data`, e `consultar_esaj` omite texto repetido e documentos por movimentacao (a lista de documentos continua em `documentos`). Use `compacto=false` para o formato anterior.

Quando o limite de movimentacoes e pedido de proposito, o aviso de corte continua deixando o status do envelope como `partial`.

## Validacao

Suite offline com 198 testes, ruff, mypy e cobertura minima de 90%. Medido ao vivo no processo de demonstracao: `search` de 11,6 s para 0,8 s, duas consultas seguidas funcionando e leitura do texto da sentenca a partir de um extrato salvo.
