# Checagem editorial de lançamento — uso interno

Esta lista é aplicada ao mesmo commit e ao mesmo wheel usados no aceite técnico. A versão 0.6.0 só deixa de ser chamada de candidata depois da publicação e de uma instalação limpa a partir do PyPI. O Sol registra a decisão; o Luna prepara provas e corrige o conteúdo.

## Antes de publicar

1. Confrontar cada linha da matriz pública com uma execução datada da fonte, grau e capacidade anunciados. Retirar da promessa qualquer linha sem evidência no artefato final.
2. Executar, em instalação limpa do wheel, todos os comandos copiáveis do README, quickstart, guia do advogado, demonstração, instalação com IA, CLI, API e MCP. Conferir versão, saída, estados parciais e mensagem de erro.
3. Testar a jornada humana e a de agente: busca, linha do tempo, comunicação, peça quando acessível, tabela, lote, falha parcial e exportação. Conferir que cada resposta preserva fonte e grau.
4. Revisar títulos, navegação, links internos e externos, blocos de código, ortografia e legibilidade em desktop, mobile e teclado. Rodar `mkdocs build --strict`.
5. Confirmar que README, página inicial, notas, PyPI, `pyproject.toml`, CLI e `__version__` descrevem a mesma versão, faixa de Python, extras e limites.
6. Conferir que os exemplos não afirmam uma situação processual atual sem consulta recente, não expõem dados pessoais desnecessários e não confundem índice de peças, download individual e autos completos.

## Depois de publicar

1. Instalar do PyPI em ambiente limpo, repetir a consulta e a inicialização MCP, e registrar versão e resultado.
2. Trocar em README e site as notas de “candidata”, data e versão anterior pelas informações efetivamente publicadas; preservar limites da matriz que continuarem abertos.
3. Conferir páginas implantadas, links, metadados, licença e notas de versão; a documentação servida deve corresponder ao pacote publicado.
4. Registrar tag, URL do pacote, hash do artefato, commit, veredito e problemas residuais. Publicar correções de código ou pacote somente em nova versão.

Uma checagem executada antes de alteração posterior no código, metadados ou documentação não vale para o novo artefato. Repetir as etapas afetadas.

## Execução da candidata local 0.6.0 — 13/11/2026

Esta seção registra o que foi verificado nesta árvore e no wheel atual. “Sintaxe válida” não significa que um exemplo foi executado; consultas live são provas apenas da amostra, fonte, grau e data indicados.

| Item | Evidência atual | Estado |
| --- | --- | --- |
| Inventário do conteúdo público | 25 páginas na navegação MkDocs e README foram percorridos; 82 blocos de código: 45 Bash, 19 Python, 10 JSON, 7 de texto e 1 PowerShell | Inventariado |
| Python e JSON | Os 19 blocos Python passaram `ast.parse` e Ruff `F821`; os 10 blocos JSON foram decodificados. A tabela da API e a exceção de CNJ inválido foram executadas no wheel. O exemplo de lote gerou um item `partial`, DJEN `ok` com 8 comunicações e DataJud `error` por timeout; removi o JSONL após resumir estados. Extração agregada DataJud/DJEN retornou 8 registros DJEN e erro isolado DataJud; PJe/TJMG + DataJud retornou `partial` com 240 eventos; e-SAJ 2G + DataJud retornou `partial` com 25 eventos. Login e MNI dependem de interação/credenciais reais | Sintaxe e nomes resolvidos; execução por amostra, estados parciais observados |
| CLI | `--ajuda`, `--versao` e `--ajuda` nos 13 subcomandos documentados passaram no wheel instalado. Extraí as 46 invocações `nanojud` dos blocos Bash e executei cada uma com CNJ deliberadamente inválido ou arquivo sintético: todas chegaram ao parser/validador sem iniciar consulta externa. No wheel, `esaj-2g` retornou `ok`; `esaj-2g-pdf` baixou peça vinculada com 281.488 bytes e assinatura PDF. O exemplo `autos` 2G produziu 1 item `partial` e 7 PDFs válidos (exit code 1). A jornada e-SAJ 1G `extrato --inspecionar-pecas` → `ler-pecas --limite 1` retornou extrato `partial` com 100 movimentos e uma resposta de leitura; ambos os JSONs temporários foram removidos. O comando documentado PJe/TJMG retornou CNJ exato, `status=ok`, 319 movimentos e 20 candidatos; completude não foi inferida dessa contagem. O fluxo offline `tabela` → `baixar` → `ler-pecas` preservou proveniência em fixture sintética | Argumentos e jornadas documentais exercitados; amostras live não exaustivas |
| Python | Consulta e-SAJ pelo `NanoJudClient`, exemplo `examples/consulta_processual_com_tabela.py`, PJe/TJMG, documento individual e exemplos agregados constam no relatório operacional. Executei no wheel a tabela da API (2 linhas, estados `ok`/`partial`), o caso `FormatoCNJInvalido`, configuração do cliente e `exports.to_table` | Executado por amostra e casos offline registrados |
| MCP | O wheel instalado iniciou por `stdio`; `server_info` informou 0.6.0, inventário conteve 26 ferramentas e `gerar_tabela` preservou proveniência em entrada sintética. Consultar DJEN live foi exercitado anteriormente para o mesmo código-fonte | Executado; a resposta live não foi repetida após rebuild apenas editorial |
| Configurações MCP | Os blocos JSON de configuração são sintaticamente válidos. Os caminhos marcados como placeholder precisam ser substituídos pelo consumidor; não são configurações executáveis literalmente | Modelo validado, requer configuração local |
| Instalação publicada e candidata | Instalei `nanojud[mcp,pdf]` do PyPI em venv isolada: `pip check`, import, versão 0.5.1 e `nanojud --help` passaram. Também executei literalmente `uvx --from "nanojud[mcp]" nanojud-mcp`, completei o handshake MCP, listei 9 ferramentas e confirmei por `server_info` a versão 0.5.1 e transporte `stdio`. A candidata local 0.6.0 foi validada separadamente. A versão 0.5.1 não oferece `python -m nanojud` nem `--versao`; os guias de candidata não devem ser aplicados a essa versão publicada | Ambos os caminhos distinguidos e verificados |
| Fontes/credenciais | eproc/TJMG não teve submissão da confirmação visual; eproc/TJSP não possui resposta positiva comprovada; MNI exige endpoint e credencial provisionados; autenticação e senha de processo são exemplos de fluxo interativo | Dependência externa; sem resultado positivo atribuível nesta rodada |
| Inspeção editorial e visual | REA registrou capturas da página inicial desktop 1365×900 e mobile 390×844. Após a última correção CSS, Edge/Playwright verificou 40 páginas geradas em 1365×900, 390×844 e 320×700: 120 combinações, sem overflow, imagens sem `alt`, IDs duplicados, controles visíveis sem nome heurístico ou erros de página JavaScript. Uma verificação de reflow em 640 px também não encontrou overflow. A travessia por teclado final cobriu 1.564 paradas nas 40 páginas; todas tinham indicador de foco. No campo de busca, foco e placeholder tiveram contraste calculado acima de 4,5:1 nos estados fechado e aberto. Corrigi os rótulos teal pequenos da home. Medi as nove ocorrências em captura de página inteira: contraste mínimo 4,86:1 e máximo 5,70:1 nos pixels de fundo amostrados ao lado dos rótulos. Amostragem de 101 pontos nos gradientes normal e hover do botão primário encontrou contraste mínimo de 4,91:1 para texto branco. O atalho Ctrl+= no Edge automatizado não alterou viewport nem escala, portanto zoom real não foi validado. Não foi feita avaliação WCAG completa nem inspeção visual manual página a página | Parcial; responsividade, teclado e contraste dos componentes verificados estão delimitados |

### Pendências que mantêm P4 aberto

- Completar a reprodução das saídas documentadas que ainda não constam nas evidências deste relatório. As jornadas e-SAJ 1G/2G, PJe/TJMG, lote, autos e fluxos offline já exercitados estão delimitados por fonte e amostra acima; isso não prova funcionamento de cada bloco nem cobertura completa.
- A evidência de navegação cobre responsividade, foco por teclado e contraste do controle de busca; não equivale a auditoria WCAG de todos os textos/componentes, zoom real do navegador ou inspeção visual manual de cada página. O bloqueio do desafio eproc TJMG permaneceu sem submissão: o usuário relatou que não conseguiu preencher; o portal não forneceu resultado e isso não altera a classificação do provedor.
- Na home, os rótulos pequenos `.legal-kicker` e `.legal-card__label` usavam `#18a999` sobre superfícies claras: a verificação inicial calculou 2,75:1 no fundo base e 2,93:1 no cartão branco. Foram alterados para `#0b736c`. Uma primeira tentativa de amostrar pixels de rótulos abaixo da dobra usou coordenadas fora da captura viewport e foi descartada. A reamostragem em screenshot de página inteira mediu os nove rótulos adjacentes ao fundo real, com mínimo 4,86:1; não se deve usar os valores antigos calculados apenas com o fundo base como resultado final. O gradiente do CTA em hover termina na cor teal escura; 101 amostras de cada gradiente mantiveram no mínimo 4,91:1 para texto branco. Esses resultados são limitados à home e aos componentes citados, não cobrem todas as combinações de texto, estados ou conteúdo de terceiros no site.
- A tentativa de zoom por atalho no Edge headless e headed não alterou escala/viewport; a rodada de 640 px é evidência de reflow nessa largura, não teste de zoom de navegador a 200%.
- As chamadas que ainda exigem login oficial e senha processual em `docs/api-reference.md`/`docs/mcp-local.md` não foram executadas: dependem da sessão do advogado e de eventual senha autorizada. O callback do MCP está identificado como ponto de integração e falha de modo explícito até o host configurá-lo. Exemplos MNI dependem de endpoint e credencial provisionados. Não usar endpoints/segredos fictícios para alegar execução.
- Após resolver qualquer divergência, reconstruir e reinstalar o artefato, comparar novamente README/metadados, executar o checklist afetado e atualizar o hash usado na auditoria Sol.

### Classificação dos 19 blocos Python

“Executado por amostra” significa que uma execução correspondente está registrada no wheel 0.6.0; não garante resposta idêntica futura da fonte. Um exemplo com pré-requisito só é copiável após preenchimento da configuração e, quando indicado, ação do advogado.

| Arquivo e linha | Estado verificável |
| --- | --- |
| `README.md:66`, `docs/quickstart.md:35` | Mesmo exemplo `NanoJudClient.get_extrato`; executado no wheel, status `partial` e origem e-SAJ conferidos. |
| `docs/api-reference.md:79` | Executei o bloco exato no wheel com o login, `get_extrato` e `ler_pecas` substituídos por mocks; as três chamadas esperadas ocorreram sem rede. Login live ainda requer ação do advogado e sessão válida. |
| `docs/api-reference.md:91` | Executei o bloco exato no wheel com login, `getpass` e `get_extrato` simulados; as chamadas ocorreram sem rede e sem solicitar nem registrar senha real. Login live exige sessão e senha fornecidas pelo advogado. |
| `docs/api-reference.md:141` | Consulta PJe/TJMG e leitura de PDF. Executei o bloco exato extraído do Markdown no wheel 0.6.0 com os dois métodos da fonte substituídos por mocks/fixture: consulta e leitura foram chamadas uma vez, CNJ do exemplo foi preservado e nenhum tráfego foi enviado. Isso verifica o encadeamento executável, não a resposta do portal. A sessão do ensaio live mais recente expirou sem saída recuperável; não repetir a consulta live equivalente nesta rodada. |
| `docs/api-reference.md:172` | Executei o bloco exato no wheel com `consultar_processo` simulado; a configuração-placeholder e a chamada foram aceitas sem rede. Não há evidência live do endpoint/credenciais dessa instalação. |
| `docs/api-reference.md:195` | Executei o bloco exato no wheel com `consultar_extrato` simulado; o contexto de cliente e chamada foram aceitos sem rede. Endpoint/token são placeholders; não há evidência live. |
| `docs/api-reference.md:211` | Executei o bloco exato no wheel com `consultar_eproc_tjsp_1g` simulado; a função e o objeto de retorno foram consumidos sem rede. A consulta live da fonte permanece sem resultado positivo demonstrado e não deve ser descrita como cobertura confirmada. |
| `docs/api-reference.md:220` | Extração PJe/TJMG + DataJud; amostra registrada com 240 eventos e status `partial`, DataJud sujeito a indisponibilidade. |
| `docs/api-reference.md:244` | Fábrica e configuração do cliente; construção executada offline no wheel. |
| `docs/api-reference.md:265` | Lote JSONL; exemplo executado no wheel: DJEN `ok` com 8 comunicações, DataJud `error` por timeout e item `partial`. Arquivo temporário removido. |
| `docs/api-reference.md:295` | Exportação de tabela; executada com dados sintéticos, duas linhas e proveniência. |
| `docs/client.md:7` | `search_processo`; consulta de amostra executada no wheel, resposta `partial` de e-SAJ. |
| `docs/errors.md:16` | CNJ inválido; executado offline e gerou `FormatoCNJInvalido` antes da rede. |
| `docs/extraction.md:5` | DataJud + DJEN; executado por amostra, DJEN trouxe 8 comunicações completas e DataJud terminou em `ReadTimeout`; envelope parcial preservou a falha. |
| `docs/extraction.md:80` | Executei o bloco exato no wheel com `extract_process` simulado; a configuração MNI e seleção `sources=("mni",)` foram aceitas sem rede. Sem consulta autenticada live. |
| `docs/extraction.md:100` | Executei o bloco exato no wheel com `api.extract_process` simulado; a chamada retornou o envelope de fixture sem rede. Consultas PJe/TJMG live foram exercitadas em outras jornadas, com estados parciais e limites registrados; não atribuir à configuração MNI nem completude integral. |
| `docs/extraction.md:117` | e-SAJ 2G + DataJud; executado por amostra, 25 eventos e status `partial`. |
| `docs/mcp-local.md:72` | Executei o bloco exato no wheel com autenticação e `create_server` simulados. O cliente aceitou o callback, e o método `run` foi chamado com `transport="stdio"`; não iniciei um servidor real neste smoke. O callback contém `NotImplementedError` intencional e requer cofre/diálogo seguro no host; o exemplo não é um fluxo pronto de senha.

Os blocos com sessão, credencial e serviço externo foram executados com dependências externas simuladas quando possível; isso verifica que o exemplo percorre o contrato local, mas não autentica o advogado nem prova disponibilidade do serviço. A saída live específica do bloco PJe não é recuperável. Zoom real do navegador também permanece sem evidência; não mascarar essas lacunas com execução de um exemplo parecido.

### Wheel reconstruído após ajuste editorial

README é incorporado aos metadados do pacote; por isso o wheel e o sdist foram reconstruídos depois de alinhar as frases sobre os gates. `twine check` passou em ambos; o wheel foi reinstalado por cima no venv limpo, `pip check`, versão, localização em `site-packages`, CLI e MCP stdio (26 ferramentas e `gerar_tabela` sintético) passaram. SHA-256 atualizado está em `reports/arquivo/candidate-0.6.0-linux-matrix-2026-11-13.sha256`. O rebuild alterou README/metadata, não o código-fonte Python; a matriz Linux executada anteriormente cobre o mesmo código-fonte, mas não é uma execução remota de GitHub Actions para esta árvore sem commit.
