# Changelog

## [Unreleased]

### Corrigido

- Leitura de pecas (`ler_pecas`, `baixar_pecas`, CLI `ler-pecas`/`baixar` e MCP `ler_documentos_publicos`): a pasta digital so abre na sessao que consultou o processo e carregou a pagina de movimentacoes do documento. Antes, ao ler a partir de um extrato salvo (JSON), o eSAJ devolvia a tela "Sua sessao expirou" e a lib a reportava como texto do documento. Agora a sessao e preparada (processo reaberto, paginas de movimentacoes ate o documento, metadados refeitos), e a tela de sessao expirada vira `status: sessao_expirada`, nunca texto.
- A saida de `ler_pecas` traz `pasta_digital` resumida (`status` e `paginas`), sem a URL com ticket.
- "Processo nao encontrado" do eSAJ passa a dizer que pode ser processo sigiloso, de outro sistema ou numero inexistente.
- `normalizar_oab` devolve a forma canonica `NUMERO/UF` (`140969/SP`, suplementar `12345A/RJ`); antes `OAB/SP 140.969` virava `/SP 140.969`.

### Adicionado

- Ritmo minimo de 1,1 s entre consultas de processo ao eSAJ, valendo para todo o processo Python (o eSAJ recusa intervalos menores por IP). Um lote de 4 processos passou de ~13 s para ~6 s, sem consultas perdidas.
- `search` (API, cliente e CLI) funciona fora do TJSP usando o DataJud (sem partes, foro e juiz; `fonte: datajud`).
- `NanoJudClient.search_processo` reaproveita o extrato ja buscado pelo mesmo cliente, sem repetir a consulta ao eSAJ.
- CLI `djen --desde` (mesmo que `--data-inicio`).

### Corrigido

- eSAJ: consultas em sequencia muito rapida recebiam o aviso de "multiplas consultas simultaneas" no lugar do processo e eram reportadas como processo nao encontrado. Agora a pagina e tentada de novo apos uma pausa e, se o bloqueio persistir, o erro e de indisponibilidade com mensagem clara.
- `partes.todas` vinha vazio em processos que so trazem a tabela de partes principais; passa a repetir as principais.
- eSAJ: `dados_basicos` ganha `situacao` (ex.: Extinto) e `etiquetas` do cabecalho do processo.
- `search` busca so uma pagina de movimentacoes (de ~11 s para ~1 s no processo de demonstracao).

### Adicionado

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
