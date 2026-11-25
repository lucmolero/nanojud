# API Reference

## `api.search_processo(numero)`

Para CNJs do TJSP, consulta o e-SAJ de primeiro grau; para outros tribunais, consulta o DataJud. Retorna um resumo estruturado com `numero`, `fonte`, `grau`, `data_coleta`, `coleta_completa`, `status` e os campos processuais disponíveis.
`coleta_completa` reflete a paginação informada pela fonte: movimentos do e-SAJ ou registros do DataJud. Se ela for interrompida, `status="partial"` e `mensagem` preserva o aviso. Quando a fonte não fornece algum metadado, a API o deixa vazio ou como `None` em vez de inferi-lo.

## `api.get_extrato(numero, baixar_pecas=False, limite_pecas=3, *, inspecionar_pecas=False, limite_inspecao_pecas=10, salvar_html=False, pasta_pecas=None, session=None, senha_processo=None, timeout=30.0)`

Monta o extrato do processo, com a cobertura que a fonte disponibiliza para a sessão usada.
Se a paginação de movimentações ficar incompleta, `status` será `partial` e `mensagem` incluirá o aviso da fonte.

Parâmetros:

- `numero`: número CNJ TJSP.
- `baixar_pecas`: tenta baixar os documentos que a fonte expõe à sessão.
- `limite_pecas`: limite de peças para download.
- `pasta_pecas`: diretório para salvar PDFs baixados; quando omitido, mantém o padrão `esaj_pecas`.
- `session`: sessão HTTP opcional. Passe uma `requests.Session` autenticada pelo fluxo oficial do Tribunal para que a consulta preserve essa identidade e seus cookies.
- `timeout`: limite aplicado às requisições da consulta e ao percurso de páginas do portal. O padrão é 30 segundos por operação, inclusive quando uma `requests.Session` comum é injetada. `NanoJudClient` usa o valor de `NanoJudConfig.timeout` também ao inspecionar, ler e baixar peças.
- `senha_processo`: senha que o usuário está autorizado a usar no formulário oficial do processo. A NanoJud a envia para cada recurso restrito e não a inclui no extrato. Prefira `getpass` ou um cofre de segredos; não passe o valor em argumentos de CLI, URLs ou logs.
- `inspecionar_pecas`: busca metadados da pasta digital para documentos candidatos.
- `limite_inspecao_pecas`: limite de inspeções.
- `salvar_html`: salva HTML bruto da consulta em `esaj_raw/tjsp/cpopg`.

## `api.consultar_esaj_tjsp_2g(numero, *, timeout=30.0, max_paginas=10)`

Consulta pública do CPoSG por CNJ, em sessão própria. A busca pode devolver
vários recursos para um único número de origem. `numero_consultado` identifica a
entrada e `resultados_listados` preserva o CNJ e a URL de cada resultado
identificado na resposta do portal. `resultados` traz capa e movimentos para
até dez desses registros, na ordem do portal.

`max_paginas` aceita de 1 a 100 páginas de movimentos por resultado. Cada
resultado informa `movimentacoes_completas` e, quando aplicável, a causa da
coleta parcial. `status=ok` indica que a coleta de movimentos terminou para os
resultados retornados. `partial` indica limite, falha isolada ou paginação
inconclusiva. `erro` indica que nenhuma capa da lista foi confirmada. Um
formulário sem resultado verificável levanta `ConsultaIndisponivel`.

Cada movimentação traz `documentos`, com o identificador e o título dos
vínculos exibidos pelo portal. `status_acesso=nao_verificado` indica que a
consulta encontrou o vínculo e que a abertura da peça exige verificação
própria. A lista cobre os movimentos coletados. O CPoSG tem entrada própria
para consulta de capa, movimentos e vínculos documentais.

## `api.obter_pdf_esaj_tjsp_2g(numero, cd_documento, *, timeout=30.0, max_paginas=10, max_bytes=8388608)`

Retorna os bytes de um PDF do CPoSG. Use o CNJ próprio do resultado de
segundo grau e o `cd_documento` listado na movimentação. A biblioteca
revalida o vínculo em sessão pública e segue a verificação de acesso do
portal para aquela peça. A busca termina assim que encontra o vínculo.
`max_paginas` limita a busca pelo vínculo e
`max_bytes` limita o download a até 8 MiB. Se o portal negar acesso, a
chamada sinaliza a restrição. Esta operação cobre a peça individual.

Para consultar vários CNJs, passe `source="esaj_tjsp_2g"` a
`api.iter_extract_dockets(numeros, destination=...)`. O manifesto
identifica os vínculos de cada recurso e registra falhas ou restrições por
peça. A coleta cobre os vínculos das movimentações observadas e marca
`autos_completos=false`. Por padrão, cada PDF pode ter até 8 MiB.

## `api.get_partes(numero)`

Retorna partes classificadas por polo quando a estrutura da página permite.

## `api.baixar_pecas(extrato, destino, sobrescrever=False, limite=0, *, session=None)`

Baixa documentos presentes no extrato e acessíveis pela sessão. `limite` deve ser inteiro não negativo; `0` significa sem limite por processo. Passe a mesma sessão autenticada usada na consulta.

## `api.ler_pecas(extrato, limite=3, max_chars=4000, *, session=None)`

Lê documentos acessíveis pela sessão em memória, sem salvar PDFs em disco. `limite` e `max_chars` devem ser inteiros não negativos; `0` significa sem limite para o respectivo parâmetro. Cada resposta transferida para leitura é limitada a 8 MiB durante o stream; documentos maiores retornam `documento_muito_grande`.

Quando a fonte retorna um PDF acessível à sessão, até 8 MiB são transferidos para memória por peça e o texto é extraído com o parser opcional `pypdf`. O limite é conferido durante o stream; `max_chars` limita o texto final, não o tamanho da transferência. Se o parser não estiver instalado, o retorno informa `pdf_parser_indisponivel`. O Tribunal decide quais peças a identidade da sessão pode consultar.

Para reutilizar uma sessão oficial na API de alto nível:

```python
from nanojud.autenticacao import autenticar_esaj_no_navegador
from nanojud.api import get_extrato, ler_pecas

numero = "INFORME_O_NUMERO_CNJ"
sessao = autenticar_esaj_no_navegador()  # login no navegador oficial, operado pelo advogado
extrato = get_extrato(numero, session=sessao)
pecas = ler_pecas(extrato, limite=10, session=sessao)
```

Para consultar peças que apresentam o campo oficial de senha do processo, a API aceita a senha em memória. O portal documenta o uso da senha para partes/interessados; o advogado deve autenticar-se no e-SAJ e depender da autorização concedida à sua identidade.

```python
from getpass import getpass
from nanojud.autenticacao import autenticar_esaj_no_navegador
from nanojud.api import get_extrato

numero = "INFORME_O_NUMERO_CNJ"
sessao = autenticar_esaj_no_navegador()
senha = getpass("Senha do processo: ")
extrato = get_extrato(numero, session=sessao, senha_processo=senha)
```

Use a mesma sessão em `get_extrato` e em `baixar_pecas` ou `ler_pecas` quando houver autorização por senha ou login.

A sessão de advogado pode ser obtida pelo login oficial com `autenticacao.autenticar_esaj_no_navegador()` (instale `nanojud[autenticacao]`); `timeout_login` aceita de 1 a 1800 segundos. O advogado escolhe no portal CPF/CNPJ e senha, código adicional ou certificado. Também se pode fornecer uma sessão autenticada pelo host. A OAB pode identificar vínculo, mas não substitui a autenticação do e-SAJ. `NanoJudClient(session=sessao)` mantém a sessão entre operações; extratos de sessões injetadas ou com senha não são compartilhados pelo cache local. Para o MCP, configure `senha_processo_provider` no cliente para buscar a senha num cofre ou diálogo local, sem expô-la como argumento da ferramenta.

Para percorrer CNJs e obter documentos em fluxo, use `api.iter_extract_dockets(numeros, destination=..., ...)` ou `NanoJudClient.iter_extract_dockets(...)`. O lote roteia eSAJ/TJSP e PJe/TJMG pelo CNJ, processa os processos sequencialmente e cria uma pasta por processo quando baixa PDFs. `timeout` limita cada requisição HTTP e valida antes de consumir o iterador; o padrão é 30 segundos. Fechar ou interromper o fluxo não encerra à força uma chamada de rede já iniciada. `max_documents_per_process` deve ser um inteiro não negativo; `0` significa sem limite por processo. Booleanos e números fracionários são rejeitados, pois `False` poderia remover o limite acidentalmente. Com `read_documents=True`, tenta extrair texto em memória. Para PJe/TJMG, percorre até 100 páginas por tabela e mantém `partial` se houver falha ou páginas acima do limite; o mesmo cliente mantém a sessão entre consulta e acesso aos PDFs. Cada item indica `ok`, `partial`, `no_documents`, `unsupported` ou `error`. `downloaded` lista somente arquivos obtidos ou já existentes; `document_statuses` registra também falhas por peça. Outros tribunais ainda não têm adaptador de autos em lote; PDFs digitalizados sem camada textual não passam por OCR.

Use o campo `arquivo` do manifesto para abrir o PDF. No PJe/TJMG, o caminho deriva do identificador da peça ou, quando ausente, do link público. Arquivos antigos com nome sequencial permanecem no destino e devem ser associados às peças pelo manifesto da execução que os gerou.

## `api.resumo_rapido(numero)`

Retorna texto curto para triagem, briefing ou e-mail.

## `api.consultar_djen(numero, data_inicio="")`

Consulta comunicações do DJEN para o número CNJ informado. O adaptador usa a paginação oficial do DJEN (`pagina` e `itensPorPagina`), com tamanho padrão de 100 itens e teto de 100 páginas. Internamente, aceita tamanho de 5 ou 100; os demais valores são rejeitados antes da chamada de rede. `api.consultar_djen` não expõe o tamanho de página como argumento. Uma lista vazia indica ausência de resultados na janela consultada. Respostas fora do formato esperado geram `ConsultaIndisponivel`.

`api.consultar_djen_detalhado(numero, data_inicio="")` retorna `comunicacoes`, `status`, `completo`, `paginas` e `avisos`. Use essa variante para saber se a busca terminou: teto de páginas, página repetida, limite de tempo ou falha após páginas úteis produzem `partial`, preservando as comunicações obtidas. A implementação usa orçamento total padrão de 120 segundos e limita cada timeout HTTP ao tempo restante; por usar `requests`, esse orçamento não é um prazo rígido garantido contra todo comportamento de rede. A função histórica acima preserva a lista como retorno, sem indicador de completude. Uma lista vazia só descreve a consulta DJEN feita; não confirma inexistência do processo.

Cada comunicação normalizada inclui `fonte="djen"` para preservar proveniência em agregações e exportações. Cada comunicação incluída na resposta detalhada precisa declarar o mesmo CNJ consultado. Itens sem identidade verificável ou de outro processo são descartados e fazem o resultado permanecer `partial`.

## `api.consultar_datajud(numero, *, api_key=None, include_raw=False, prazo_total=60.0)`

Consulta dados processuais estruturados na API pública DataJud/CNJ e solicita até dez registros por página para consolidar os graus. Quando o total exato excede a primeira página, percorre `search_after` com ordenação `@timestamp`, até dez páginas (100 registros). Confere que o CNJ retornado corresponde exatamente ao consultado e, quando o CNJ tem alias DataJud conhecido, que a sigla do tribunal retornado corresponde ao tribunal esperado ([campo `tribunal`](https://datajud-wiki.cnj.jus.br/api-publica/glossario/), [aliases oficiais](https://datajud-wiki.cnj.jus.br/api-publica/endpoints/), [paginação oficial `search_after`](https://datajud-wiki.cnj.jus.br/api-publica/exemplos/exemplo3/)). Registro sem identidade, com CNJ inválido/divergente ou tribunal incompatível gera `ConsultaIndisponivel`; não é associado ao processo consultado nem tratado como ausência. `metadata.records_complete` indica se a resposta confirma todos os registros; inclui `records_returned`, `records_pages`, `total_hits` e `total_relation`. O retorno é `partial` se o total falta, é apenas um limite inferior, a paginação falha, o cursor não avança ou o limite de páginas é atingido. Dados da primeira página são preservados em falha posterior. Uma consulta vazia só resulta em `nao_encontrado` quando o DataJud confirma total zero. A extração agregada e `search_processo` preservam o estado parcial e seus avisos. `retry` limita as tentativas por página para falhas de transporte e respostas transitórias HTTP 408, 429, 500, 502, 503 e 504. A biblioteca respeita `Retry-After` em segundos ou data HTTP quando presente; se o servidor solicitar espera acima de 60 segundos, encerra sem repetir cedo. Sem esse cabeçalho válido, o atraso cresce linearmente por tentativa a partir de `backoff`, que deve ser finito e não negativo. `backoff=0` desativa essa espera de fallback. Respostas de autenticação ou erros HTTP não transitórios não são repetidos.

`prazo_total` limita, em segundos, o tempo acumulado entre requisições, tentativas e esperas de retry/paginação; `None` desativa o orçamento total. Cada chamada de rede recebe no máximo o menor valor entre `timeout` e o tempo restante. O limite é cooperativo e não cancela trabalho já iniciado: espera interna de uma sessão customizada ou uma resposta que continue entregando bytes pode ultrapassar o prazo, mas a biblioteca não inicia outro retry/página após a expiração. `extract_process` passa ao DataJud o tempo restante do envelope compartilhado.

Usa a chave pública vigente documentada na Wiki oficial do DataJud/CNJ como fallback. O parâmetro `api_key` existe para override explícito quando necessário. Para controlar `indice`, `session`, `timeout`, `retry` ou `backoff`, use `nanojud.datajud.consultar_processo` diretamente; o `prazo_total` também se aplica nesse nível.

## PJe/TJMG (opt-in)

`api.consultar_pje_tjmg(numero, timeout=30.0, prazo_total=60.0)` consulta processos de primeiro grau do TJMG e percorre as páginas públicas observadas de movimentos e documentos, até 100 páginas por tabela. `timeout` limita cada requisição de rede; `prazo_total` limita a operação inteira, incluindo rate limit e paginação, e aceita `None` para remover o teto total. Cada requisição recebe o menor prazo entre esses limites. O prazo é cooperativo: uma chamada HTTP já iniciada não pode ser interrompida à força, mas a biblioteca não inicia outra requisição depois do vencimento. Se o prazo termina durante a paginação, o resultado preserva os dados já recebidos e retorna `partial`. A resposta não integra o perfil padrão; seu `status` também é `partial` quando a paginação não pode ser verificada, falha durante a coleta ou excede o limite. Quando a tabela de documentos não tem paginador, a completude só é confirmada se a contagem explícita de resultados do portal coincide com as linhas renderizadas. O sucesso dessa listagem não implica que todas as peças dos autos estejam públicas. Para documentos cujo botão oficial de PDF esteja público:

- `api.ler_documento_pje_tjmg(url, max_chars=4000)` lê o PDF em memória.
- `api.obter_pdf_pje_tjmg(url, max_bytes=8 MiB)` retorna os bytes de um PDF público, com limite configurável até 128 MiB.
- `api.baixar_documento_pje_tjmg(url, destino, sobrescrever=False)` grava o PDF no destino informado.
- `api.obter_pdf_esaj(numero, cd_documento, max_bytes=8 MiB)` localiza uma peça listada pelo e-SAJ, revalida o acesso na mesma sessão e retorna os bytes até o limite configurado (máximo de 512 MiB).

Os métodos aceitam `session` e `timeout` na API funcional; `NanoJudClient` reutiliza a sessão HTTP configurada. A leitura e o download seguem a ação pública oferecida pelo portal e não contornam senha, autenticação, CAPTCHA ou sigilo. A observação de um documento público não prova acesso a todas as peças do processo.

```python
from nanojud import api

processo = "5060583-19.2021.8.13.0024"
cliente = api.create_client()
extrato = cliente.consultar_pje_tjmg(processo)
documentos = extrato["documentos"]["publicos_candidatos_unicos"]
if documentos:
    texto = cliente.ler_documento_pje_tjmg(documentos[0]["href"])
```

Reutilize o mesmo `NanoJudClient` para manter cookies de uma consulta pública até a leitura do documento. `NanoJudClient.obter_pdf_esaj(numero, cd_documento, max_bytes=...)` usa esse mesmo cliente para consultar o processo e obter somente a peça selecionada. As funções `api.consultar_pje_tjmg`, `api.ler_documento_pje_tjmg` e `api.obter_pdf_pje_tjmg` também aceitam `session`; nesse estilo, passe a mesma `requests.Session` nas chamadas.

## TJRJ 1G (opt-in)

`api.consultar_tjrj_1g(numero, timeout=30, session=None, max_paginas_movimentos=150)` consulta a SPA pública oficial seguindo a sequência observada: inicia a SPA, pesquisa pelo CNJ, seleciona a origem `tipoProcesso=1`, consulta detalhe e solicita os movimentos. Expande `movimentosExibicao` e segue `ultimaOrdemExibida` em processo volumoso, preservando ordem e identidade. O padrão limita a 150 páginas; o teto configurável é 500. Se atingir o limite, uma página falhar, o CNJ divergir ou a estrutura/cursor for inválida, retorna o que recebeu como `partial`. A origem informa `movimentacoes_paginas` e `movimentacoes_registros`. A validação live confirmou sete CNJs; o caso volumoso `0089454-81.2003.8.19.0001` retornou 1.574 eventos expandidos em 104 páginas completas. A fonte ainda não lista nem baixa documentos; a amostra não prova cobertura geral do tribunal. O limite também está disponível em `NanoJudClient.consultar_tjrj_1g` e na ferramenta MCP; `sources=("tjrj_1g",)` na extração versionada usa o padrão. Só se aplica a processos estaduais do RJ.

## TJMG 2G legado por identificador

`api.consultar_tjmg_2g_legado(numero, identificador_tjmg, timeout=30.0, session=None)` e `NanoJudClient.consultar_tjmg_2g_legado(...)` consultam as páginas oficiais de detalhe legado de segundo grau. São necessários o CNJ e o identificador interno de 17 dígitos usado por `listaProcessos`; esse ID não é derivado do CNJ e a função não integra `extract_process`. O adaptador valida CNJ e número sequencial TJMG em cada página; retorna movimentos, campos rotulados básicos e partes/advogados quando legíveis, sempre com `status="partial"`, `movimentacoes_completas=false`, `partes_completas=false` e `origem.documentos_completos=false`. Links públicos identificados na página de movimentos aparecem em `documentos.publicos_candidatos_unicos`, sem alegação de índice completo. `api.obter_documento_tjmg_2g_legado(numero, identificador_tjmg, cd_documento, ano_criacao_doc, session=None, timeout=30.0, max_bytes=8388608)` revalida a identidade e a existência do vínculo na página antes de obter o arquivo em memória; só aceita PDF, DOC e DOCX com assinatura e MIME compatíveis, não segue redirecionamento e não grava em disco. A ferramenta MCP `obter_documento_tjmg_2g_legado` retorna a peça como recurso binário com MIME real. A paginação e a completude do índice não foram comprovadas; publicações não são normalizadas.

## eproc/TJSP 1G (opt-in)

`api.consultar_eproc_tjsp_1g(numero, timeout=30, headless=False, aguardar_desafio_interativo=False)` automatiza o formulário público **Consulta Processual Unificada** do TJSP com Playwright/Chromium e retorna a capa, eventos e links públicos de documentos apresentados na página. O formulário é o destino do link público “Consulta Unificada” descrito no [manual do cidadão](https://www.tjsp.jus.br/Download/EPROC/ManuaisPublicoExterno/3.1-EPROC-CIDADAO-EXTERNO-TJSP-Consulta-Processual_26.01.2026.pdf). Se a verificação automática ficar pendente, a biblioteca agora espera até 30 segundos (ou o `timeout` configurado, se menor) antes de classificar como `AcessoRestrito`. Para abrir o Chromium visível e permitir que o operador conclua o desafio apresentado pelo portal, defina `aguardar_desafio_interativo=True` e `headless=False`; após a ação no navegador, a biblioteca retoma a espera pelo resultado até `timeout`. Ela não clica, resolve ou fabrica resposta de desafio. Só aceita a resposta se o conteúdo confirmar exatamente o CNJ consultado. O resultado só informa `movimentacoes_completas=true` quando a URL final confirma o parâmetro `eventos=true` e o limite de eventos não foi atingido; caso contrário, marca `status="partial"`. Instale `nanojud[autenticacao]` e o navegador Chromium com `python -m playwright install chromium`. O adaptador não baixa os documentos. Está disponível também como `NanoJudClient.consultar_eproc_tjsp_1g` e ferramenta MCP `consultar_eproc_tjsp_1g`, que aceita `aguardar_desafio_interativo=True`. Para extração versionada, use `sources=("eproc_tjsp_1g",)`; a fonte permanece opt-in e só se aplica a CNJs de processos estaduais de SP.

`api.consultar_eproc_tjsp_2g(numero, timeout=30, headless=False, aguardar_desafio_interativo=False)` automatiza a rota pública de Consulta Unificada de 2º grau: seleciona “Tribunal de Justiça”, escolhe EPROC na tela de roteamento e envia o CNJ ao formulário de consulta processual eproc. A fonte `eproc_tjsp_2g` pode ser solicitada explicitamente em `extract_process`, e também está disponível como `NanoJudClient.consultar_eproc_tjsp_2g` e ferramenta MCP homônima. Se a verificação automática ficar pendente, espera até 30 segundos (limitada pelo `timeout`); para deixar o Chromium visível e permitir ação do operador, use `aguardar_desafio_interativo=True` com `headless=False`. Depois a biblioteca aguarda o resultado até `timeout`, sem resolver nem fabricar resposta de desafio. O parser só aceita resposta que confirme o CNJ consultado. O número `1002476-30.2025.8.26.0224` aparece em documento público do eproc 2G, mas a consulta direta pela biblioteca ainda precisa retornar dados para validar o adaptador ponta a ponta.

## Cliente genérico MNI SOAP 3.0 e 2.2.2

`MNI3Client` executa as operações de leitura `consultarProcesso` e `consultarDocumentosProcesso` do contrato MNI 3.0 publicado pelo CNJ. O cliente recebe endpoint e credenciais explicitamente; exige HTTPS, valida TLS por padrão, não segue redirecionamentos com o corpo de credenciais, limita o tamanho da resposta e sanitiza falhas SOAP/HTTP. Configure token ou usuário/senha e, quando exigido pelo serviço, `pessoa_vinculada` com CPF/CNPJ sem pontuação. A modalidade de assinatura certificada do protocolo ainda não está implementada.

```python
from nanojud import MNI3Client, MNI3Config

cliente = MNI3Client(
    MNI3Config(
        endpoint="https://ENDPOINT-PUBLICADO-PELO-TRIBUNAL/Servico.svc",
        usuario="USUARIO_FORNECIDO_PELO_TRIBUNAL",
        senha="SENHA_FORNECIDA_PELO_TRIBUNAL",
    )
)
resposta = cliente.consultar_processo(
    "1001194-30.2024.8.26.0114",
    incluir_cabecalho=True,
    incluir_partes=True,
    incluir_movimentos=True,
    incluir_documentos=True,
)
```

As respostas de baixo nível preservam nomes e atributos MNI em dicionários Python, incluindo conteúdo binário em base64 quando o serviço o retorna. Para obter o extrato normalizado da NanoJud, use `cliente.consultar_extrato(...)`; `normalizar_resposta_processo_mni(...)` também está disponível no nível do pacote para normalizar uma resposta já desserializada. O extrato só contém metadados de documentos quando `incluir_documentos=True`; a fonte agregada `mni` não solicita esse índice por padrão. No SOAP 3.0, `consultar_documentos_processo(...)` é uma operação separada; no SOAP 2.2.2, documentos são solicitados inline com `consultarProcesso` e `incluirDocumentos=True`. As duas versões filtram IDs pedidos, mas a instalação pode retornar apenas parte. O extrato só marca movimentações como completas quando `movimentacoes_completas=True` é explicitamente informado, após confirmação do contrato da instalação. A fonte opt-in `mni` pode ser consultada por `api.extract_process(..., sources=("mni",), mni_config=config)` ou por `NanoJudClient` configurado com `NanoJudConfig(mni_config=config)`; lote, CLI e MCP também aceitam a fonte. O protocolo é geral, mas cada configuração aponta para uma instalação; não existe endpoint nacional MNI padrão. `NANOJUD_MNI_VERSION` seleciona `3.0` ou `2.2.2` no carregamento por ambiente (padrão legado: `3.0`). Para 2.2.2 configure `ENDPOINT`, `USERNAME` como `idConsultante` e `PASSWORD` como `senhaConsultante`; token MNI 3.0 não é aceito nessa versão. O TJRJ publica WSDL 2.2.2 em [`https://www12.tjrj.jus.br/MNI/Servico.svc`](https://www12.tjrj.jus.br/MNI/Servico.svc?singleWsdl); o WSDL público não concede credencial de produção. Consulte o [WSDL oficial MNI 3.0](https://www.cnj.jus.br/wp-content/uploads/conteudo/arquivo/2019/10/servico-intercomunicacao.wsdl), o [manual MNI do TJRJ](https://www.tjrj.jus.br/documents/10136/3067978/modelo-nacional-interoperabilidade.pdf) e a etapa correspondente no [roadmap](roadmap.md#plano-de-desenvolvimento-atual).

Para CLI e MCP locais, configure endpoint e credencial no ambiente do processo com `NANOJUD_MNI_ENDPOINT` e exatamente uma destas opções: `NANOJUD_MNI_TOKEN` ou `NANOJUD_MNI_USERNAME` + `NANOJUD_MNI_PASSWORD`. `NANOJUD_MNI_TRIBUNAL`, `NANOJUD_MNI_GRAU`, `NANOJUD_MNI_PESSOA_VINCULADA` e `NANOJUD_MNI_MOVIMENTACOES_COMPLETAS=true|false` são opcionais. Os valores de movimentos completos devem refletir o contrato operacional confirmado da instalação; o padrão é `false`. Sem configuração, a fonte MNI selecionada retorna erro tipado dentro do envelope, sem tentar uma URL padrão.

```python
from nanojud import MNI3Client, MNI3Config

with MNI3Client(
    MNI3Config(
        endpoint="https://ENDPOINT-FORNECIDO-PELO-TRIBUNAL/Servico.svc",
        token="TOKEN-FORNECIDO-PELO-TRIBUNAL",
    )
) as cliente:
    extrato = cliente.consultar_extrato(
        "1001194-30.2024.8.26.0114",
        tribunal="TJSP",
        grau="1G",
    )
```

```python
from nanojud import api

processo = "4000708-48.2025.8.26.0020"
extrato = api.consultar_eproc_tjsp_1g(processo)
```

Para combinar com outras fontes sem alterar o padrão global:

```python
from nanojud import api

processo = "5060583-19.2021.8.13.0024"
resultado = api.extract_process(
    processo,
    sources=("pje_tjmg", "datajud"),
    timeout=10,
    datajud_retry=1,
    prazo_total=20,
)
```

## `api.extract_process(numero, sources=("esaj", "datajud", "djen"), include_raw=False, datajud_api_key=None, djen_data_inicio="", mni_config=None)`

Extrai dados das fontes solicitadas em envelope versionado, preservando resultado, erros e timeline cronológica.

Omitir `sources` consulta as três fontes padrão. Informe uma ou mais fontes para limitar a consulta; uma sequência vazia é rejeitada com `ValueError` antes de qualquer chamada remota.
`pje_tjmg`, as fontes eproc/TJSP e `mni` são opt-in. `mni` exige `mni_config` ou as variáveis de ambiente documentadas acima.

## `api.create_client(config=None)`

Cria um `NanoJudClient` configurável para automações profissionais.

```python
from nanojud import api, NanoJudConfig

client = api.create_client(NanoJudConfig(timeout=20, rate_limit_interval=1.0, cache_enabled=True))
```

## `NanoJudClient`

Métodos principais:

- `search_processo(numero)`: retorna resumo estruturado.
- `get_extrato(numero, ...)`: retorna extrato completo.
- `get_partes(numero)`: retorna partes classificadas.
- `consultar_datajud(numero, ...)`: consulta dados processuais DataJud/CNJ.
- `consultar_djen(numero, data_inicio="")`: consulta comunicações DJEN.
- `consultar_pje_tjmg(numero)`, `ler_documento_pje_tjmg(url, ...)`, `obter_pdf_pje_tjmg(url, ...)` e `baixar_documento_pje_tjmg(url, destino, ...)`: percorre páginas públicas do PJe/TJMG (até 100 por tabela), lê, devolve bytes limitados ou grava PDFs oferecidos publicamente.
- `obter_pdf_esaj(numero, cd_documento, ...)`: obtém em bytes uma peça listada como acessível pelo e-SAJ, reconsulta movimentos na sessão do cliente e falha com `AcessoRestrito` quando o portal não libera a peça.
- `extract_process(numero, ...)`: retorna envelope de extração por fonte.
- `iter_extract_processes(numeros, ...)`: consulta iterável em fluxo, preserva ordem e isola erros por CNJ. Use `max_workers=1` por padrão; o limite global é 8.
- `extract_processes(numeros, ...)`: forma agregada para lotes que cabem em memória; retorna contagens e resultados individuais.

```python
import json
from pathlib import Path

from nanojud import api

cnjs = ["0015020-23.2010.8.26.0053"]
with Path("resultados.jsonl").open("w", encoding="utf-8") as arquivo:
    for item in api.iter_extract_processes(
        cnjs,
        sources=("datajud", "djen"),
        timeout=10,
        datajud_retry=1,
        prazo_total=20,
        max_workers=1,
    ):
        arquivo.write(json.dumps(item, ensure_ascii=False) + "\n")
```

O JSONL contém o resultado integral e pode incluir dados pessoais. Escolha um
diretório protegido e defina retenção antes de executar a consulta.

O lote usa três tentativas DataJud por processo por padrão, em alinhamento com `extract_processes` e o cliente HTTP; configure `datajud_retry` para alterar esse valor. Após falha transitória, abre um circuit breaker temporário para não repetir chamadas conhecidamente indisponíveis em todos os CNJs. Os resultados indicam fontes pausadas como `skipped`; isso não equivale a processo não encontrado. `max_workers`, `datajud_retry` e `circuit_breaker_threshold` exigem inteiros positivos (sem aceitar booleanos), com máximo de 8 trabalhadores; `circuit_breaker_cooldown` aceita número finito não negativo em segundos. `timeout` deve ficar entre 0 e 86.400 segundos (24 horas); `prazo_total` aceita valor nesse mesmo intervalo ou `None` para aguardar sem prazo total. Configurações inválidas são rejeitadas antes de consumir o iterador de CNJs. O executor compartilhado limita a 32 tarefas submetidas (8 processos × até 4 fontes); um timeout do envelope não interrompe uma chamada de rede já iniciada. Fechar o iterador do lote cancela futures ainda não iniciados e espera os ativos terminarem; essa espera pode durar até `prazo_total` por processo. `NanoJudClient` mantém uma sessão HTTP configurada e, por isso, suas consultas em lote são sequenciais.
- `baixar_pecas(extrato, destino, sobrescrever=False, limite=0)`: baixa documentos liberados para a sessão.
- `ler_pecas(extrato, limite=3, max_chars=4000)`: lê documentos liberados em memória.

## Tabelas e exportação CSV

`nanojud.exports.to_table(registros, columns=None, max_rows=None, max_chars=None)` devolve uma tabela estruturada com `row_count`, `columns`, `rows` e `csv`. As colunas e a ordem são explícitas quando `columns` é informado; sem isso, a ordem é alfabética e determinística. `to_csv` produz somente o CSV e `write_csv` grava no caminho escolhido pelo chamador. Campos estruturados permanecem intactos; textos que planilhas poderiam executar como fórmulas recebem apóstrofo somente na representação CSV.

```python
from nanojud import exports

numero = "0015020-23.2010.8.26.0053"
tabela = exports.to_table(
    [
        {"id": "evt-1", "numero_cnj": numero, "fonte": "djen", "status_fonte": "partial"},
        {"id": "evt-2", "numero_cnj": numero, "fonte": "esaj", "status_fonte": "ok"},
    ],
    columns=["id", "numero_cnj", "fonte", "status_fonte"],
)
print(tabela["csv"])
```

`max_rows` e `max_chars` rejeitam tabelas acima dos limites fornecidos; a biblioteca não trunca linhas sem informar.

## `NanoJudConfig`

Campos principais:

- `timeout`: timeout das requisições HTTP; deve ser positivo, finito e de no máximo 86.400 segundos (24 horas).
- `rate_limit_interval`: intervalo mínimo entre requisições ao mesmo host da mesma sessão; hosts diferentes permanecem independentes.
- `cache_enabled`: habilita cache JSON local.
- `cache_dir`: diretório de cache.
- `cache_ttl_seconds`: TTL inteiro não negativo; `0` mantém entradas sem expiração. Valores negativos, booleanos e frações são rejeitados.
- `salvar_html`: salva HTML bruto quando suportado pelo fluxo.
- `datajud_api_key`: override opcional da chave DataJud/CNJ para clientes configuráveis.
- `user_agent`: modelo de `User-Agent` com suporte a `{version}`.
