# Operação do Goal — uso interno

O Goal do Codex guarda objetivo e estado na conversa. O repositório guarda fila, evidência e ponto de retomada. O pedido mais recente do usuário prevalece; nenhum arquivo cria, retoma ou conclui um Goal. Consulte o estado pela ferramenta em cada rodada.

## Fontes de verdade

| Pergunta | Consulte |
| --- | --- |
| O que o usuário quer agora e o Goal está ativo? | Pedido atual e ferramenta de Goal |
| Qual é o escopo e quando termina? | `docs/plano-produto-e-handoff.md`, P0–P5 e gate Sol |
| Qual item e próximo passo? | `reports/estado-goal.md`, reconciliado com Git |
| Como executar e quais provas exigir? | `AGENTS.md` e `docs/equipe-e-execucao.md` |
| O que a fonte fez? | Código, testes, resposta live datada e `docs/validacao-real.md` |

O relatório extenso em `reports/arquivo/` contém decisões e testes de rodadas anteriores. Ele não define prioridades atuais. Busque nele apenas a seção necessária para uma dúvida específica.

## Retomada em cada continuação

1. Conferir Goal, data, pasta, branch e `git status --short`. Executar `python scripts/goal_preflight.py`.
2. Ler `AGENTS.md`, este arquivo e `reports/estado-goal.md` integralmente. Se o fingerprint, HEAD ou item divergir, inspecionar as mudanças e corrigir o estado antes de editar código.
3. Ler do plano o resultado esperado, os bloqueadores, o P-ID ativo e o aceite. Consultar em `docs/equipe-e-execucao.md` as perspectivas pertinentes.
4. Buscar a fonte/grau/capacidade da fatia em roadmap, validação, catálogo de casos, contratos, código e testes. Não carregar documentos históricos inteiros por rotina.
5. Declarar `P-ID | fato observado | aceite verificável | próxima ação` e executar no mesmo turno.

## Seleção e fechamento

Corrija primeiro uma falha reproduzida de identidade, completude, documento, segredo ou contrato público. Dentro do P-ID ativo, escolha uma fatia que entregue comportamento observável em Python, CLI ou MCP. Em P3, avance por fonte × instalação × grau × capacidade: SP 1G/2G, depois RJ, depois MG; DataJud e DJEN mantêm alcance nacional. Se uma linha depender de condição externa, registre evidência e gatilho de retomada, retire-a da promessa e continue outra linha independente.

Depois de cada fatia, execute os testes pertinentes e atualize `reports/estado-goal.md` com contexto consultado, decisão, arquivos, comando/resultado, evidência live, risco e uma próxima ação. Ao fechar um P-ID, compare cada critério do plano com prova concreta e execute os gates de `AGENTS.md`. Em P5, confira o wheel final instalado e MCP por `stdio`. Recalcule o fingerprint e sincronize `goal-tree` no estado.

Luna só entrega o pacote de passagem quando P0–P5 estiverem demonstrados ou quando uma dependência externa estiver documentada e fora da promessa. Sol audita o diff, reproduz os riscos materiais e decide o lançamento. Se houver contradição, corrija-a e repita os gates afetados. Não marque um Goal como concluído por terminar uma rodada ou um teste isolado.
