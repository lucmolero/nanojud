# Segurança

Se você encontrar uma falha de segurança, exposição indevida de dados ou comportamento que possa incentivar uso abusivo das fontes consultadas, não abra uma issue pública com detalhes sensíveis.

## Como reportar

Use o relato privado de vulnerabilidades do GitHub: <https://github.com/lucmolero/nanojud/security/advisories/new>. Só o mantenedor vê o relato. Envie:

- descrição resumida do problema;
- impacto potencial;
- passos mínimos para reprodução, quando seguro;
- sugestão de mitigação, se houver.

## Escopo

O projeto se preocupa especialmente com:

- vazamento de dados pessoais em logs, fixtures ou exemplos;
- tratamento inadequado de documentos restritos;
- chamadas excessivas ou comportamento agressivo contra serviços públicos;
- parsing que misture dados de processos diferentes;
- mensagens que induzam usuários a interpretar dados incompletos como definitivos.

## Fora de escopo

Este projeto não oferece suporte para burlar autenticação, captcha, segredo de justiça, controle de acesso, paywalls ou limitações impostas pelas fontes consultadas.
