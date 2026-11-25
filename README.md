# NanoJud

Biblioteca Python, interface de linha de comando e servidor MCP local para consulta processual. A NanoJud reúne dados de fontes judiciais, identifica a origem de cada resultado e informa quando uma coleta está incompleta.

**Estado das versões em 13/11/2026:** a versão disponível no [PyPI](https://pypi.org/project/nanojud/) é a **0.5.1**. Este repositório contém uma **candidata local 0.6.0**, ainda sem publicação. Os exemplos de novas fontes, lote e tabela nesta documentação se referem à candidata; instalar do PyPI ainda não entrega essas funções. Confira a versão com `python -c "import nanojud; print(nanojud.__version__)"`.

## O que você pode fazer

- Consultar por número CNJ e receber capa, partes e movimentações quando a fonte as disponibilizar.
- Consultar comunicações do DJEN e metadados do DataJud como fontes separadas.
- Localizar peças acessíveis à sessão e obter um PDF pelo identificador quando a integração oferecer essa capacidade.
- Produzir uma linha do tempo, exportar registros e usar as mesmas informações em scripts, terminal ou agentes por MCP.
- Processar uma lista de processos com resultado individual e estados de falha parcial na candidata 0.6.0.

**Cobertura depende da fonte, do tribunal, do grau e da sessão.** A [matriz de fontes](https://lucmolero.github.io/nanojud/fontes/) separa consulta, publicações, índice de peças e download. eproc/TJSP e MNI operacional ainda não têm consulta positiva comprovada neste candidato. Uma resposta vazia em uma fonte não significa que o processo inexista.

## Instalação

### Versão publicada

Para instalar a 0.5.1 do PyPI, com biblioteca e CLI:

```bash
python -m pip install nanojud
```

Para incluir o servidor MCP e a leitura opcional de PDFs:

```bash
python -m pip install "nanojud[mcp,pdf]"
```

A versão publicada declara Python 3.10 ou superior. Seus comandos e ferramentas correspondem às [notas da versão publicada](https://github.com/lucmolero/nanojud/releases), não a todas as funções da candidata descritas abaixo.

### Candidata 0.6.0 neste repositório

Use Python 3.11.5 a 3.14. Na pasta raiz deste checkout:

```bash
python -m venv .venv
```

Ative o ambiente virtual: `.\.venv\Scripts\Activate.ps1` no PowerShell ou `source .venv/bin/activate` em Linux/macOS. Depois instale e confira:

```bash
python -m pip install -e ".[mcp,pdf]"
python -c "import nanojud; print(nanojud.__version__)"
```

O wheel candidato 0.6.0 passou pelos gates técnicos locais registrados nas [notas de versão](docs/release-notes-v0.6.0.md). A revisão editorial P4 e o aceite de lançamento pelo Sol continuam pendentes; a candidata não foi publicada.

## Primeira consulta

Com a candidata instalada:

```bash
nanojud consultar 0015020-23.2010.8.26.0053
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --recentes-primeiro --limite 20
nanojud djen 0015020-23.2010.8.26.0053
```

O caso é um exemplo público; andamentos, datas e disponibilidade mudam. `nanojud --ajuda` mostra as opções da instalação em uso. Para salvar um extrato, execute `nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json`; proteja o arquivo se contiver dados pessoais.

Em Python:

```python
from nanojud import NanoJudClient

cliente = NanoJudClient()
extrato = cliente.get_extrato("0015020-23.2010.8.26.0053")
print(extrato["status"])
print(extrato["origem"])
```

Confira `status`, avisos e indicadores de completude antes de usar os dados para uma conclusão. O [quickstart](https://lucmolero.github.io/nanojud/quickstart/) explica os retornos e o [guia do advogado](https://lucmolero.github.io/nanojud/guia-do-advogado/) acompanha a primeira consulta sem exigir programação.

## Uso com agentes

O extra `mcp` instala o servidor `nanojud-mcp`, executado localmente por `stdio`. Um cliente MCP que aceita processos externos pode usar:

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

Essa configuração instala a **versão publicada no PyPI**. Para testar as ferramentas da candidata, configure no cliente MCP o executável `nanojud-mcp` do ambiente virtual deste checkout. Reinicie o cliente e confira o inventário de ferramentas após trocar a instalação. Veja [configuração do MCP](https://lucmolero.github.io/nanojud/mcp-local/) e [instalação com agente](https://lucmolero.github.io/nanojud/instalacao-com-ia/).

Peça ao agente que apresente número CNJ, fonte, grau, data de coleta, movimentos relevantes, documentos consultados e limites. Respostas jurídicas devem distinguir fatos extraídos, inferências e pontos que exigem leitura dos autos.

## Documentos e lotes

Na candidata, o acesso a documentos é específico por peça e sessão. Um índice de peças não comprova que todos os arquivos possam ser obtidos; um PDF individual não comprova autos completos. As APIs de [cliente](https://lucmolero.github.io/nanojud/client/), [extração](https://lucmolero.github.io/nanojud/extraction/) e [MCP](https://lucmolero.github.io/nanojud/mcp-local/) mostram como verificar estados e limites. O lote preserva resultado e falha por processo.

## Qualidade e limites

O projeto mantém testes sem rede, testes live opcionais, contratos tipados, lint, checagem de tipos e construção de pacote. O wheel candidato 0.6.0 passou pelos gates técnicos locais descritos nas [notas de versão](docs/release-notes-v0.6.0.md); ainda falta concluir a revisão editorial e obter o aceite de lançamento. A biblioteca depende de sistemas externos, cujas respostas e disponibilidade podem mudar.

A NanoJud é independente dos tribunais e do CNJ. Use a proveniência para conferir atos e documentos na fonte antes de tomar uma providência processual. Consulte [uso responsável](https://lucmolero.github.io/nanojud/uso-responsavel/), [LGPD](https://lucmolero.github.io/nanojud/lgpd/) e [erros](https://lucmolero.github.io/nanojud/errors/).

## Desenvolvimento

Na raiz do repositório:

```bash
python -m pip install -e ".[dev,mcp,pdf]"
python -m pytest -q --cov
python -m ruff check src tests
python -m mypy src/nanojud
python -m mkdocs build --strict
```

Para contribuir, descreva o problema, a fonte/grau afetados, o comportamento observado e um teste de regressão quando houver mudança funcional. Não inclua credenciais nem conteúdo de peças em issues ou fixtures. Leia [contribuição](https://github.com/lucmolero/nanojud/blob/main/CONTRIBUTING.md), [segurança](https://github.com/lucmolero/nanojud/blob/main/SECURITY.md) e [roadmap](https://lucmolero.github.io/nanojud/roadmap/).

Licença MIT. Mantenedor: Luciano Molero.
