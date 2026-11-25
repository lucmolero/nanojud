# Metodologia

Este projeto privilegia rastreabilidade e previsibilidade em vez de automação opaca.

## Premissas

- A biblioteca consulta fontes públicas ou legitimamente acessíveis pelo usuário.
- Cada modo de acesso informa seus requisitos de sessão e as capacidades disponíveis.
- Cada retorno deve deixar claro origem, status e limites conhecidos.
- Testes automatizados usam fixtures sanitizadas, sem depender de rede.

## Coleta

A coleta é feita por chamadas HTTP conservadoras, com validação de CNJ antes da consulta e tratamento explícito de falhas esperadas. Quando uma página muda, o comportamento correto é falhar de forma compreensível e gerar nova fixture sanitizada para manutenção.

## Estruturação

Os dados extraídos são organizados em contratos públicos documentados. O objetivo não é substituir análise jurídica, mas reduzir trabalho repetitivo e criar uma base auditável para revisão humana, relatórios e integrações.

## Pesquisa e academia

Para uso acadêmico, registre:

- versão da biblioteca;
- data e hora da coleta;
- fonte consultada;
- filtros aplicados;
- critérios de exclusão;
- eventuais falhas de consulta.

Use o arquivo `CITATION.cff` para citar o projeto em trabalhos, artigos ou repositórios derivados.
