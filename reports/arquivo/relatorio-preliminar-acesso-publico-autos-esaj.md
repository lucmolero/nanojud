# Relatório técnico preliminar: acesso público a peças no e-SAJ/TJSP

**Data da verificação:** 9 de novembro de 2026
**Escopo:** consulta pública de primeiro grau do e-SAJ/TJSP e caminho de acesso a documentos públicos pela NanoJud.
**Finalidade:** registrar evidências e limites para avaliação institucional. Este documento não afirma que todo processo ou peça seja publicamente acessível.

## Conclusão executiva

O e-SAJ expõe movimentações e permite baixar algumas peças quando a própria consulta pública as apresenta como documentos públicos. Isso **não equivale a acesso público à íntegra de todos os autos**. No processo usado para a verificação, 33 documentos foram classificados pelo portal como restritos por senha; a biblioteca corretamente não tenta abri-los. A petição inicial não foi confirmada entre as peças públicas verificadas.

A NanoJud demonstrou o caminho de download de um PDF público em uma consulta real. Não foi feita uma descarga integral das 43 peças públicas candidatas; portanto, ainda não há evidência de que todas sejam baixáveis, legíveis ou completas. Um único processo também não permite generalizar o comportamento para todos os processos do TJSP.

## Processo e método

Foi usado o número CNJ indicado pelo solicitante: `1076539-20.2019.8.26.0100`. A consulta foi feita sem login, senha, CAPTCHA, cookies fornecidos por usuário ou tentativa de acessar documento restrito.

Verificações realizadas:

1. Consulta eSAJ pela NanoJud, com paginação completa das movimentações (`limite_movimentacoes=0`).
2. Contagem de documentos distintos por classificação de acesso exposta pelo portal.
3. Inspeção da tabela pública “Petições diversas” e da peça vinculada ao movimento de recebimento da petição inicial.
4. Leitura em memória e download temporário de PDFs marcados como públicos, sem conservar os arquivos de teste.
5. Leitura do código-fonte do adaptador e dos testes de parser, sessão, download e extração de texto da biblioteca.
6. Inspeção controlada via REA do fluxo público do e-SAJ e da tela oficial de identificação, sem inserir nem enviar credenciais.

O [processo no e-SAJ](https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=2S0013LMM0000&processo.foro=100&processo.numero=1076539-20.2019.8.26.0100) é a fonte primária para repetir a conferência. Os totais abaixo são uma captura pontual; o portal pode mudar com novos andamentos.

## Resultados observados

| Item | Resultado | Interpretação |
| --- | ---: | --- |
| Movimentações com paginação sem limite | 342 | A listagem completa de movimentações foi recuperada neste teste. |
| Documentos distintos vinculados a movimentações | 76 | Não significa que todos sejam públicos ou baixáveis. |
| Candidatos públicos | 43 | O portal disponibilizou links que a NanoJud classifica para tentativa de acesso público. |
| Marcados como restritos por senha | 33 | Não foram abertos nem contornados. |
| Peças públicas testadas por leitura/download | 2 | Ambos os caminhos funcionaram em uma amostra pequena. |

Com o limite padrão de 100 movimentações, a mesma consulta retornou somente 13 candidatos públicos e 6 restritos. Para enumerar o histórico deste processo e encontrar peças mais antigas, é necessário usar `limite_movimentacoes=0`.

### Petição inicial

O movimento “Recebida a Petição Inicial” tinha um documento vinculado publicamente acessível. A NanoJud abriu o visualizador e extraiu texto do PDF em memória, mas os metadados fornecidos pelo próprio e-SAJ indicavam `fl_peticao_inicial=false`. Portanto, esse arquivo **não foi confirmado como a petição inicial**. A tabela “Petições diversas” mostrou protocolos e descrições, mas nenhuma linha dessa tabela continha link de documento na página pública examinada.

Resultado: **não localizamos evidência suficiente de uma rota pública para obter a petição inicial deste processo**. Isso não prova que a inicial esteja indisponível em todos os processos ou por todas as formas oficiais de acesso; exige investigação adicional no portal e, se aplicável, confirmação institucional autorizada.

### Identificação e acesso autorizado

Ao acionar “Visualizar autos” na consulta pública, a página oferece a ação “Identificar-se” e um campo de senha do processo. O texto do portal distingue o advogado vinculado ao processo (que deve se identificar) da parte/interessado que informa a senha do processo; também orienta a parte sem senha a solicitá-la ao cartório. A captura DOM mostrou o formulário de senha, mas o clique apenas alterou o fragmento da URL e não abriu o formulário oculto naquele estado. Portanto, registramos o fluxo e os campos presentes, sem afirmar que a tentativa de autenticação foi concluída.

A rota oficial de identificação, acessada com o parâmetro `redirect_uri` fornecido pelo portal, apresentou opções de CPF/CNPJ e senha e de certificado digital. Também havia interface de código de verificação e cadastro. A rota sem `redirect_uri` respondeu “redirectURI not informed”; isso é comportamento esperado da rota e não evidência de indisponibilidade do login. Não foram enviados CPF, senha, OAB, certificado, token ou código de verificação. A página observada não demonstra que informar apenas um número OAB seja suficiente; o e-SAJ precisa validar a identidade e o vínculo/autorização no próprio sistema.

**Conclusão prática:** não identificamos uma rota pública para contornar senha ou sigilo. O fluxo oficial exige que o e-SAJ autentique a identidade e verifique sua permissão no processo. A NanoJud agora oferece login assistido no navegador oficial (CPF/CNPJ, senha, código adicional ou certificado conforme as opções apresentadas pelo portal), preserva os cookies apenas em memória, aceita sessão oficial externa e envia a senha processual ao formulário oficial para cada recurso restrito. Só marca a peça liberada quando o portal passa a expor um link de documento utilizável. O protocolo de autenticação ainda precisa de validação com conta autorizada do TJSP, e certificado com integração nativa/extensão pode exigir configuração específica no navegador escolhido. O número OAB isolado nunca é tratado como credencial.

## Rota pública observada

No fluxo coberto pelo adaptador, o acesso ocorre assim:

1. Abrir a consulta pública do processo em `cpopg/show.do`.
2. Percorrer `carregarMovimentacoesAjax.do` com o cursor de paginação, preservando a mesma sessão HTTP.
3. Selecionar links de movimentação que o portal expõe como documentos públicos.
4. Abrir o visualizador em `pastadigital` e ler o `requestScope` que descreve formato, páginas e parâmetros de visualização.
5. Obter o PDF por `getPDF.do` usando a sessão e os parâmetros efêmeros obtidos na própria navegação.

Os parâmetros da pasta digital são vinculados à sessão e podem expirar. A NanoJud reabre o processo e prepara uma sessão para acessar os documentos; não depende de reutilizar um ticket antigo exportado em JSON. A biblioteca grava o PDF por fluxo para arquivo temporário, valida o cabeçalho `%PDF-` e só então publica o arquivo de destino. Também consegue extrair texto de PDF em memória quando o parser opcional está instalado.

## Acesso autenticado adicionado à biblioteca

A descoberta ao vivo confirmou que os documentos marcados como restritos ainda têm `cd_documento`, sequência de movimentação e um identificador de recurso como `linkMovVincProc-<id>`. O JavaScript público do e-SAJ usa esse identificador ao abrir o formulário da senha. A NanoJud preserva agora esse identificador, submete a senha ao formulário oficial com o token CSRF da sessão e recarrega as movimentações. Uma peça só migra para a lista de download/leitura quando o portal apresenta um link de documento utilizável.

Foram adicionados três meios para operar com a identidade autorizada: (1) login oficial assistido num navegador local, com cookies mantidos somente em memória; (2) sessão HTTP já autenticada fornecida pelo host Python; e (3) senha processual obtida por prompt oculto na CLI, argumento Python ou provedor seguro de credenciais no MCP embutido. A OAB isolada não é usada como senha. O MCP padrão não recebe credenciais em argumentos: o host injeta a sessão e o provedor de senha.

A etapa de senha e a extração do identificador do recurso passaram por testes simulados; a extração real confirmou IDs de recurso nas peças restritas do processo deste relatório. Não foi realizado login com identidade ou senha real autorizada, então a aceitação de credenciais, liberação de cada documento e download autenticado permanecem pendentes de validação assistida.

Na prova de download via API da biblioteca, um PDF público foi gravado em diretório temporário: **28.044 bytes**, status `baixado`, cabeçalho PDF válido. Na prova separada de leitura, outro documento público retornou `texto_extraido`; a leitura foi limitada a 400 caracteres para manter o teste pequeno.

## Como repetir pela biblioteca

Para enumerar todas as movimentações antes de procurar peças antigas:

```python
from nanojud.api import get_extrato

extrato = get_extrato(
    "1076539-20.2019.8.26.0100",
    limite_movimentacoes=0,
)
documentos = extrato["documentos"]
publicos = documentos["publicos_candidatos_unicos"]
restritos = documentos["restritos_por_senha_unicos"]
```

Para baixar todos os **candidatos públicos identificados** desse extrato, forneça um diretório e limite zero. Faça isso de modo controlado: os arquivos podem ser grandes e a classificação do portal não garante que toda tentativa terminará com sucesso.

```python
from pathlib import Path
from nanojud.api import baixar_pecas

baixados = baixar_pecas(extrato, Path("autos_publicos"), limite=0)
```

O comando de autos em lote também deve ser executado com ambos os limites zerados para buscar o histórico completo e tentar todas as peças públicas candidatas:

```bash
nanojud autos processos.txt --out-dir autos --max-documentos 0 --limite-movimentacoes 0 --out manifesto.jsonl
```

O manifesto deve ser revisado: erro de sessão, documento não PDF, tamanho acima do limite e falha de leitura são estados diferentes de sucesso. Não interprete a contagem de movimentações como contagem de documentos obtidos.

## Limites e lacunas

- `publico_candidato` significa que o portal apresentou um link público candidato; o resultado só é confirmado depois de obter e validar o PDF.
- Documentos com senha, sigilo, CAPTCHA ou bloqueio permanecem inacessíveis pela rota pública. A afiliação institucional do projeto não substitui a autorização específica do usuário ou da instituição.
- A rota observada depende de sessão HTTP, e sua estabilidade precisa ser monitorada por testes de integração periódicos.
- Nesta amostra, a identificação da petição inicial não foi resolvida. A NanoJud deve preservar `fl_peticao_inicial` como metadado quando disponível e apresentar `não identificado` quando não houver confirmação, sem inferir pelo título da movimentação.
- O teste real de download cobriu um documento, não os 43 candidatos. Cobertura integral exige uma execução controlada por documento, com orçamento total de bytes, pausa entre requisições, manifesto de falhas e deduplicação.
- A captura REA foi executada em navegador iniciado pelo próprio REA e finalizada com encerramento do processo controlado (`terminated-owned-process`). Evidências: `ev_8da43a7c63e43ce1d58d392591f8cf131cb2ec018ce9e8e08577ca576466cc5f` (consulta pública); `ev_b82e419e305510d43eda5a099b591fe448d2bbbadb9d2c7d9cd5ce1337bf0d1e` (ação “Visualizar autos” e formulário de senha); `ev_80ec6e37045603043d01c44b3fb575d16181a61c4fe9f34d2fc3a76d841abd03` (tela de identificação). A captura da tela de identificação foi apenas leitura da interface, sem envio de credenciais. Um cenário inicial sem parâmetro de retorno confirmou a mensagem “redirectURI not informed” (`ev_7d6e4df74c36b05a4e5053055f5dec30693e6c53c92b68f59d34098b45ded951`). As capturas são instantâneos e não substituem validação com advogado autorizado.

## Próximos passos para uma validação institucional

1. Validar o fluxo autenticado em ambiente e processo autorizados, com advogado responsável operando o login oficial; não coletar credenciais em logs ou no chat.
2. Fazer uma execução controlada sobre a lista de candidatos públicos, com limite agregado de bytes e registro por documento de metadados, páginas, resultado HTTP, validade do PDF e extração de texto.
3. Verificar em processos de teste adequados se o portal disponibiliza a petição inicial por algum link público distinto; manter o resultado como não confirmado até obter o arquivo e seu metadado `fl_peticao_inicial`.
4. Executar validação assistida com advogado autorizado para confirmar login, senha processual, recuperação de links e download de peças liberadas; documentar separadamente CPF/senha, certificado, MFA e limites que o próprio TJSP aplicar.
5. Ajustar a API e o manifesto para distinguir: histórico completo, candidatos enumerados, peças obtidas, peças restritas, falhas, peças sem texto e cobertura desconhecida.

## Parecer técnico

**A NanoJud consulta o histórico e pode obter peças pela sessão autenticada ou senha processual que o TJSP aceitar. Neste processo, 33 documentos apareceram como restritos na consulta pública e a petição inicial não foi identificada. A implementação do fluxo de credenciais está pronta para validação técnica, mas a liberação de documentos protegidos ainda não foi testada com credencial autorizada. O objetivo técnico permanece amplo: cobrir todas as peças que a identidade autorizada consiga obter por mecanismos oficiais, com estado de acesso auditável por documento.
