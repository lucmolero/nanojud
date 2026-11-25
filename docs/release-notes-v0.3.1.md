# NanoJud v0.3.1

Release de maturidade para preparar o projeto para divulgação pública como biblioteca open source profissional de tecnologia jurídica.

## Destaques

- Novo `NanoJudClient` para automações profissionais.
- `NanoJudConfig` com timeout, rate limit, cache, TTL e User-Agent configurável.
- Cache JSON local, opt-in e com TTL.
- Pacote marcado como tipado com `py.typed`.
- CI com testes, cobertura, lint, formatação, build, auditoria de dependências e `mypy`.
- Documentação ampliada com metodologia, reprodutibilidade, LGPD, governança e modelo de ameaças.
- `CITATION.cff` para uso acadêmico e institucional.
- Workflow de release com artefatos anexados ao GitHub Release.

## Validação

- Testes: `53 passed`.
- Cobertura: `83.32%`.
- `ruff check`: aprovado.
- `ruff format --check`: aprovado.
- `mypy src`: aprovado.
- `mkdocs build --strict`: aprovado.
- `python -m build`: aprovado.
- `twine check`: aprovado.
- `pip-audit`: sem vulnerabilidades conhecidas no ambiente validado.

## Limites conhecidos

- O projeto está em beta.
- GitHub Pages depende do plano/configuração do repositório.
- Upload CodeQL para Code Scanning depende da feature estar habilitada.
- Publicação PyPI requer configurar Trusted Publisher no PyPI para `lucmolero/nanojud`.

## Para usuários jurídicos

Use apenas dados acessíveis no modo de consulta empregado. A disponibilidade de conteúdo depende da fonte e das permissões da sessão.
