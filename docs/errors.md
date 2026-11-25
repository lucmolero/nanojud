# Erros

Erros previstos usam exceções públicas de `nanojud.exceptions`.

## Exceções

- `FormatoCNJInvalido`: número CNJ mal formatado, com dígito inválido ou incompatível com o escopo exigido pela operação.
- `URLInvalida`: URL fora do host ou da rota oficial aceitos pela integração consultada.
- `ConsultaIndisponivel`: fonte indisponível, HTTP inesperado, timeout, JSON inválido ou resposta JSON fora do formato esperado.
- `ProcessoNaoEncontrado`: a fonte indica ausência de processo ou página sem dados de processo.
- `AcessoRestrito`: a fonte exige identificação ou outra condição de acesso, ou recusa a consulta. Inclui desafios interativos e páginas que declaram explicitamente um bloqueio automatizado; a biblioteca informa o bloqueio e não tenta resolvê-lo.
- `DownloadIndisponivel`: falha prevista ao baixar peças públicas candidatas.

## Exemplo

```python
from nanojud import api
from nanojud.exceptions import NanoJudError

try:
    extrato = api.get_extrato("123")
except NanoJudError as exc:
    print(type(exc).__name__, str(exc))
```

O CNJ inválido neste exemplo provoca `FormatoCNJInvalido` antes de qualquer
chamada à fonte. Para tratar falhas de rede, substitua-o por um CNJ válido e
capture a exceção tipada correspondente.

## CLI

A CLI imprime erros previstos em JSON e retorna código `2`:

```json
{
  "status": "erro",
  "erro": "FormatoCNJInvalido",
  "mensagem": "Dígito verificador CNJ inválido."
}
```
