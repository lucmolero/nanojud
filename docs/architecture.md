# Arquitetura

`nanojud` é organizado em camadas pequenas para separar experiência pública, parsing, clientes HTTP e utilidades de domínio jurídico.

## Camadas

- `nanojud.api`: fachada pública para scripts, notebooks, CLIs e integrações.
- `nanojud.client`: cliente configurável para automações profissionais.
- `nanojud.config`: configuração imutável de timeout, cache, rate limit e User-Agent.
- `nanojud.cache`: cache JSON local e opcional.
- `nanojud.esaj`: cliente e parser do eSAJ/TJSP.
- `nanojud.datajud`: cliente da API pública DataJud/CNJ para dados processuais.
- `nanojud.djen`: cliente do DJEN para comunicações e publicações.
- `nanojud.mni` e `nanojud.mni_222`: clientes SOAP MNI 3.0 e 2.2.2 versionados, configuráveis por instalação. A compatibilidade offline de contrato não comprova credenciais ou operação live.
- `nanojud.mni_normalizacao`: normalizador de respostas MNI para o envelope NanoJud.
- `nanojud.extraction`: envelope versionado de extração por fonte.
- `nanojud.timeline`: timeline cronológica sem interpretação jurídica.
- `nanojud.exports`: exportadores JSON, JSONL, CSV e SQLite.
- `nanojud.mcp_server`: servidor MCP local opcional por `stdio`.
- `nanojud.models`: contratos tipados dos retornos.
- `nanojud.exceptions`: exceções públicas e previsíveis.
- `nanojud.utils`: normalização de texto, CNJ e classificação auxiliar.
- `nanojud.cli`: interface de linha de comando.

## Fontes nacionais e famílias de portais

DJEN e DataJud são fontes nacionais independentes. O DJEN fornece publicações. O DataJud fornece metadados e movimentos conforme a cobertura da API pública e dos aliases oficiais; a ausência de alias ou resultado não demonstra inexistência do processo. O roteamento DataJud usa ramo e tribunal do CNJ e não está limitado à fila estadual SP → RJ → MG. Veja a [taxonomia de fontes](roadmap.md#taxonomia-e-alcance-das-fontes).

e-SAJ e eproc são famílias de portais. Cada instalação tem escopo próprio de tribunal, instância, paginação e acesso a peças. O código inclui e-SAJ/TJSP no perfil padrão e eproc/TJSP 1G/2G e PJe/TJMG 1G sob seleção explícita. O eproc consulta a interface pública no navegador. Em 12/11/2026, o smoke real de 2G alcançou o formulário e a consulta respondeu com desafio Turnstile, classificado como `AcessoRestrito`; movimentos não foram obtidos nessa execução. O perfil padrão agrega e-SAJ quando aplicável, DataJud e DJEN. O plano de consulta em primeiro e segundo grau avança por TJSP, TJRJ e TJMG. O e-SAJ/TJSP possui adaptadores separados para CPoPG e CPoSG. Veja o [roadmap de provedores](roadmap.md#plano-de-desenvolvimento-atual).

MNI SOAP 3.0 e 2.2.2 estão disponíveis como fonte opt-in `mni` para API, `NanoJudClient`, CLI, MCP e lote. MNI não é uma base nacional única. `NANOJUD_MNI_VERSION` seleciona o contrato; se omitida, preserva o padrão legado 3.0. O contrato MNI permite solicitar dados e movimentos, listar IDs de documentos e consultar o conteúdo de documentos por identificador. A configuração representa uma instalação por chamada; ambientes com vários tribunais devem selecionar a instalação explicitamente e nunca reutilizar credenciais. Consulta real exige credencial provisionada para aquela instalação. O TJRJ documenta um estado adicional no MNI-DCP para processos ativos, baixados ou migrados para eproc; seu formato de requisição ainda não está modelado. Fixtures verificam serialização e normalização, mas nenhuma consulta autenticada foi comprovada nesta rodada. Veja a etapa MNI no [roadmap](roadmap.md#plano-de-desenvolvimento-atual).

## Princípios

- Testes não devem depender de rede.
- Fixtures devem ser sanitizadas.
- Erros previsíveis devem usar exceções próprias.
- A API pública deve preservar contratos estáveis.
- Funcionalidades sensíveis, como download de peças, devem respeitar restrições técnicas e jurídicas.

## Fluxo eSAJ

1. Valida e normaliza CNJ.
2. Monta URL pública de busca.
3. Abre sessão HTTP com cabeçalhos conservadores.
4. Segue lista de resultados quando necessário.
5. Detecta captcha, senha, restrição ou processo não encontrado.
6. Extrai dados básicos, partes, movimentações, documentos e tabelas complementares.
7. Retorna dicionário estruturado com `status`, `mensagem`, `origem` e dados do processo.

## Cliente configurável

O `NanoJudClient` encapsula a sessão HTTP e aplica configuração operacional sem mudar os contratos principais:

1. cria sessão com `User-Agent` versionado;
2. aplica timeout padrão;
3. respeita intervalo mínimo entre chamadas quando configurado;
4. consulta cache local quando habilitado;
5. delega parsing e download aos módulos especializados;
6. retorna os mesmos contratos documentados da API pública.

## Fluxo DJEN

1. Consulta endpoint público do DJEN por número CNJ.
2. Pagina resultados até `max_pages`.
3. Aplica retry/backoff para falhas transitórias e HTTP 429.
4. Deduplica comunicações por `id`.
5. Normaliza datas e campos de saída. Uma resposta fora do formato esperado gera `ConsultaIndisponivel`.

## Fluxo DataJud

1. Valida e normaliza o CNJ sem restringir a TJSP.
2. Infere o índice DataJud a partir do segmento e tribunal do CNJ.
3. Consulta a API pública DataJud/CNJ com `APIKey`.
4. Valida a estrutura da resposta e normaliza classe, grau, órgão julgador, assuntos, movimentos e partes quando presentes.
5. Retorna payload bruto opcional quando solicitado.
