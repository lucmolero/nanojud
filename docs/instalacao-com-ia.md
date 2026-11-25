# Instalação com IA

Um cliente MCP pode executar a NanoJud localmente e usar suas ferramentas para consultar processos. Este guia distingue a versão [publicada no PyPI](https://pypi.org/project/nanojud/) da candidata 0.6.0 do repositório. Confira a versão e o inventário de ferramentas antes de seguir exemplos da candidata.

## Usar a versão publicada

Se o cliente aceitar `uvx`, configure o servidor por `stdio`:

```json
{
  "mcpServers": {
    "nanojud": {
      "command": "uvx",
      "args": ["--from", "nanojud[mcp]", "nanojud-mcp"]
    }
  }
}
```

`uvx` obtém a versão publicada no PyPI. Reinicie o cliente MCP após alterar a configuração. A posição exata desse bloco depende do cliente usado.

## Usar a candidata do repositório

Siga o [quickstart](quickstart.md) para criar o ambiente virtual e instalar `.[mcp,pdf]`. Configure o cliente para executar o Python desse ambiente com o módulo do servidor:

```json
{
  "mcpServers": {
    "nanojud": {
      "command": "CAMINHO_ABSOLUTO_PARA_O_PYTHON_DA_VENV",
      "args": ["-m", "nanojud.mcp_server"]
    }
  }
}
```

No Windows, o executável costuma estar em `.venv\\Scripts\\python.exe`; em Linux/macOS, em `.venv/bin/python`. Substitua o caminho pelo endereço absoluto real e use barras escapadas no JSON do Windows. Reinicie o cliente e confira se as ferramentas da versão instalada aparecem. O [guia MCP](mcp-local.md) descreve os contratos e parâmetros.

## Conferir a instalação

Peça ao agente para informar a versão instalada, listar as ferramentas NanoJud e validar um número CNJ. Depois use uma consulta que a [matriz de fontes](fontes.md) indique como observada. Se houver erro, peça o nome da ferramenta, os parâmetros usados e a mensagem retornada; não aceite uma resposta processual sem fonte.

Um pedido inicial:

```text
Consulte 0015020-23.2010.8.26.0053 com a NanoJud. Informe versão da biblioteca, ferramentas usadas, fonte, grau, data da coleta e estado de cada resposta. Apresente uma tabela dos movimentos mais recentes e das comunicações disponíveis. Separe fatos encontrados de inferências e registre documentos ainda não consultados.
```

O agente pode produzir tabela e síntese jurídica, mas um prazo, uma providência ou uma conclusão sobre o mérito exige conferência da publicação e das peças pertinentes na fonte oficial. Consulte [guia do advogado](guia-do-advogado.md) e [uso responsável](uso-responsavel.md).
