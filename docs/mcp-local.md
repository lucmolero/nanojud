# MCP Local

`nanojud` pode ser usado como servidor MCP local por `stdio`.

Esta referência descreve a candidata 0.6.0 do repositório. Os comandos que instalam pelo PyPI ou `uvx` obtêm a [versão publicada](https://pypi.org/project/nanojud/), cujo inventário de ferramentas pode ser diferente até o lançamento.

Essa camada atende clientes MCP executados na máquina do usuário. Ela não hospeda um endpoint público, não abre porta HTTP e mantém o contrato principal da biblioteca Python.

O servidor padrão consulta sem autenticação. Aplicações que incorporam a NanoJud podem fornecer um `NanoJudClient` com uma sessão obtida no fluxo oficial do Tribunal; o e-SAJ valida a permissão para cada processo. O transporte MCP padrão não pede nem grava senha, certificado ou número OAB.

## Instalação

Instale a biblioteca com o extra opcional `mcp`:

```bash
python -m pip install "nanojud[mcp]"
```

O extra `mcp` também instala `pypdf`, usado para extrair texto de PDFs públicos em memória quando a fonte permite.

Para usar a candidata depois de criar e ativar um ambiente virtual na raiz do repositório:

```bash
python -m pip install -e ".[mcp]"
```

## Executar sem clone com uvx

Em clientes MCP que aceitam executar comandos externos, você pode executar o servidor diretamente do PyPI:

```bash
uvx --from "nanojud[mcp]" nanojud-mcp
```

Configuração MCP:

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

Também é possível executar pelo módulo:

```bash
python -m nanojud.mcp_server
```

O transporte padrão é `stdio`.

### Incorporar uma sessão autenticada

O servidor MCP padrão pode ser autenticado sem código Python de integração. Depois de iniciar `nanojud-mcp`, invoque a ferramenta `autenticar_esaj`; ela abre o login oficial do e-SAJ num navegador visível na máquina que executa o servidor. O advogado completa no próprio portal o método disponível, como CPF/CNPJ e senha, código adicional ou certificado. Nenhum dado de login é enviado como argumento MCP. Os cookies ficam em memória no processo e não são escritos em arquivo.

Após sucesso, `consultar_esaj`, `extrair_processo`, `extrair_processos`, `consultar_autos_em_lote` e `ler_documentos_publicos` usam a sessão em memória para o e-SAJ. `consultar_datajud`, `consultar_djen` e `gerar_timeline` continuam consultando as fontes públicas; autenticar no e-SAJ não altera essas ferramentas. Lotes autenticados usam `max_workers=1` para manter uma única sessão HTTP isolada. Se o processo MCP for reiniciado, autentique-se novamente.

`server_info` inclui `esaj_session_authentication`: `not_configured` quando o servidor usa o fluxo público padrão, `host_supplied_unverified` quando o host fornece um cliente/sessão e `verified_by_official_login` após o login assistido concluir. O estado `host_supplied_unverified` não presume que a sessão esteja autenticada. `verified_by_official_login` registra que o portal confirmou a identidade durante o login; uma consulta posterior ainda pode ser recusada se a sessão expirar ou não tiver autorização para aquele processo.

O login assistido também pode ser incorporado por um host Python que precise fornecer seu próprio callback seguro para senha processual:

```python
from nanojud import NanoJudClient, autenticacao
from nanojud.mcp_server import create_server

sessao = autenticacao.autenticar_esaj_no_navegador()


# Substitua esta implementação por integração ao cofre ou diálogo seguro do host.
def obter_senha_segura(numero, documentos):
    raise NotImplementedError("Conecte o callback ao cofre institucional do host.")


cliente = NanoJudClient(session=sessao, senha_processo_provider=obter_senha_segura)
servidor = create_server(client=cliente)
servidor.run(transport="stdio")
```

O callback do exemplo é intencionalmente um ponto de integração: substitua o
`NotImplementedError` por acesso ao cofre ou diálogo seguro do seu host antes de
usar peças que solicitem senha processual.

Instale com `python -m pip install "nanojud[mcp,autenticacao]"` e o Chromium do Playwright com `python -m playwright install chromium`. Se a autenticação informar que o executável não foi encontrado, rode o segundo comando no mesmo ambiente Python que inicia o MCP. Para um navegador Chromium já instalado, o host Python pode passar seu caminho em `autenticar_esaj_no_navegador(executable_path=...)`. A instalação padrão continua sem login até a ferramenta ser invocada. Para senha processual, o callback Python só é chamado quando há documentos restritos; a senha não é argumento MCP e não é registrada. O e-SAJ valida a autorização e decide quais peças são liberadas. O login assistido requer uma sessão desktop com navegador visível; em hosts sem interface gráfica, use o fluxo Python incorporado com o mecanismo de autenticação aprovado pelo ambiente.

## Configuração em cliente MCP local

Use o Python do ambiente onde o pacote esta instalado.

Exemplo genérico:

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

Depois de atualizar ou instalar uma versão nova, encerre e reabra o cliente MCP. Confira
`server_info` e a lista de ferramentas exposta pelo cliente: a versão deve corresponder à
instalação pretendida, e ferramentas novas (como `extrair_processos` e
`consultar_autos_em_lote`) só aparecem quando o servidor carregado já contém esses recursos.
Se a versão ou a lista estiver antiga, o cliente está iniciando outra instalação do pacote;
revise o caminho do Python configurado e reinstale a versão desejada nesse ambiente. Durante
o desenvolvimento deste checkout, instale com `python -m pip install -e ".[mcp]"` e aponte o
cliente para o Python desse ambiente virtual.

No Windows:

```json
{
  "mcpServers": {
    "nanojud": {
      "command": "C:\\caminho\\para\\nanojud\\.venv\\Scripts\\python.exe",
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
- `autenticar_esaj`: abre o login oficial e configura a sessão em memória para as ferramentas e-SAJ compatíveis. `timeout_login` aceita de 30 a 1800 segundos.
- `validar_cnj`: valida e normaliza número CNJ.
- `extrair_numeros_cnj_de_texto`: extrai numeros CNJ encontrados em texto livre.
- `consultar_esaj`: consulta extrato público do e-SAJ/TJSP. Aceita `limite_movimentacoes` (padrão 100; `0` busca todas), `desde` (AAAA-MM-DD) e `compacto` (padrão `true`, omite texto repetido e documentos por movimentação).
- `consultar_esaj_tjsp_2g` consulta capas, movimentos e vínculos documentais no CPoSG em sessão independente. Um CNJ pode retornar vários recursos. Aceita `max_paginas` (1 a 100, padrão 10 por resultado) e informa a completude das movimentações. Os vínculos vêm com `status_acesso=nao_verificado`.
- `obter_documento_esaj_tjsp_2g` recebe o CNJ próprio do resultado e o `cd_documento` listado. Revalida o vínculo e o acesso no portal e entrega o PDF como recurso binário, com limite de 8 MiB.
- Em `consultar_autos_em_lote`, `source="esaj_tjsp_2g"` seleciona os vínculos do CPoSG. A resposta marca `autos_completos=false` e identifica cada peça pelo CNJ e código do recurso. Use `ler_documentos=true` para receber texto em memória.
- Em `extrair_processo` e `extrair_processos`, selecione `sources=["esaj_tjsp_2g"]` para consultar o CPoSG em sessão pública. A linha do tempo conserva os vínculos documentais, o CNJ próprio e a URL de cada recurso.
- `obter_documento_esaj`: recebe CNJ e `cd_documento` listado por `consultar_esaj`, valida o documento na sessão e devolve PDF como recurso MCP binário. `max_bytes` vai de 1 byte a 8 MiB e limita o stream; peças não listadas como acessíveis retornam erro de acesso ou documento ausente conforme a fonte.
- `consultar_pje_tjmg`: consulta páginas públicas de movimentos/documentos do PJe/TJMG, até 100 por tabela. É opt-in; `prazo_total` limita busca, detalhe e paginação (padrão 60 s, `None` desativa). Se vencer durante a coleta, preserva o que já foi recebido e retorna `partial`.
- `consultar_tjrj_1g`: consulta a SPA pública do TJRJ, seleciona a origem de primeiro grau, expande os eventos agrupados e pagina históricos volumosos pelo cursor oficial. `max_paginas_movimentos` aceita 1–500 (padrão 150); a resposta informa páginas e eventos e fica `partial` se o teto, uma falha ou um cursor inválido impedir confirmar o fim. Sete CNJs foram validados, incluindo um histórico com 1.574 eventos em 104 páginas completas. A ferramenta permanece opt-in e não lista nem baixa documentos.
- `consultar_tjmg_2g_legado`: consulta o detalhe público legado TJMG 2G e pode retornar movimentos, campos básicos, partes/advogados e vínculos de documentos expostos na página. Exige CNJ e identificador interno `listaProcessos` de 17 dígitos; valida também o sequencial nas páginas auxiliares. O ID não é derivado do CNJ; o retorno é sempre `partial`, pois paginação e completude do índice documental não foram comprovadas. Não faz a busca massiva nem normaliza publicações.
- `obter_documento_tjmg_2g_legado`: obtém em memória PDF, DOC ou DOCX que esteja listado com vínculo público na página do mesmo processo; revalida CNJ/ID, impõe limite de até 8 MiB, confere assinatura/MIME e retorna o conteúdo como recurso MCP. A ferramenta não grava a peça em disco nem segue redirecionamentos.
- `consultar_eproc_tjsp_1g` e `consultar_eproc_tjsp_2g`: automatizam a Consulta Unificada pública eproc/TJSP em cada grau com Chromium/Playwright; exigem `nanojud[autenticacao]` e `python -m playwright install chromium`. Retornam capa, eventos e vínculos expostos, sem baixar peças. `aguardar_desafio_interativo=True` mantém o navegador visível à espera da ação do operador e retoma a consulta quando o portal mostrar o resultado; o padrão espera até 30 segundos (ou o `timeout`, se menor) por verificação automática antes de retornar `AcessoRestrito`. A biblioteca não resolve desafios nem fabrica tokens. A captura direta de dados continua pendente de um resultado positivo verificável.
- `ler_documento_pje_tjmg`: obtém texto em memória de PDF oferecido publicamente pelo botão oficial do PJe/TJMG; valida URL, limita a transferência a 8 MiB e limita `max_chars` (inteiro de 1 a 10.000). O servidor mantém uma sessão HTTP PJe no processo entre consulta e leitura.
- `obter_documento_pje_tjmg`: retorna o PDF público como recurso binário MCP (`application/pdf`), sem caminho local. `max_bytes` vai de 1 byte a 8 MiB e o limite também é aplicado durante o streaming. Para PDFs maiores, use `baixar_documento_pje_tjmg` num cliente que compartilhe o sistema de arquivos do servidor.
- `baixar_documento_pje_tjmg`: baixa o PDF oferecido publicamente pelo PJe para `documento.pdf` numa pasta temporária exclusiva criada pelo servidor e retorna o caminho local e o tamanho. A ferramenta aceita somente a URL, sem caminho de destino arbitrário; o arquivo permanece após a chamada para o cliente MCP poder abri-lo.
- `limpar_documentos_temporarios`: remove pastas temporárias NanoJud de autos e documentos PJe com idade mínima configurável (`min_age_hours`, padrão 24, intervalo de 1 hora a 1 ano). Examina somente diretórios diretamente na pasta temporária do sistema que tenham prefixo NanoJud e marcador de propriedade válido criado pelo servidor; pastas sem marcador, recentes, links simbólicos e arquivos de outros aplicativos são preservados.
- `consultar_datajud`: consulta dados processuais estruturados no DataJud/CNJ e pagina até dez páginas de dez registros com `search_after` quando o total exato excede a primeira página. Pode retornar `status=partial` se o total não for confirmado, uma página falhar, o cursor não avançar ou exceder 100 registros. `metadata.records_pages`, `records_returned` e `records_complete` tornam a completude observável. `prazo_total` (padrão 60 segundos) limita retries, esperas e paginação desta consulta; `None` remove esse teto. Aceita `compacto` (padrão `true`), que omite o `payload_origem` repetido de cada movimento, preservando os avisos.
- `consultar_djen`: consulta comunicações do DJEN e retorna `count`, `comunicacoes`, `status`, `completo`, `paginas` e `avisos`. Teto de páginas, limite de tempo ou falha após páginas úteis geram `partial`, preservando os itens coletados; o orçamento de 120 segundos não é deadline rígida de rede. Lista vazia não significa inexistência do processo.
- `extrair_processo`: retorna envelope versionado por fonte. Sem `sources`, consulta as três fontes padrão; informe uma ou mais para restringir a consulta. Uma lista vazia é rejeitada. Usa a sessão MCP para o e-SAJ quando autenticada. Aceita `desde` e `compacto` (padrão `true`, mantém só a timeline unificada, sem repetir movimentações e comunicações em `data`). TJRJ 1G é opt-in por `sources=["tjrj_1g"]`; MNI exige endpoint/credencial no ambiente do servidor.
- `extrair_processos`: consulta de 1 a 50 números CNJ numa chamada, preserva a ordem e retorna contagens e resultados individuais. Para incluir PJe/TJMG, selecione explicitamente `sources=["pje_tjmg"]`; cada item preserva o estado `partial` e os avisos quando restam páginas. Usa a sessão MCP para o e-SAJ quando autenticada; nesse caso `max_workers` deve ser 1. Sem sessão, `max_workers` aceita de 1 a 4 (padrão 1). A fonte MNI usa a configuração do ambiente MCP e continua opt-in. `limite_movimentacoes=0` busca todos os movimentos do e-SAJ; lotes maiores devem usar Python ou CLI `batch`.
- `consultar_autos_em_lote`: consulta até 10 processos TJSP/eSAJ ou TJMG/PJe e baixa PDFs acessíveis em pastas por processo, ou tenta ler texto em memória. `max_documentos_por_processo` é inteiro de 1 a 10 e `max_chars` é inteiro de 1 a 10.000; booleanos e frações são rejeitados antes de criar pastas ou consultar fontes. PJe/TJMG percorre até 100 páginas por tabela e mantém estado `partial` se restarem páginas ou ocorrer falha. A lista `downloaded` inclui só arquivos obtidos ou já existentes; falhas aparecem em `document_statuses`. Em modo de leitura, `texto_extraido` e `texto_html_extraido` contam como texto obtido; PDF sem texto, parser ausente, sessão expirada ou falha de extração mantêm o estado parcial. Processos de outros tribunais retornam `unsupported`.
- `gerar_timeline`: retorna uma timeline cronológica, sem interpretação jurídica. Aceita `limit`, `recent_first`, `include_text` e `max_text_chars` para reduzir o contexto.
- `gerar_tabela`: recebe `registros` estruturados previamente obtidos e, opcionalmente, `colunas` e `source_status` do `gerar_timeline`; devolve `row_count`, `columns`, `rows` e CSV. Quando fornecido, propaga o estado por fonte a cada linha conforme `fonte`, sem sobrescrever `status_fonte` já presente. Não consulta fontes nem grava arquivos; limita a 250 linhas e 200.000 caracteres e neutraliza fórmulas só no CSV. Para comunicações com texto integral, selecione colunas concisas (por exemplo, `id`, `dataDisponibilizacao`, `tipoComunicacao`, `numero_processo`, `fonte` e `status_fonte`) para evitar exceder o limite de saída.
- `ler_documentos_publicos`: lê documentos públicos candidatos em memória, sem salvar PDF em disco. Cada PDF é limitado a 8 MiB durante a transferência; um documento maior aparece como falha individual. `limite` é inteiro de 1 a 10 e `max_chars` é inteiro de 1 a 10.000; os dois são validados antes de consultar o processo. A resposta inclui `status` (`ok`, `partial` ou `no_documents`), `total_public_candidates`, `restricted_documents` e `movimentacoes_completas`. `partial` indica paginação não confirmada, documentos restritos, candidatos acima do limite ou falhas de extração. `no_documents` só é usado quando a listagem está completa e não há candidatos públicos nem documentos restritos.

O diretório de download é criado pelo processo MCP e permanece após uma chamada concluída para que o cliente possa abrir os arquivos. Se a iteração do lote falhar antes de devolver o resultado, a pasta exclusiva daquela chamada é removida automaticamente. O servidor grava um marcador de propriedade e a limpeza exige esse marcador, além do prefixo NanoJud e localização direta na pasta temporária. Depois de copiar ou abrir os arquivos, um agente pode chamar `limpar_documentos_temporarios`; o padrão só remove diretórios sem alterações por pelo menos 24 horas, e essa limpeza não é automática. A idade considera também os arquivos internos e não segue links simbólicos. Esse caminho só é acessível a clientes que compartilham o sistema de arquivos do servidor; para clientes remotos, use `obter_documento_esaj` ou `obter_documento_pje_tjmg` dentro do limite de 8 MiB. Para escolher o destino diretamente, use as funções de download da API Python ou `NanoJudClient` em um aplicativo confiável.

## Leitura de documentos sem salvar PDF

A ferramenta `ler_documentos_publicos` permite que agentes leiam peças públicas sem gerar arquivos locais.

Fluxo técnico:

1. consulta o extrato público do e-SAJ;
2. identifica documentos publicos candidatos;
3. abre metadados da pasta digital quando disponíveis;
4. solicita o conteúdo público;
5. processa bytes em memoria;
6. retorna texto, estado, quantidade de bytes e avisos.

Limites importantes:

- nenhum PDF e salvo em disco;
- PDFs públicos precisam ser transferidos para memória para que o texto seja extraído;
- documentos com senha, CAPTCHA, sigilo ou restrição de acesso não são acessados;
- sem `pypdf`, a ferramenta retorna `pdf_parser_indisponivel` para os PDFs;
- use `limite` e `max_chars` para evitar respostas longas demais em agentes.

## Escopo de Seguranca

O servidor MCP local extrai e normaliza dados. A ferramenta `consultar_autos_em_lote` grava PDFs acessíveis de eSAJ/TJSP ou PJe/TJMG em pastas temporárias criadas pelo próprio servidor quando `ler_documentos=false`; as demais ferramentas não recebem caminhos de destino para arquivos.

O servidor não:

- escreve em caminhos arbitrários do usuário;
- publica dados;
- burla autenticação, CAPTCHA, senha ou segredo de justiça;
- emite aconselhamento jurídico;
- classifica risco, fase ou relevância jurídica.

## DataJud

A API pública do DataJud/CNJ usa a chave pública documentada na Wiki oficial do DataJud/CNJ.

A biblioteca inclui a chave pública vigente como fallback. Caso o CNJ rotacione a chave, informe a nova chave como argumento da ferramenta ou variável de ambiente:

- `NANOJUD_DATAJUD_API_KEY`
- `DATAJUD_API_KEY`
- `CNJ_DATAJUD_API_KEY`

## MNI SOAP 3.0 e 2.2.2

Para usar `sources=["mni"]` em `extrair_processo` ou `extrair_processos`, configure `NANOJUD_MNI_ENDPOINT` e credenciais no ambiente do servidor MCP. `NANOJUD_MNI_VERSION` aceita `3.0` ou `2.2.2`; sem ela, mantém o padrão legado 3.0. A versão 3.0 aceita `NANOJUD_MNI_TOKEN` ou `NANOJUD_MNI_USERNAME` + `NANOJUD_MNI_PASSWORD`. A versão 2.2.2 exige `USERNAME` + `PASSWORD` (`idConsultante`/`senhaConsultante`) e não aceita token. `NANOJUD_MNI_TRIBUNAL`, `NANOJUD_MNI_GRAU` e `NANOJUD_MNI_MOVIMENTACOES_COMPLETAS` são opcionais; `PESSOA_VINCULADA` aplica-se ao 3.0. Defina segredos somente no ambiente do servidor, nunca como argumentos de ferramentas. Sem endpoint configurado, a fonte retorna `ConsultaIndisponivel` no envelope. O contrato 2.2.2 tem testes offline; operação real depende de endpoint e credenciais provisionados para a instalação. O TJRJ publica a integração MNI e seu fluxo de provisionamento. Consulte a [matriz de fontes](fontes.md) antes de configurar: o endpoint de produção ainda precisa ser confirmado neste projeto.

## Arquitetura

O MCP local é uma camada fina sobre a API pública da biblioteca:

```text
cliente MCP local
  -> stdio
  -> nanojud.mcp_server
  -> nanojud.api
  -> eSAJ / DataJud / DJEN / PJe-TJMG (opt-in)
```

Essa separação mantém o núcleo da biblioteca independente do MCP. Quem usa apenas Python ou CLI não precisa instalar o SDK MCP.

Para uma instalação guiada por agente, veja [Instalação Com IA](instalacao-com-ia.md).
