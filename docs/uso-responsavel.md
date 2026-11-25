# Uso Responsável

`nanojud` é uma ferramenta para organizar informações públicas ou legitimamente acessíveis pelo usuário. O projeto deve ser usado com cuidado jurídico, técnico e ético.

## Escopo do acesso

Cada fonte informa as capacidades disponíveis e os requisitos da sessão. A posse de uma senha ou credencial não altera as permissões concedidas pelo tribunal. Uma consulta pode retornar dados parciais, indisponibilidade ou exigência de autenticação; esses estados devem ser preservados em relatórios e automações.

## Recomendações

- Consulte apenas processos e dados que você tenha legitimidade para tratar.
- Evite armazenar dados sensíveis sem necessidade.
- Proteja arquivos JSON gerados pela CLI.
- Use intervalos razoáveis em automações.
- Registre a data da consulta quando usar dados em relatórios internos.
- Valide informações relevantes diretamente na fonte oficial antes de tomar decisões processuais.
- Use cache/rate limit em rotinas recorrentes quando disponível.

## LGPD e dados sensíveis

Processos judiciais podem conter dados pessoais, dados sensíveis, informações de menores, segredos comerciais e outros elementos protegidos. Ao usar a biblioteca, o operador continua responsável por base legal, finalidade, minimização, segurança e descarte adequado dos dados.
