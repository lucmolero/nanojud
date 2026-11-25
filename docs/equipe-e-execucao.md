# Equipe, decisões e execução — uso interno

Este documento descreve as **perspectivas profissionais** necessárias para construir e operar a NanoJud e o fluxo sequencial entre Luna (execução) e Sol (direção, auditoria e release). Os nomes dos papéis não representam pessoas contratadas, pareceres emitidos ou aprovações externas. A responsabilidade por uma decisão existe mesmo quando a mesma pessoa ou modelo aplica várias perspectivas.

## Documentos por momento de uso

**Toda continuação do Luna:** ler [`AGENTS.md`](../AGENTS.md), [operação do Goal](operacao-goal.md) e [estado operacional](../reports/estado-goal.md) integralmente; do [plano de produto](plano-produto-e-handoff.md), ler objetivo, bloqueadores e P-ID ativo. O plano contém a **única fila ativa**.

**Ao selecionar uma fatia:** ler a seção pertinente do [roadmap](roadmap.md), da [validação real](validacao-real.md) e do [catálogo de casos](../tests/live_cases.json); depois contratos, código e testes relacionados. [Arquitetura](architecture.md), [fontes](fontes.md), [MCP](mcp-local.md) e [ameaças](threat-model.md) entram conforme a fronteira alterada. Não carregar o relatório histórico inteiro por rotina.

**Na revisão Sol:** ler o pacote curto, plano e este documento, depois diff, evidências, código, testes e artefato. Um resumo da conversa não substitui essas verificações. A leitura seletiva reduz contexto irrelevante sem dispensar a prova do comportamento.

## Perspectivas profissionais e decisão controlada

| Perspectiva | Responsabilidade concreta | Prova ou decisão |
| --- | --- | --- |
| Direção de produto | Define público, promessa por capacidade, prioridade e escopo de release | Aceite de jornada e texto público comparados à matriz |
| Gestão de produto | Traduz tarefas reais em cenários e critérios mensuráveis | CNJ, andamento, publicação, peça, lote e tabela com resultado esperado |
| Liderança de entrega | Ordena dependências e remove filas concorrentes | P0–P5 atualizado e riscos residuais |
| Especialista jurídico processual | Confere significado de grau, capa, andamento, publicação, intimação, peça, autos e migração | Revisão semântica; nenhuma providência inferida apenas do último evento |
| Pesquisa de UX | Observa uso real, compreensão, tempo e erro | Roteiro e achados; inspeção heurística não é pesquisa com usuários |
| Design e conteúdo | Organiza página, guia, CLI, mensagens e fluxo de consulta | Tarefa concluível e estados claros em desktop, mobile e terminal |
| Acessibilidade | Confere teclado, foco, semântica, contraste e leitura de tabelas | Inspeção e correções; build do site não comprova conformidade |
| Arquitetura | Define fronteiras de fonte, normalização, API, CLI, MCP e compatibilidade | Contrato versionado e decisão de migração quando necessário |
| Engenharia Python | Implementa API, cliente, erros, cache, lote e pacote | Comportamento testado no wheel instalado |
| Integração de tribunais | Descobre e valida instalação, grau, identidade, paginação, sessão e peças | Amostra datada da própria fonte; matriz por capacidade |
| Engenharia de dados | Preserva origem, datas, duplicações, status e reconciliação documental | Schema e exportação sem perda de proveniência |
| Engenharia MCP e agentes | Define ferramentas, descrições, erros, limites, paginação e saída de documentos | Semântica equivalente à API; payload utilizável por agente |
| Avaliação de IA aplicada | Mede fundamentação, omissão e afirmações sem fonte quando houver síntese por modelo | Corpus e rubrica; consulta e exportação funcionam sem LLM |
| Qualidade | Cobre comportamento, falhas parciais, regressões e casos live | Teste antes/depois, matriz de risco e gates |
| Segurança | Confere segredo, sessão, TLS, downloads, logs e dependências | Fronteiras sensíveis verificadas e risco residual |
| Privacidade | Define minimização, retenção e descarte de dados e PDFs | Relatórios sem dados desnecessários e política operacional |
| Desempenho e confiabilidade | Mede latência, chamadas, tamanho, erros e recuperação por fonte | Orçamento e diagnóstico sem afirmar disponibilidade não medida |
| Plataforma e release | Mantém CI, build, publicação, compatibilidade e reversão | Mesmo artefato aprovado, instalado, testado e publicado |
| Documentação e suporte | Mantém guias, exemplos, cobertura, erros e triagem de relatos | Comandos reproduzidos e explicação de limites conhecidos |

Cada perspectiva age em uma **decisão concreta**. Não criar pareceres fictícios nem formulários por cargo. Em mudança pequena, o registro pode ter uma linha; em autenticação, documento, contrato público ou release, deve conter a prova específica de cada fronteira.

### Aplicação da equipe à fila atual

| Etapa | Perspectivas que decidem | Decisão concreta antes de avançar |
| --- | --- | --- |
| P0 — auditoria inicial | Produto, arquitetura, integração, QA, segurança e documentação | Qual alegação do candidato é confirmada, contradita ou desconhecida; qual falha tem prioridade P0 |
| P1 — correções | Engenharia Python, dados, MCP e QA; segurança em sessão ou arquivo | Qual contrato é preservado, qual regressão reproduz o defeito e se a correção não troca identidade, peça ou estado |
| P2 — jornada completa | Produto, jurídico, UX, Python, MCP, dados e desempenho | Se advogado e agente entendem o mesmo processo, fonte, limite e documento; se a tabela conserva proveniência |
| P3 — expansão | Integração, jurídico, dados, QA e segurança | Promover ou manter aberta cada linha de fonte × grau × capacidade com prova própria, incluindo acesso a peças |
| P4 — comunicação pública | Produto, design, acessibilidade, documentação e suporte | Quais tarefas são concluíveis, quais exemplos rodam e quais frases de cobertura devem ser retiradas ou qualificadas |
| P5 — release | Plataforma, release, QA, segurança, privacidade e produto | Se CI, pacote instalado, dependências, dados de exemplo e promessa correspondem ao mesmo artefato |

O executor aplica essas perspectivas como perguntas de revisão, não como assinaturas inventadas. Sol toma a decisão técnica de aceite ou devolução com evidência; a decisão de publicar usa o gate final do plano.

## Protocolo de execução em dois modelos

O fluxo é sequencial, sem subagentes. Luna implementa e entrega provas; Sol confronta a entrega com o objetivo, reproduz pontos críticos e decide o próximo incremento ou o release. É uma adaptação de comunicação de ciclo fechado: a instrução tem identificador e critério; o executor devolve exatamente o que entendeu e demonstrou; o revisor confere a parte crítica. [FAA](https://www.faa.gov/air_traffic/publications/atpubs/atc_html/chap2_section_4.html) descreve readback de dados críticos; [Anthropic](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) recomenda progresso persistente e teste ponta a ponta entre sessões; [OpenAI](https://developers.openai.com/api/docs/guides/agent-evals) descreve avaliação de fluxo por rastros e critérios. Essas fontes fundamentam o mecanismo, não uma promessa de ausência de erros. Nenhuma contagem fixa de palavras ou etapas garante qualidade.

### 1. Preparar a rodada (Luna)

- Confirmar diretório, branch, HEAD, `git status`, diff, versão/import path e arquivos locais ainda não comitados. Preservar tudo.
- Ler os documentos obrigatórios na ordem acima. Selecionar o primeiro item aberto P0–P5. Escrever em até cinco linhas: **ID, resultado observável, interfaces afetadas, prova planejada e risco principal**.
- Conferir casos positivos no catálogo pela identidade retornada pela própria fonte. Separar hipótese, contrato offline, observação live e capacidade aprovada. Se a alegação existente contrariar o código ou a fonte, registrar a contradição antes de expandir.

### 2. Executar um incremento (Luna)

1. Reproduzir o defeito ou estado inicial na interface afetada. Para mudança de comportamento, criar teste que falha quando houver cenário reproduzível.
2. Definir saída, erro, estado parcial, proveniência e compatibilidade antes da implementação. Em peça/documento, conferir vínculo entre índice, ID, arquivo e escopo.
3. Fazer a menor alteração que resolve a causa. Refatorar depois de provar equivalência. Preservar API pública ou documentar migração.
4. Rodar testes afetados e gates aplicáveis de `AGENTS.md`. Mudança pública exige wheel instalado e smoke MCP stdio. Mudança de fonte exige amostra live da instalação/grau se a capacidade for anunciada.
5. Registrar o resultado no pacote de handoff: comando, ambiente/data, amostra, saída resumida, arquivos e risco residual. Não registrar segredo, PDF integral ou dados pessoais desnecessários.

### 3. Conferir a transmissão (Luna → Sol)

O Luna entrega uma tabela com uma linha por afirmação importante:

| ID | Afirmação ou entrega | Evidência reproduzível | Estado | Risco residual |
| --- | --- | --- | --- | --- |
| Pn | Comportamento específico, fonte/grau/capacidade | Arquivo/linha, comando/resultado, amostra/data, hash do artefato | Confirmado / contradito / não verificado | Impacto e próximo teste |

Anexar diff desde o HEAD, versão e hash do wheel, lista de mudanças de contrato, resultados dos gates, matriz fonte × grau × capacidade e exemplos executados. **“Testes passaram” sem comando, ambiente e artefato é insuficiente.** Se a execução parar no meio, registrar primeiro estado e próximo passo no mesmo pacote; não criar nova fila narrativa.

### 4. Fazer o readback técnico (Sol)

Sol repete a tarefa e os critérios em termos de resultado verificável, audita o diff completo e reproduz pelo menos os casos de maior risco no artefato exato. Compara resultado Python/CLI/MCP, casos parciais, documentação pública e matriz. Para cada alegação devolve **aceita, corrigir ou sem evidência**, com arquivo/linha ou comando. Um aceite anterior não se transfere para versão, wheel ou fonte diferente. Contradição relevante volta a Luna com teste de reprodução e critério de correção; publicação requer gate final do plano de produto.

## Estados de evidência

| Estado | Prova mínima | Uso na comunicação |
| --- | --- | --- |
| Hipótese | Comportamento esperado ou indício sem execução | Não anunciar |
| Implementado offline | Código e teste de contrato sem rede | Compatibilidade técnica, sem alegar operação real |
| Observado live | CNJ, grau e resposta da própria fonte, data, escopo e estado | Apenas a capacidade e amostra observadas |
| Pronto para release | Jornada no artefato instalado, casos negativos/parciais, CI e promessa pública coerente | Anunciável com limites explícitos |
| Indisponível/inconclusivo | Timeout, bloqueio, configuração ausente ou falha sem resposta conclusiva | Não converter em inexistência processual |

Um teste unitário não prova operação live; índice não prova download; PDF individual não prova autos integrais. As perspectivas de produto, jurídico, dados, segurança e QA conferem essas distinções antes da promoção. A amostragem deve cobrir diversidade real por fonte/grau/capacidade; contagem isolada de CNJs não substitui estratificação nem casos negativos.

## Critérios para encerrar a rodada

Luna conclui P0–P5 ou identifica uma dependência externa específica com evidência e efeito na promessa. Sol encerra a revisão somente depois de registrar veredito de lançamento por escopo e artefato. Qualidade significa identidade correta, completude honesta, documentos vinculados, erros úteis, compatibilidade, segurança, usabilidade e instalação reproduzível. Percentual de cobertura de testes é indicador auxiliar. A aprovação técnica não equivale a pesquisa com usuários, parecer jurídico ou conformidade externa.
