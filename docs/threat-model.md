# Modelo de Ameaças

Este modelo descreve riscos práticos para uso da biblioteca em ambiente jurídico.

## Ativos protegidos

- Dados pessoais em extratos, peças, logs e cache.
- Credenciais e tokens de ambientes que integrem a biblioteca.
- Integridade dos dados extraídos.
- Disponibilidade das fontes públicas consultadas.
- Reputação profissional de usuários e mantenedores.

## Riscos

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Vazamento de extratos ou peças | Exposição de dados pessoais e estratégia jurídica | `.gitignore`, sanitização, controle de acesso e revisão antes de publicar |
| Coleta excessiva | Bloqueio, dano reputacional ou violação de regras | rate limit, cache, finalidade definida e volume proporcional |
| Mudança de HTML da fonte | Dados incompletos ou parsing incorreto | fixtures, testes, erros explícitos e versionamento |
| Logs com dados sensíveis | Exposição operacional | logging moderado e política de retenção |
| Acesso sem contexto de sessão | Exposição indevida ou resultado incorreto | escopo de sessão explícito, autorização de acesso, erros tipados e segregação de cache |

## Fora de escopo

Modos com sessão exigem credenciais fornecidas pelo usuário e isolamento por consulta. A existência de uma peça no índice não implica disponibilidade do arquivo. O modelo deve ser revisto ao adicionar uma integração ou alterar o tratamento de credenciais.
