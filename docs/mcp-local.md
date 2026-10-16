# MCP Local

`nanojud` pode ser usado como servidor MCP local por `stdio`.

Essa camada foi desenhada para clientes MCP que rodam na maquina do usuario. Ela nao hospeda endpoint publico, nao abre porta HTTP e nao muda o contrato principal da biblioteca Python.

Para advogados, a lógica é simples: o agente de IA chama ferramentas locais para consultar fontes públicas, e o resultado volta estruturado com fonte, data e limites. A análise jurídica continua sendo humana.

## Instalacao

Instale a biblioteca com o extra opcional `mcp`:

```bash
python -m pip install "nanojud[mcp]"
```

O extra `mcp` tambem instala `pypdf`, usado para extrair texto de PDFs publicos em memoria quando a fonte permite.

Para desenvolvimento completo:

```bash
python -m pip install -e ".[dev,mcp]"
```

## Executar sem clone com uvx

Em clientes MCP que aceitam executar comandos externos, voce pode rodar o servidor diretamente do PyPI:

```bash
uvx --from "nanojud[mcp]" nanojud-mcp
```

Configuracao MCP enxuta:

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

## Executar

```bash
nanojud-mcp
```

Tambem e possivel executar pelo modulo:

```bash
python -m nanojud.mcp_server
```

O transporte padrao e `stdio`.

## Configuracao em cliente MCP local

Use o Python do ambiente onde o pacote esta instalado.

Exemplo generico:

```json
{
  "mcpServers": {
    "nanojud": {
      "command": "python",
      "args": ["-m", "nanojud.mcp_server"],
      "env": {
        "NANOJUD_DATAJUD_API_KEY": "APIKey ..."
      }
    }
  }
}
```

Em ambiente virtual local, use o caminho absoluto do Python da `.venv`.

No Windows:

```json
{
  "mcpServers": {
    "nanojud": {
      "command": "C:\\Users\\luciano.finozzi\\Desktop\\Lib Python - Esaj - Datajud\\.venv\\Scripts\\python.exe",
      "args": ["-m", "nanojud.mcp_server"],
      "env": {
        "NANOJUD_DATAJUD_API_KEY": "APIKey ..."
      }
    }
  }
}
```

## Jornada com Claude Code, Codex, Gemini ou cliente MCP

1. Instale `nanojud` com o extra `mcp`.
2. Configure o cliente MCP apontando para `python -m nanojud.mcp_server`.
3. Peça ao agente para validar o CNJ antes de consultar.
4. Solicite respostas com separação entre fatos extraídos e hipóteses.
5. Valide atos sensíveis na fonte oficial.

Prompt sugerido:

```text
Use o MCP local nanojud para consultar 0015020-23.2010.8.26.0053.
Primeiro valide o CNJ. Depois consulte as fontes públicas disponíveis.
Entregue dados básicos, últimas movimentações e timeline.
Não invente teses e não dê aconselhamento jurídico.
```

## Ferramentas

- `server_info`: retorna metadados do servidor MCP local.
- `validar_cnj`: valida e normaliza numero CNJ.
- `extrair_numeros_cnj_de_texto`: extrai numeros CNJ encontrados em texto livre.
- `consultar_esaj`: consulta extrato publico do eSAJ/TJSP. Aceita `limite_movimentacoes` (padrao 100; `0` busca todas), `desde` (AAAA-MM-DD) e `compacto` (padrao `true`, omite texto repetido e documentos por movimentacao).
- `consultar_datajud`: consulta dados processuais estruturados no DataJud/CNJ. Aceita `compacto` (padrao `true`), que omite o `payload_origem` repetido de cada movimento.
- `consultar_djen`: consulta comunicacoes do DJEN e retorna `count` e `comunicacoes`.
- `extrair_processo`: retorna envelope versionado por fonte. Aceita `desde` e `compacto` (padrao `true`, mantem so a timeline unificada, sem repetir movimentacoes e comunicacoes em `data`).
- `gerar_timeline`: retorna timeline cronologica sem interpretacao juridica. Aceita `limit`, `recent_first`, `include_text` e `max_text_chars` para reduzir contexto.
- `ler_documentos_publicos`: le documentos publicos candidatos em memoria, sem salvar PDF em disco.

## Leitura de documentos sem salvar PDF

A ferramenta `ler_documentos_publicos` foi pensada para agentes de IA que precisam ler pecas publicas sem gerar arquivos locais.

Fluxo tecnico:

1. consulta o extrato publico do eSAJ;
2. identifica documentos publicos candidatos;
3. abre metadados da pasta digital quando disponiveis;
4. solicita o conteudo publico;
5. processa bytes em memoria;
6. retorna texto, status, quantidade de bytes e avisos.

Limites importantes:

- nenhum PDF e salvo em disco;
- PDFs publicos ainda precisam ser transferidos para memoria para extracao de texto;
- documentos com senha, captcha, sigilo ou restricao de acesso nao sao acessados;
- se `pypdf` nao estiver instalado, PDFs retornam `pdf_parser_indisponivel`;
- use `limite` e `max_chars` para evitar respostas longas demais em agentes.

## Escopo de Seguranca

O servidor MCP local e somente de extracao e normalizacao.

Ele nao:

- salva pecas em disco automaticamente;
- escreve arquivos;
- publica dados;
- burla autenticacao, captcha, senha ou segredo de justica;
- emite aconselhamento juridico;
- classifica risco, fase ou relevancia juridica.

## DataJud

A API publica do DataJud/CNJ usa chave publica documentada na Wiki oficial do DataJud/CNJ.

A biblioteca inclui a chave publica vigente como fallback. Caso o CNJ rotacione a chave, envie a chave atualizada por argumento da ferramenta ou por variavel de ambiente:

- `NANOJUD_DATAJUD_API_KEY`
- `DATAJUD_API_KEY`
- `CNJ_DATAJUD_API_KEY`

## Arquitetura

O MCP local e uma camada fina sobre a API publica da biblioteca:

```text
cliente MCP local
  -> stdio
  -> nanojud.mcp_server
  -> nanojud.api
  -> eSAJ / DataJud / DJEN
```

Essa separacao mantem o nucleo da biblioteca independente do MCP. Quem usa apenas Python ou CLI nao precisa instalar o SDK MCP.

Para uma instalação guiada por agente, veja [Instalação Com IA](instalacao-com-ia.md).
