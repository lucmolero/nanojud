# Quickstart

Este guia mostra o caminho mais curto para instalar o projeto e fazer uma consulta básica usando a demonstração pública recomendada: `0015020-23.2010.8.26.0053`. Se você não programa, o [Guia do advogado](guia-do-advogado.md) explica tudo desde a instalação do Python.

## Instalar

Para usar o pacote publicado:

```bash
python -m pip install nanojud
```

Para também ler o texto de peças em PDF (`ler-pecas`):

```bash
python -m pip install "nanojud[pdf]"
```

Para usar tambem o MCP local:

```bash
python -m pip install "nanojud[mcp]"
```

Para contribuir no repositorio clonado:

```bash
python -m pip install -e ".[dev]"
```

## Consultar pelo terminal

```bash
nanojud consultar 0015020-23.2010.8.26.0053
nanojud partes 0015020-23.2010.8.26.0053
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --recentes-primeiro --limite 20
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
```

No terminal o resultado vem em texto legível; com `--out` ou ao redirecionar, vem em JSON. Se `nanojud` não for reconhecido, use `python -m nanojud`. Passo a passo completo, com instalação do Python no Windows: [Guia do advogado](guia-do-advogado.md).

## Usar em Python

Para quem programa. A primeira consulta:

```python
from nanojud import api

numero = "0015020-23.2010.8.26.0053"
resumo = api.search_processo(numero)

print(resumo["numero"])
print(resumo["classe"])
print(resumo["ultima_movimentacao"])
```

## Gerar extrato

```python
from nanojud import api

extrato = api.get_extrato("0015020-23.2010.8.26.0053")
print(extrato["dados_basicos"])
print(len(extrato["movimentacoes"]))
```

## Usar cliente configurável

```python
from nanojud import NanoJudClient, NanoJudConfig

client = NanoJudClient(
    NanoJudConfig(
        timeout=20,
        rate_limit_interval=1.0,
        cache_enabled=True,
    )
)

resumo = client.search_processo("0015020-23.2010.8.26.0053")
print(resumo["classe"])
```

## Tratar erros previstos

```python
from nanojud import api
from nanojud.exceptions import NanoJudError

try:
    extrato = api.get_extrato("0015020-23.2010.8.26.0053")
except NanoJudError as exc:
    print(type(exc).__name__, str(exc))
```

## Próximo passo

Leia a [Demonstração Pública](demonstracao-publica.md) para entender por que esse processo foi escolhido e consulte o guia de [uso responsável](uso-responsavel.md) antes de automatizar consultas recorrentes.
