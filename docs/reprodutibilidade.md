# Reprodutibilidade

Reprodutibilidade é essencial em tecnologia jurídica porque dados judiciais mudam ao longo do tempo.

## Ambiente

Recomendação mínima:

```bash
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest --cov
```

Em Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest --cov
```

## Registro de execução

Para rotinas reais, registre somente o necessário para reproduzir o comportamento. CNJ, URL de consulta e conteúdo de resposta podem revelar atividade jurídica; não os grave em log operacional por padrão. Se a correlação entre execuções for indispensável, use um identificador interno ou hash com segredo controlado pela organização, e defina acesso e retenção.

- versão do pacote e ambiente;
- identificador pseudonimizado da execução;
- data e hora;
- host/rota sem query string, tokens ou identificadores do processo;
- status da consulta e fonte;
- quantidade de movimentações e documentos, sem conteúdo;
- parâmetros operacionais não sensíveis de cache, timeout e rate limit.

Não registre sem necessidade:

- CNJ em claro;
- URL integral com query, tokens ou IDs de documentos;
- partes, advogados, textos de movimentos ou documentos;
- segredos de sessão, senha processual ou chave de API.

## Artefatos

Os artefatos de build são gerados com:

```bash
python -m build
python -m twine check dist/*
```

As releases no GitHub são criadas a partir de tags `v*`, com pacote anexado ao release.
