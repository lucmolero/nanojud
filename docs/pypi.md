# Distribuição e publicação

A NanoJud é distribuída como um pacote Python: `nanojud`. A instalação básica fornece biblioteca e CLI; o extra `mcp` fornece o servidor local `nanojud-mcp`, e o extra `pdf` adiciona leitura opcional de PDFs.

```bash
python -m pip install "nanojud[mcp,pdf]"
python -c "import nanojud; print(nanojud.__version__)"
```

O comando acima instala a versão disponível no [PyPI](https://pypi.org/project/nanojud/). Em 13/11/2026, a versão publicada era 0.5.1; o código 0.6.0 deste repositório ainda era candidato. Use o [quickstart](quickstart.md) para testar essa candidata antes do lançamento.

## Servidor MCP

Clientes que aceitam `uvx` podem iniciar a versão publicada por `stdio`:

```bash
uvx --from "nanojud[mcp]" nanojud-mcp
```

Para usar a candidata, aponte o cliente para o Python do ambiente virtual criado no checkout. A configuração está em [instalação com IA](instalacao-com-ia.md).

## Procedimento de lançamento

Esta seção é um roteiro de publicação; não indica que a versão 0.6.0 já foi aprovada ou publicada.

1. Fechar a [matriz de cobertura](fontes.md) com as capacidades verificadas no código e no pacote final.
2. Alinhar versão, faixa de Python, notas de versão, README, site e metadados do pacote.
3. Executar os gates de testes, tipos, lint, documentação e dependências na árvore final, incluindo CI Linux na faixa suportada.
4. Construir wheel e sdist, executar `twine check`, instalar o wheel em ambiente limpo e repetir os exemplos de Python, CLI e MCP.
5. Verificar o pacote no TestPyPI e conferir versão, extras, comandos e ferramentas MCP instalados a partir dele.
6. Publicar no PyPI pelo fluxo configurado, instalar a versão pública em ambiente limpo e conferir site, links e notas de versão.

O fluxo do repositório usa publicação confiável via GitHub Actions e OIDC. A versão publicada no PyPI é imutável; se houver correção após a publicação, ela requer nova versão. Os gates técnicos locais da candidata 0.6.0 passaram; a revisão editorial final, a validação no TestPyPI e a publicação ainda estão pendentes. Consulte as [notas da 0.6.0](release-notes-v0.6.0.md) para o escopo candidato.
