# Changelog

## [Unreleased]

### Compatibilidade e confiabilidade

- O parser e-SAJ deixou de usar `ignore_errors` no mypy; os dados de capa, partes, movimentos, documentos e estados de autorização agora usam contratos tipados. A sessão HTTP e-SAJ declara o timeout padrão sem depender de atributo dinâmico não tipado.
- O login assistido e-SAJ só cria a sessão HTTP após o navegador retornar ao endpoint oficial e entregar cookies; falta do extra opcional, timeout ou falha de login não deixa uma sessão sem uso.
- O login assistido e-SAJ só cria a sessão HTTP após a autenticação no navegador retornar ao endpoint oficial e entregar cookies; falta de Playwright, timeout ou falha de login não deixa uma sessão sem uso.
- A normalização DJEN preserva `ativo=None` quando a API omite o campo; ausência de sinalização não é interpretada como comunicação ativa.
- Candidato 0.6.0 passa a requerer Python 3.11.5–3.14. Python 3.10 chegou ao fim de vida upstream em 01/10/2026; essa versão também resolvia Soup Sieve e ferramentas de desenvolvimento em versões vulneráveis sem correção compatível conhecida. Python 3.15 permanece explicitamente fora da faixa até ser validado.
- `write_sqlite` fecha a conexão depois da transação, em vez de apenas confirmar o commit e deixar o descritor aberto.
- PJe/TJMG fornece `dados_basicos.orgao_julgador` com o valor da capa; `dados_basicos.foro` permanece como alias compatível.

### Adicionado

- Consulta DJEN detalhada em API Python, `NanoJudClient` e MCP, com estado de completude, páginas e avisos; a API histórica de lista continua compatível. Extração agregada marca `partial` quando a paginação não termina.
- Exportação tabular determinística em Python (`exports.to_table`/`to_csv`), CLI (`tabela`/`csv`) e MCP (`gerar_tabela`), preservando campos de proveniência e neutralizando conteúdo que planilhas poderiam executar como fórmulas na representação CSV. A ferramenta MCP pode receber `source_status` de `gerar_timeline` para preencher o estado por fonte em cada linha sem sobrescrever valor explícito. Exemplo de agente gera resposta factual com referência de registro e escape de marcação fornecida pelo texto da fonte.

- Cliente MNI SOAP 2.2.2 com namespaces e operação `consultarProcesso` versionados ao lado do cliente 3.0, seleção por `NANOJUD_MNI_VERSION`, configuração de credenciais por instalação e suporte a documentos inline. O contrato usa schema oficial em fixtures offline; nenhuma instalação autenticada foi validada live.
- Fonte opt-in `mni` integrada ao envelope de extração Python, `NanoJudClient`, CLI, MCP e lotes, com configuração por objeto ou variáveis de ambiente, sessão SOAP isolada por consulta, timeline normalizada e erro tipado quando a instalação não está configurada. O cliente genérico não presume endpoint TJSP nem foi validado contra a instalação do tribunal.
- Normalização pública de respostas `consultarProcesso` MNI 3.0 com validação do CNJ retornado, proveniência por host, mapeamento de partes/movimentos/metadados documentais e estado parcial até confirmação operacional da completude. `MNI3Client.consultar_extrato` usa esse normalizador; conteúdo dos documentos continua em operação separada.
- Cliente configurável `MNI3Client` para operações SOAP 3.0 de consulta processual e conteúdo de documentos, com autenticação por token ou usuário/senha, validação TLS, limite de resposta e erros sanitizados.

- Piloto público e-SAJ/TJSP de segundo grau na API Python, CLI `esaj-2g` e MCP `consultar_esaj_tjsp_2g`. Preserva os recursos distintos encontrados para um CNJ, indexa os vínculos documentais exibidos em cada movimento e sinaliza coleta parcial por resultado.
- API `obter_pdf_esaj_tjsp_2g`, CLI `esaj-2g-pdf` e ferramenta MCP `obter_documento_esaj_tjsp_2g` entregam PDFs individuais após confirmação do vínculo e verificação oficial de acesso. A busca pelo vínculo termina assim que encontra o documento solicitado.
- Fonte opt-in `esaj_tjsp_2g` na extração individual e em lote, com CNJ próprio, grau e procedência por recurso na linha do tempo.
- Opção `esaj_tjsp_2g` no fluxo de autos em lote, com gravação de peças vinculadas ou leitura em memória, manifesto por recurso e verificação individual de acesso.

- Consultas processuais em lote na API Python (`iter_extract_processes`, `extract_processes`), CLI (`batch`) e MCP (`extrair_processos`), com saída incremental, ordem estável, falhas isoladas por CNJ e circuit breaker por fonte.
- Fluxo em lote de autos e peças públicas do eSAJ/TJSP (`iter_extract_dockets`, CLI `autos` e MCP `consultar_autos_em_lote`), com diretório separado por processo, leitura de texto em memória e status explícitos para restrições, resultados parciais e fontes ainda não suportadas.
- Download de PDF em streaming para arquivo temporário, validação de assinatura, limite de tamanho e publicação atômica; arquivos existentes só são reutilizados quando são arquivos regulares com cabeçalho PDF e tamanho dentro do limite.
- Acesso eSAJ/TJSP por sessão autenticada, login oficial assistido em navegador, senha processual digitada sem eco ou provedor seguro no MCP; peças restritas são reavaliadas após resposta do portal.
- Ferramenta MCP `autenticar_esaj` para iniciar o login oficial sob demanda no navegador local e habilitar consultas e autos e-SAJ pela sessão em memória, sem transportar credenciais pelo MCP.
- Estado MCP `esaj_session_authentication` para distinguir configuração ausente, sessão fornecida pelo host ainda não verificada e login oficial confirmado.
- Entrega MCP de PDF público do PJe/TJMG como recurso binário, sem depender do caminho local do servidor, com limite de 8 MiB aplicado durante o download.
- API Python `obter_pdf_pje_tjmg` para obter bytes de PDF público com limite configurável e sessão reutilizável.
- Entrega MCP de peça e-SAJ/TJSP por `cd_documento`, na sessão configurada e como recurso binário de até 8 MiB; API e `NanoJudClient` retornam bytes com validação de acesso e limpeza do arquivo temporário.
- Ferramenta MCP `limpar_documentos_temporarios`, para remover pastas NanoJud antigas com limite de idade e sem aceitar caminhos arbitrários; diretórios recentes e arquivos de outros aplicativos são preservados.
- DataJud agora aplica `prazo_total` (60 s por padrão) em retries, `Retry-After` e paginação, com parâmetro nos adaptadores, API, cliente e MCP; a extração compartilha o orçamento restante do envelope com o DataJud e o cache do cliente não persiste respostas parciais.

### Corrigido

- DJEN agora preserva comunicações já coletadas como `partial` quando uma página posterior falha, o JSON fica inválido ou o orçamento total de 120 segundos termina; cada requisição e espera respeita o tempo restante. A API histórica continua retornando lista, enquanto a variante detalhada mantém completude explícita.
- DJEN agora confere o CNJ explícito de cada comunicação antes de incluí-la; itens sem identidade confirmável ou de outro processo são omitidos e mantêm a resposta parcial. A CLI `djen` agora usa a variante detalhada, mostra avisos e retorna código 1 para resultado parcial sem descartar registros válidos.
- O DJEN respeita `Retry-After` numérico ou em data HTTP nas respostas 429, com limite de espera de 60 segundos por tentativa.
- O cache do `NanoJudClient` não persiste listas DJEN cuja paginação terminou de forma parcial.

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- DataJud agora compara o total reportado com os registros entregues, sinaliza `partial` quando o total está ausente, é apenas um limite inferior ou excede o lote retornado, e reserva `nao_encontrado` a total zero confirmado. Extração agregada e resumo preservam a incompletude e o aviso.
- A consulta em lote pela API e CLI agora usa três tentativas DataJud por processo por padrão, igual à extração individual e ao cliente HTTP; antes o iterador Python e a CLI usavam uma tentativa e encerravam o item cedo em falhas transitórias como HTTP 429.
- O circuit breaker do lote agora zera a sequência de falhas após resposta `partial` com dados, pois resposta parcial utilizável não é falha transitória do provedor.
- A automação pública eproc aguarda resultados dinâmicos e captura alertas JavaScript do portal; alertas de captcha são classificados como `AcessoRestrito` e alertas de processo ausente preservam `ProcessoNaoEncontrado`.
- Consultas eproc 1G/2G aceitam `aguardar_desafio_interativo=True` em API, `NanoJudClient` e MCP: mantém Chromium visível até o operador concluir a verificação apresentada, depois continua aguardando o resultado. O padrão permanece passivo e limitado a 8 segundos; nenhum token é produzido ou injetado.

- O CPoSG reconhece a capa retornada diretamente na busca pelo CNJ próprio e confere o número antes de usar o código de processo informado pelo portal.

- DJEN e DataJud distinguem respostas fora do formato esperado de buscas sem resultados. O DJEN rejeita paginação e número de tentativas inválidos antes de acessar a rede.
- A extração agregada elimina fontes repetidas após a normalização e usa a mesma lista de fontes padrão na API, CLI, cliente e MCP.

- Extração direta, lotes, configuração do cliente e adaptadores DataJud/PJe rejeitam timeouts de rede ausentes, não positivos, não finitos ou acima do limite operacional de 24 horas; sessões eSAJ comuns recebem 30 s por padrão, e lotes validam o prazo total antes de consumir a entrada.
- A CLI expõe `--timeout` em `extrato`, `extract`, `baixar` e `ler-pecas`; `extract_process` na API Python propaga o limite por requisição a todas as fontes.
- O fluxo de autos (`api.iter_extract_dockets`, `NanoJudClient.iter_extract_dockets` e CLI `autos`) aceita timeout por requisição, propagado ao e-SAJ e PJe/TJMG; a CLI valida o valor antes de abrir a saída.
- O cache do cliente distingue extratos com e sem solicitação de arquivamento HTML, não reutiliza movimentações parciais como extrato completo em memória e ignora metadados JSON malformados.
- As chaves do cache do cliente usam serialização estruturada e validam o CNJ antes da busca; gravações são atômicas e TTL inválidos são rejeitados.
- O namespace do cache não aceita os segmentos de caminho `.` e `..`, impedindo que o namespace saia da raiz configurada.
- Ferramentas MCP de leitura/autos validam limites inteiros e booleanos antes de consultar fontes ou criar pastas; adaptadores eSAJ/PJe validam limites de documentos e texto também na API Python.
- A ferramenta MCP `ler_documentos_publicos` preserva status e aviso de paginação do e-SAJ, informa candidatos públicos e documentos restritos, e marca a resposta como parcial quando a leitura ou a listagem não cobre todos os candidatos conhecidos.
- Lotes de autos e-SAJ preservam o aviso específico de paginação incompleta retornado pelo provedor, em vez de substituí-lo por uma mensagem genérica.
- Lotes de autos e-SAJ/PJe consideram `texto_html_extraido` uma leitura bem-sucedida, assim como `texto_extraido`, sem classificar o processo como parcial apenas pelo formato da peça.
- Leitura de PDFs sem camada textual distingue digitalização de ausência do parser e dá orientação no resultado; lotes preservam a mensagem específica retornada pela leitura, inclusive erros de sessão.
- Erros de comunicação do e-SAJ, DataJud e DJEN não propagam mensagens brutas de `requests`, que poderiam expor URLs com identificadores ou tokens.
- O timeout configurado também alcança as consultas DJEN feitas pela extração agregada e pelo `NanoJudClient`; o adaptador valida e aplica o limite em cada requisição.
- Envelopes de extração e lotes também sanitizam exceções HTTP inesperadas antes de expor mensagens em resultados Python, CLI ou MCP.
- A API de autos em lote rejeita booleanos e frações nos limites inteiros, evitando que `False` seja interpretado como “baixar todas as peças”.
- O fluxo de senha processual e-SAJ não repete o POST para a mesma peça quando ela aparece em vários movimentos; sincroniza o estado das referências duplicadas e conta peças únicas liberadas.
- `NanoJudClient.obter_pdf_esaj` consulta novamente quando recebe uma senha processual explícita, inclusive quando o cliente já tem um extrato público completo.
- O lote PJe/TJMG identifica o arquivo pela peça. Reexecutar um lote com os documentos em outra ordem preserva a correspondência entre cada PDF e a peça no manifesto.
- `batch` e `autos` agora relatam erros de codificação UTF-8 sem traceback e mantêm JSONL válido quando a leitura falha após registros já emitidos.
- A limpeza MCP de autos temporários agora considera também a alteração mais recente dos itens internos; um PDF mais novo que a pasta não é removido antes do prazo.
- Os comandos `batch` e `autos` recusam usar o próprio arquivo de CNJs como manifesto, evitando truncar a lista antes de iniciar a consulta.
- O limitador HTTP do cliente agora respeita `rate_limit_interval` também após timeouts e erros de conexão; tentativas falhas não disparam a próxima requisição imediatamente.
- Limites `max_bytes` para download e entrega MCP agora rejeitam valores fracionários, texto, `None` e booleanos com `ValueError` previsível, antes de consultar os portais.
- O timeout de login e-SAJ exige inteiro positivo na API Python e inteiro entre 30 e 1800 segundos no MCP, rejeitando tipos inválidos antes de criar sessão ou iniciar navegador.
- e-SAJ/TJSP e PJe/TJMG não marcam diretórios, links simbólicos, arquivos truncados ou conteúdo sem cabeçalho PDF como documentos já baixados; destinos inválidos são substituídos após novo download validado.
- A ferramenta MCP de limpeza rejeita frações e textos no limite `min_age_hours`, além de booleanos e valores fora do intervalo.
- `nanojud autos` valida caminhos antes do login e só abre o manifesto após a autenticação assistida; falha de login não trunca um resultado anterior.
- Extratos e resumos rápidos do e-SAJ preservam estado `partial` quando a paginação não confirma a lista completa de movimentações; a fonte no envelope agregado também reflete esse estado.
- A limpeza MCP de pastas temporárias exige um marcador de propriedade criado pela NanoJud além do prefixo, evitando apagar diretórios alheios com nome coincidente.
- A ferramenta MCP `extrair_processos` valida que `numeros` seja uma lista de strings antes de iniciar a consulta em lote e rejeita workers inválidos na fronteira da ferramenta.
- `NanoJudConfig.timeout` alcança também a preparação da sessão, metadados da pasta digital e leitura/download de PDFs e-SAJ; a API funcional expõe o timeout nas mesmas operações.
- Leitura e-SAJ/PJe em memória limita cada PDF a 8 MiB durante a transferência; respostas acima do limite são interrompidas antes de materializar o conteúdo completo.
- O MCP preserva configuração operacional e `senha_processo_provider` fornecidos pelo host quando ativa uma sessão e-SAJ autenticada no navegador.
- As ferramentas MCP DataJud/DJEN delegam ao `NanoJudClient` fornecido pelo host, respeitando sua sessão, cache, chave e limites; o timeout configurado no cliente agora também é aplicado às requisições DJEN.
- O login assistido e-SAJ só considera concluído o retorno ao endpoint HTTPS exato `open.do` da origem oficial; caminhos adjacentes ou fragmentos não encerram o fluxo.
- A navegação inicial do login assistido respeita `timeout_login`, evitando o timeout padrão de 30 segundos do Playwright antes da espera explícita pelo retorno.
- `nanojud extract` retorna código de saída não zero para envelopes `partial` e `error`, mantendo a saída JSON para diagnóstico e automação.
- A mensagem de andamento de `nanojud extract` agora identifica as fontes selecionadas pelo usuário.
- O `nanojud batch` voltou a usar o perfil estável e opt-in de provedores; PJe/TJMG só é consultado quando selecionado com `--source pje_tjmg`.
- Requisições simultâneas pela mesma sessão agora são serializadas por host, mantendo o intervalo configurado sem bloquear fontes independentes.
- A autenticação assistida agora explica como instalar o Chromium ausente sem expor caminhos locais do navegador nos erros.
- Logs HTTP e hits de cache deixaram de registrar URLs completas e números CNJ.
- Paginação pública PJe/TJMG agora aceita respostas HTML completas e atualizações JSF parciais, confirma a página solicitada, percorre movimentos e documentos até 100 páginas por tabela e mantém resultados parciais quando uma página falha. Validado por teste offline e consulta live pública.

## [0.5.3] - 2026-10-15

### Seguranca

- Pisos de dependencia sem vulnerabilidades conhecidas (auditoria com `pip-audit`): `requests>=2.33.0`, `pypdf>=6.19.0,<7` e `mcp>=1.30.0,<2`. Os pisos anteriores (`requests>=2.28`, `pypdf>=5`, `mcp>=1.0`) permitiam versoes com dezenas de avisos de seguranca; instalacoes novas ja pegavam as versoes recentes, mas ambientes com versoes fixadas antigas nao.

### Corrigido

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- `mcp>=1.0` estava errado: o servidor usa `FastMCP`, que so existe a partir do mcp 1.2. O novo piso resolve isso.
- Links relativos do README (`docs/...`, `SECURITY.md` etc.) quebravam na pagina do projeto no PyPI; agora apontam para o site da documentacao e para o GitHub.

### Adicionado

- CLI em portugues: ajuda, mensagens de uso e de erro em portugues; apelidos `consultar` (search), `linha-do-tempo` (timeline) e `extrair` (extract); opcoes `--fonte`, `--limite`, `--recentes-primeiro`, `--max-caracteres`, `--ajuda` e `--versao`. Os nomes em ingles continuam valendo.
- Saida em texto legivel no terminal (`--formato auto|texto|json` em `consultar`, `partes`, `linha-do-tempo` e `djen`), com datas em dia/mes/ano. Ao redirecionar a saida ou usar `--out`, continua JSON.
- `--out` tambem em `consultar` e `partes`.
- Avisos de andamento no terminal durante consultas demoradas (no stderr, so quando ha terminal).
- Erros com "O que fazer": texto no terminal e campo `dica` no JSON; mensagens claras para arquivo de extrato ausente ou invalido; Ctrl+C encerra com mensagem.
- `python -m nanojud` e `situacao` no resumo do `search`.
- Novo `docs/guia-do-advogado.md`, com instalacao do Python no Windows, tarefas do dia a dia, como ler o resultado, solucao de problemas e glossario; README, quickstart, guia da CLI e pagina para advogados reorganizados para comecar pelo terminal.
- MCP: `consultar_datajud` aceita `compacto` (padrao `true`), que omite o `payload_origem` repetido de cada movimento; processos grandes passavam de 150 KB.

### Alterado

- A linha do tempo `--recentes-primeiro --limite N` nao avisa mais do corte de movimentacoes que a propria CLI escolhe.
- Os workflows `Publish PyPI` e `Publish TestPyPI` so rodam a partir de uma tag `vX.Y.Z` igual a versao em `version.py`; antes construiam o pacote de qualquer ref.

## [0.5.2] - 2026-10-15

### Corrigido

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- Leitura de pecas (`ler_pecas`, `baixar_pecas`, CLI `ler-pecas`/`baixar` e MCP `ler_documentos_publicos`): a pasta digital so abre na sessao que consultou o processo e carregou a pagina de movimentacoes do documento. Antes, ao ler a partir de um extrato salvo (JSON), o eSAJ devolvia a tela "Sua sessao expirou" e a lib a reportava como texto do documento. Agora a sessao e preparada (processo reaberto, paginas de movimentacoes ate o documento, metadados refeitos), e a tela de sessao expirada vira `status: sessao_expirada`, nunca texto.
- A saida de `ler_pecas` traz `pasta_digital` resumida (`status` e `paginas`), sem a URL com ticket.
- "Processo nao encontrado" do eSAJ passa a dizer que pode ser processo sigiloso, de outro sistema ou numero inexistente.
- `normalizar_oab` devolve a forma canonica `NUMERO/UF` (`140969/SP`, suplementar `12345A/RJ`); antes `OAB/SP 140.969` virava `/SP 140.969`.
- eSAJ: consultas em sequencia muito rapida recebiam o aviso de "multiplas consultas simultaneas" no lugar do processo e eram reportadas como processo nao encontrado. Agora a pagina e tentada de novo apos uma pausa e, se o bloqueio persistir, o erro e de indisponibilidade com mensagem clara.
- `partes.todas` vinha vazio em processos que so trazem a tabela de partes principais; passa a repetir as principais.
- eSAJ: `dados_basicos` ganha `situacao` (ex.: Extinto) e `etiquetas` do cabecalho do processo.
- `search` busca so uma pagina de movimentacoes (de ~11 s para ~1 s no processo de demonstracao).

### Adicionado

- Ritmo minimo de 1,1 s entre consultas de processo ao eSAJ, valendo para todo o processo Python (o eSAJ recusa intervalos menores por IP). Um lote de 4 processos passou de ~13 s para ~6 s, sem consultas perdidas.
- `search` (API, cliente e CLI) funciona fora do TJSP usando o DataJud (sem partes, foro e juiz; `fonte: datajud`).
- `NanoJudClient.search_processo` reaproveita o extrato ja buscado pelo mesmo cliente, sem repetir a consulta ao eSAJ.
- CLI `djen --desde` (mesmo que `--data-inicio`).
- `desde` (YYYY-MM-DD) em `api.get_extrato`, `api.extract_process`, CLI (`extract`, `timeline`) e MCP: restringe movimentacoes e comunicacoes e interrompe a paginacao do eSAJ ao chegar em dados mais antigos.
- `timeline --recent-first --limit N` (e `gerar_timeline` no MCP) busca no eSAJ so as N movimentacoes mais recentes.
- `extract_process` consulta as fontes em paralelo e aceita `prazo_total` (padrao 60 s): uma fonte lenta vira erro isolado e as demais voltam. O eSAJ fora do TJSP e marcado `nao_aplicavel` em vez de erro.
- CLI `--limite-movimentacoes` em `extract` e `timeline`.
- MCP: `consultar_esaj` e `extrair_processo` aceitam `compacto` (padrao `true`), que remove dados repetidos (movimentacoes duplicadas entre `data` e `timeline`, texto repetido); `compacto=false` devolve tudo.

## [0.5.1] - 2026-10-15

### Seguranca

- eSAJ: o `href` de documentos lido de um extrato JSON externo (`baixar`, `ler-pecas`, inspecao de pecas) agora precisa ser `https://esaj.tjsp.jus.br/cpopg/` ou `/pastadigital/`; antes qualquer URL era requisitada.
- `SECURITY.md` passa a apontar para o relato privado de vulnerabilidades do GitHub.

### Corrigido

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- `partes` classifica corretamente os polos com as abreviaturas do eSAJ (`Imptte`, `Imptdo`, `Apelte`, `Agvte` etc.); antes `polo_ativo` e `polo_passivo` vinham vazios.
- `relacionados.incidentes` nao traz mais a linha de espacamento vazia da tabela do eSAJ.
- CLI: `datajud`, `djen`, `extract`, `timeline`, `extrato` e `ler-pecas` passam a imprimir o JSON na tela quando `--out` nao e informado (antes gravavam arquivo no diretorio atual); a saida em UTF-8 evita erro de acentos em consoles Windows.
- DataJud: consulta todos os graus do numero CNJ (antes `size: 1` pegava um registro arbitrario). O grau mais baixo define os dados principais, `graus` resume cada registro e cada movimento ganha `grau`.
- DJEN: preserva `numero_processo`, `incidente` (ex.: `/47`), status/cancelamento, `hash`, `numero_comunicacao` e advogados destinatarios.
- Timeline: ids unicos para movimentos repetidos na mesma data; eventos DataJud trazem `grau` e os do DJEN passam a ter `numero_cnj`.
- Corrige a extracao de movimentacoes do eSAJ/TJSP, que passou a carregar a lista sob demanda por `carregarMovimentacoesAjax.do` e vinha vazia (afetava `search`, `extrato` e a timeline).
- Pagina por cursor com limite configuravel (`limite_movimentacoes`, `--limite-movimentacoes`; 0 busca todas) e pausa entre paginas; o extrato sinaliza `movimentacoes_completas` e `aviso_movimentacoes` quando ha corte ou falha parcial.

### Adicionado

- Envelope de `extract_process` ganha `divergencias`: compara classe, data de distribuicao/ajuizamento e ultima movimentacao entre eSAJ e DataJud, e informa quando ha mais de um grau no DataJud ou comunicacoes de incidentes no DJEN.
- `normalizar_data` aceita o formato compacto do DataJud (`20120910171334`).
- Workflow semanal `Live smoke` e testes live de DataJud e DJEN, para detectar mudancas nas fontes reais.
- Documentacao de `divergencias`, `graus`, `--limite-movimentacoes` e da saida da CLI sem `--out`.
- Adiciona guia dedicado de distribuicao PyPI e MCP.
- Adiciona workflow manual de publicacao no TestPyPI com Trusted Publishing.
- Documenta instalacao de usuario via `python -m pip install "nanojud[mcp]"`.
- Documenta execucao direta do MCP via `uvx --from "nanojud[mcp]" nanojud-mcp`.

### Alterado

- Ajusta metadados do pacote para README Markdown explicito no PyPI.
- Atualiza o README para usar logo com URL absoluta compativel com PyPI.

## [0.5.0] - 2026-07-31

### Adicionado

- Adiciona servidor MCP local por `stdio` em `nanojud.mcp_server`.
- Adiciona entrypoint `nanojud-mcp` para clientes MCP locais.
- Adiciona extra opcional `mcp` com dependência `mcp>=1.0,<2`.
- Expõe ferramentas MCP somente leitura para validação CNJ, extração de CNJ em texto, consultas eSAJ/DataJud/DJEN, envelope agregado e timeline.
- Adiciona documentação de instalação e configuração local do MCP.

## [0.4.0] - 2026-07-31

### Adicionado

- Adiciona cliente DataJud/CNJ como fonte separada do DJEN, com API key, retry, backoff, normalização e raw opcional.
- Adiciona envelope versionado de extração por fonte em `nanojud.extraction`.
- Adiciona timeline cronológica em `nanojud.timeline`, sem fase, relevância, risco ou interpretação jurídica.
- Adiciona exportadores JSON, JSONL, CSV e SQLite em `nanojud.exports`.
- Adiciona módulos `sources`, `schemas` e `normalization` para contratos e normalização técnica.
- Adiciona comandos CLI `datajud`, `extract` e `timeline`.
- Adiciona documentação de fontes e extração agregada.

### Alterado

- Corrige posicionamento público para separar eSAJ/TJSP, DataJud/CNJ e DJEN.
- Atualiza README, arquitetura, contratos, CLI e API Reference para remover ambiguidade entre DataJud e DJEN.

## [0.3.8] - 2026-07-31

### Corrigido

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- Refaz a página inicial da documentação para evitar quebra incorreta do título em layouts do MkDocs Material.
- Remove dependência de largura em caracteres no hero e adiciona breakpoints responsivos mais previsíveis.
- Oculta navegação lateral e índice na home para apresentar a landing com largura adequada.

### Alterado

- Reposiciona a landing com narrativa mais premium, moderna e voltada a infraestrutura jurídica para agentes e automações.
- Atualiza o visual do pipeline, métricas, cards de público-alvo, seções de engenharia verificável e CTA final.

Todas as mudanças relevantes deste projeto serão documentadas aqui.

O formato segue a ideia de manter versões legíveis para usuários jurídicos e desenvolvedores.

## [0.3.7] - 2026-07-31

### Alterado

- Redesenha a página inicial da documentação com hero moderno, visual de pipeline agentico, métricas de confiança e CTA.
- Adiciona CSS dedicado para a landing pública do MkDocs.
- Inclui assets `.css` e `.svg` da documentação no `sdist`.

## [0.3.6] - 2026-07-31

### Alterado

- Reposiciona o README como toolkit Python para consulta responsável, estruturação e auditoria de dados públicos judiciais.
- Adiciona logo, badges de CI/Docs/CodeQL/release e links rápidos no topo do README.
- Reforça seções de confiança, casos reais de robustez e aviso de projeto independente.
- Atualiza a página inicial da documentação com narrativa de confiança, público-alvo e casos suportados.
- Configura logo, favicon e paleta do site MkDocs.
- Melhora metadados do pacote com descrição e keywords mais alinhadas a legaltech/lawtech.

## [0.3.5] - 2026-07-31

### Corrigido

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- Evita falso positivo de `AcessoRestrito` quando uma página pública do eSAJ contém o popup oculto `popupSenha`.

### Adicionado

- Teste automatizado para página pública com popup oculto de senha.
- Teste `live` opcional para validação controlada contra o eSAJ/TJSP real.
- Guia de validação real com corpus privado, sanitização e cenários obrigatórios.
- Release notes versionadas para `v0.3.5`.

### Alterado

- Workflow de release passa a usar arquivo de notas versionadas como corpo do GitHub Release.

## [0.3.4] - 2026-07-31

### Alterado

- GitHub Pages habilitado em `https://lucmolero.github.io/nanojud/`.
- Metadados do pacote atualizados para apontar homepage e documentação para o site público.

## [0.3.3] - 2026-07-31

### Alterado

- Repositório tornado público no GitHub.
- Workflow de documentação volta a publicar GitHub Pages quando permitido.
- CodeQL volta a enviar resultados para Code Scanning em repositório público.
- Roadmap limpo para refletir o estado público atual.

## [0.3.2] - 2026-07-31

### Adicionado

- Templates profissionais para issues e pull requests.
- Workflow manual de publicação PyPI com Trusted Publishing.
- Release notes versionadas em `docs/release-notes-v0.3.1.md`.

### Alterado

- `SPECS.md` passa a refletir a arquitetura real do projeto.
- GitHub Actions atualizados para versões mais recentes apontadas pelo Dependabot.
- Cobertura ampliada para 91% com novos testes de API, cliente, cache, DJEN e eSAJ.
- Gate mínimo de cobertura elevado para 90%.

## [0.3.1] - 2026-07-31

### Corrigido

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- Ajusta CI para atualizar `setuptools>=83.0.0` antes da auditoria de dependências.
- Mantém workflow de documentação como build estrito enquanto GitHub Pages não estiver disponível no plano/configuração do repositório.
- Ajusta CodeQL para executar análise sem depender de upload para Code Scanning quando a feature não estiver habilitada.

## [0.3.0] - 2026-07-31

### Adicionado

- Cliente `NanoJudClient` para uso profissional com timeout, rate limit, cache opcional, logging e sessão injetável.
- Configuração pública `NanoJudConfig`.
- Cache JSON local e opt-in.
- Marcador `py.typed` e checagem `mypy` no CI.
- Workflow de release para tags `v*`, com build, validação de metadados e artefatos anexados ao GitHub Release.
- Site MkDocs Material com navegação estruturada.
- Documentos de metodologia, reprodutibilidade, LGPD, modelo de ameaças e governança.
- Arquivo `CITATION.cff` para citação acadêmica e institucional.
- Exemplo `examples/client_configurado.py`.

### Alterado

- Validação CNJ agora permite configurar escopo de segmento e tribunal, usada pelo DJEN sem restringir ao TJSP.
- `User-Agent` passa a incluir a versão do pacote.
- Roadmap reorganizado para separar entregas 0.2, 0.3 e próximas prioridades.

## [0.2.0] - 2026-07-31

### Adicionado

- Exceções públicas para erros previstos: CNJ inválido, URL inválida, acesso restrito, consulta indisponível, processo não encontrado e download indisponível.
- Contratos tipados em `nanojud.models` com `TypedDict`.
- Validação de CNJ com normalização e conferência de dígito verificador.
- Parser eSAJ ampliado para dados básicos, partes, movimentações, documentos vinculados, metadados de publicação, audiências, petições, incidentes e apensos.
- Cliente DJEN com sessão injetável, retry configurável, backoff e testes sem rede.
- CLI com comando `baixar`, flags `--inspecionar-pecas`, `--salvar-html` e erros em JSON.
- Documentação de arquitetura, contratos e erros.

### Alterado

- `resumo_rapido` passa a consultar o extrato uma única vez.
- `baixar_pecas` passa a usar o fluxo real de documentos públicos candidatos quando disponível.

## [0.1.1] - 2026-07-31

### Corrigido

- O PJe/TJMG confirma a listagem documental sem slider somente quando o total explícito do portal coincide com as linhas exibidas; divergências e contagens ausentes continuam parciais.


- Corrige metadados PEP 621 do `pyproject.toml`, removendo `url` de `project.authors`.
- Atualiza declaração de licença para SPDX (`MIT`) e inclui `license-files`.
- Adiciona dependências dev necessárias para validação local de lint e build.
- Formata o código com Ruff e corrige problemas de lint.

### Adicionado

- CI passa a executar testes, lint e build do pacote.
- Testes de parsing com fixture HTML sanitizada.
- Documentação e arquivos de governança para GitHub.

## [0.1.0] - 2026-07-31

### Adicionado

- Estrutura inicial do pacote `nanojud`.
- API pública com funções para resumo, extrato, partes e DJEN.
- CLI `nanojud` com comandos iniciais.
- Especificação de produto em `SPECS.md`.
- Documentação inicial de uso, contribuição, segurança e roadmap.

### Conhecido

- Download de peças ainda não está implementado de ponta a ponta.
- Parser do eSAJ ainda precisa de fixtures reais sanitizadas e cobertura maior.
- Tratamento de erros será refinado nas próximas versões.
