# Primeira consulta

Este guia usa a candidata 0.6.0 do repositório. Até a publicação, `pip install nanojud` instala a [versão disponível no PyPI](https://pypi.org/project/nanojud/), cuja interface pode ser diferente. Confira a [cobertura por fonte](fontes.md) antes de automatizar uma rotina.

## Instalar a candidata

Use Python 3.11.5 a 3.14. Na raiz do repositório:

```bash
python -m venv .venv
```

Ative o ambiente virtual (`.\.venv\Scripts\Activate.ps1` no PowerShell ou `source .venv/bin/activate` em Linux/macOS). Depois instale e confira:

```bash
python -m pip install -e ".[mcp,pdf]"
python -c "import nanojud; print(nanojud.__version__)"
```

Como alternativa à ativação, use o Python desse ambiente com `-m nanojud`.

## Consultar

```bash
nanojud consultar 0015020-23.2010.8.26.0053
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --recentes-primeiro --limite 20
nanojud djen 0015020-23.2010.8.26.0053
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
```

O exemplo é um processo público do TJSP. A resposta, o tempo de consulta e a disponibilidade das fontes variam. `consultar` resume a pesquisa; `extrato` é específico do e-SAJ/TJSP. DJEN fornece comunicações, não autos. O DataJud pode trazer metadados e movimentos, mas uma ausência ou falha nessa fonte não comprova inexistência do processo.

## Usar em Python

```python
from nanojud import NanoJudClient

cliente = NanoJudClient()
extrato = cliente.get_extrato("0015020-23.2010.8.26.0053")
print(extrato.get("status"))
print(extrato.get("origem"))
```

Leia `status`, `origem` e eventuais avisos antes de interpretar os movimentos. Para outro tribunal ou grau, escolha a fonte compatível; `get_extrato` acima consulta o e-SAJ/TJSP. Veja [cliente Python](client.md), [CLI](cli.md) e [erros](errors.md).

## Próximo passo

O [guia do advogado](guia-do-advogado.md) explica a leitura do resultado. Para conectar um agente, siga [instalação com IA](instalacao-com-ia.md). Antes de uma providência jurídica, confira o ato e a peça pertinentes no portal de origem.
