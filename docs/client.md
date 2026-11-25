# Cliente Configurável

O `NanoJudClient` é a interface recomendada para automações profissionais, serviços internos, jobs agendados e notebooks que precisam de controle operacional. Ele aceita uma sessão autenticada pelo fluxo oficial do tribunal e um callback seguro que fornece a senha processual quando a fonte a exigir.

## Exemplo

```python
from nanojud import NanoJudClient, NanoJudConfig

config = NanoJudConfig(
    timeout=20,
    rate_limit_interval=1.0,
    cache_enabled=True,
    cache_dir=".nanojud_cache",
    cache_ttl_seconds=6 * 60 * 60,
)

client = NanoJudClient(config)
resumo = client.search_processo("0015020-23.2010.8.26.0053")
print(resumo["classe"])
print(resumo["fonte"], resumo["grau"], resumo["data_coleta"])
print(resumo["status"], resumo["coleta_completa"])
```

## Extração em lote de autos

`client.iter_extract_dockets(numeros, destination=..., ...)` consulta e baixa documentos públicos sequencialmente no eSAJ/TJSP ou PJe/TJMG, mantendo a sessão do cliente entre consulta e download. O timeout padrão vem de `NanoJudConfig`; o argumento `timeout` do lote pode substituí-lo naquela execução. O modo `read_documents=True` tenta extrair texto em memória. No PJe/TJMG, percorre até 100 páginas por tabela e mantém estado parcial enquanto houver páginas pendentes, falhas ou limite excedido. `downloaded` contém apenas arquivos obtidos ou já existentes; `document_statuses` mantém o resultado individual de cada peça, inclusive falhas.

Para consumir um PDF PJe/TJMG em memória como bytes, use `client.obter_pdf_pje_tjmg(url, max_bytes=...)`. O limite padrão é 8 MiB e o máximo permitido pela API Python é 128 MiB; use o método de download em arquivo para documentos maiores.

Para obter uma peça pública do e-SAJ, use `client.obter_pdf_esaj(numero, cd_documento, max_bytes=...)`. A biblioteca confirma o identificador entre as peças acessíveis no extrato, reaproveita o extrato completo do cliente quando disponível e prepara a pasta digital na mesma sessão. O arquivo temporário é removido antes da devolução dos bytes. O limite padrão é 8 MiB. Se o portal exigir autorização, o cliente pode receber uma sessão autorizada ou uma senha processual válida. Passar `senha_processo` ao método inicia nova consulta pelo formulário oficial, mesmo após uma consulta pública completa.

## Quando usar

Use o cliente configurável quando precisar de:

- timeout consistente em todas as chamadas;
- intervalo mínimo entre requisições;
- cache local para evitar consultas repetidas;
- `User-Agent` identificável;
- logging para auditoria técnica;
- uma sessão `requests` injetável em testes.
- uma sessão HTTP autenticada, mantida apenas em memória;
- `senha_processo_provider`, que recebe o número e a lista de documentos restritos e devolve a senha obtida pelo host em um cofre ou diálogo local. O segredo não entra nos logs, no cache ou no resultado.

O `timeout` configurado acompanha também a preparação da sessão e as requisições da pasta digital, leitura e streaming dos PDFs e-SAJ.

## DataJud

`client.consultar_djen_detalhado(numero, data_inicio="")` informa `status`, `completo`, `paginas`, `avisos` e `comunicacoes`. Falhas tardias e o orçamento de tempo padrão de 120 segundos retornam `partial` quando já há comunicações coletadas. Esse orçamento limita esperas e o timeout passado a cada requisição, mas não é um prazo rígido garantido pela biblioteca de rede. O método histórico `client.consultar_djen` conserva o retorno em lista e o cache opt-in, mas só grava uma lista no cache quando a paginação terminou; use a variante detalhada quando a conclusão da consulta for importante.

`client.consultar_datajud(numero, prazo_total=60.0)` compartilha esse orçamento entre retries e páginas da consulta DataJud. Use `None` para desativar o teto total quando a rotina puder aguardar indefinidamente. O `timeout` de `NanoJudConfig` continua limitando cada operação de rede; o prazo total impede iniciar novos retries ou páginas depois que o orçamento expira. Resultados DataJud `partial` não entram no cache, para uma chamada futura poder concluir uma coleta mais completa.

`client.consultar_pje_tjmg(numero, prazo_total=60.0)` aplica um prazo cooperativo à busca, ao detalhe e à paginação pública. O timeout de `NanoJudConfig` continua limitando cada requisição. Se o prazo total vencer no meio da consulta, as páginas já coletadas são preservadas e o retorno fica `partial`; `None` desativa o teto total.

Para consultar o detalhe legado TJMG 2G cujo ID interno já foi obtido, use `client.consultar_tjmg_2g_legado(numero_cnj, identificador_tjmg)`. São exigidos o CNJ e o identificador `listaProcessos` de 17 dígitos. O método valida o sequencial TJMG em cada página auxiliar e pode retornar capa básica, partes/advogados e vínculos públicos de documentos além dos movimentos. Não faz a busca massiva por CNJ; o retorno permanece `partial` e não confirma completude do histórico nem do índice de documentos. Para obter uma peça listada, use `client.obter_documento_tjmg_2g_legado(numero_cnj, identificador_tjmg, cd_documento, ano_criacao_doc)`. O método confirma novamente identidade e vínculo, retorna bytes e MIME em memória, aceita PDF/DOC/DOCX até 8 MiB e não grava o arquivo.

## Tabelas

`nanojud.exports.to_table(registros, columns=...)` transforma movimentos, comunicações ou uma timeline em linhas estruturadas e CSV, sem depender de um modelo de linguagem. Passe `numero_cnj`, `fonte`, `grau` e `status_fonte` junto dos registros quando a origem estiver disponível; o exportador preserva essas colunas. O CSV neutraliza conteúdo que planilhas poderiam interpretar como fórmulas, sem modificar os registros Python. Para CLI use `nanojud tabela extracao.json --out tabela.csv`; para MCP, envie os registros a `gerar_tabela`.

## Cache

O cache é opt-in e gravado em JSON por namespace. Ele não deve ser usado para armazenar dados sensíveis sem política interna de retenção, acesso e descarte.

Recomendação prática:

- deixe o cache desligado em scripts exploratórios;
- ligue cache em rotinas repetidas com TTL curto;
- nunca versione a pasta de cache;
- trate o cache como dado jurídico operacional.

## Rate limit

`rate_limit_interval` define a espera mínima entre requisições ao mesmo host pela mesma sessão. Chamadas simultâneas ao mesmo host são serializadas; hosts diferentes continuam independentes. Ele não substitui leitura de termos de uso, políticas do tribunal, limitação de volume ou avaliação jurídica. É uma proteção técnica básica para reduzir pressão sobre fontes públicas.

`cache_ttl_seconds` deve ser um inteiro não negativo; zero significa que as entradas não expiram. Use um TTL curto para dados processuais que precisam refletir movimentações recentes.

Os logs de depuração registram método, host e status HTTP; não incluem caminho, parâmetros da URL nem número CNJ em hits de cache.
