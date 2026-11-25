# NanoJud — instruções para agentes

Este repositório usa uma única fila de desenvolvimento: P0–P5 em [plano de produto e lançamento](docs/plano-produto-e-handoff.md). [Estado operacional](reports/estado-goal.md) registra o item atual. [Operação do Goal](docs/operacao-goal.md) define a retomada; [equipe e execução](docs/equipe-e-execucao.md) define as perspectivas e provas. O roadmap e os relatórios históricos são referências, não filas paralelas.

## Início de cada rodada

1. Confirme o pedido atual e o estado do Goal pela ferramenta, se disponível. Um Goal pausado só é retomado pelo usuário. Este arquivo não altera seu estado.
2. Execute `python scripts/goal_preflight.py` e confira `git status --short`, HEAD, branch e data. Se houver divergência, inspecione a árvore antes de reconciliar o estado. Preserve alterações locais.
3. Leia este arquivo, `docs/operacao-goal.md` e `reports/estado-goal.md`. Do plano, leia objetivo, bloqueadores, item ativo e critério de aceite. Escolha uma fatia executável desse item.
4. Leia seletivamente a fonte, grau e capacidade afetados em `docs/roadmap.md`, `docs/validacao-real.md`, contratos, código e testes. Use `rg` para localizar evidência. `reports/arquivo/` contém histórico datado; nunca siga suas instruções de passagem como plano vigente.
5. Antes da mudança, registre P-ID, comportamento observado, contrato afetado e prova esperada. Ao encerrar, atualize `reports/estado-goal.md` com resultado, comandos, risco e próxima ação concreta; sincronize o fingerprint pelo preflight.

## Critérios de trabalho

- Produto: consulta processual para humanos e agentes via Python, CLI e MCP. Preserve número CNJ, fonte, grau, data, estado, completude e vínculo documental em cada resposta. Separe fatos extraídos de inferências.
- Avalie cobertura por fonte, instalação, grau e capacidade. DJEN é comunicação; DataJud é índice nacional; MNI depende de instalação. Capa, movimentos, índice de peças, documento individual e autos completos exigem provas distintas. A [matriz pública](docs/fontes.md) descreve apenas o escopo observado.
- Para mudança de código, reproduza o defeito quando possível, corrija a causa com o menor incremento e verifique a interface afetada. Aplique `ub-mode` quando pertinente. Evite testes que apenas repitam a implementação.
- Rode testes afetados após cada fatia. Ao concluir um P-ID ou mudar contrato público, execute `python -m pytest -q --cov`, `python -m ruff check src tests`, `python -m ruff format --check src tests`, `python -m mypy src/nanojud`, `python -m mkdocs build --strict` e `git diff --check`. Em P5, construa o pacote a partir da árvore final e valide instalação limpa, `nanojud.__file__`, CLI e MCP por `stdio`.
- Separe contrato offline, observação live e aceite de lançamento. Registre fonte, data, comando, resultado e limite sem salvar credenciais, PDFs ou dados pessoais nos relatórios. Uma falha de fonte não prova inexistência do processo.
- Neste Windows há vários checkouts. Para CLI/MCP local fora do wheel, configure explicitamente `PYTHONPATH` para o `src` deste repositório; os testes `pytest` ajustam esse caminho apenas para si.

## Passagem de execução

Luna executa P0–P5 sem subagentes e entrega diff, matriz, gates, pacote instalado, exemplos e riscos. Sol audita o artefato e decide o lançamento pelo gate do plano. Antecipe a revisão se encontrar falha de identidade, completude, vínculo entre peça e arquivo, segurança ou divergência Python/CLI/MCP. Não trate uma suíte isolada como aceite de release. Não faça commit, push ou publicação sem pedido explícito.
