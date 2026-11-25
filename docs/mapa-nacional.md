# Mapa nacional de consulta processual

Este mapa organiza o universo de fontes antes da matriz de cobertura do produto. Ele distingue **órgão jurisdicional**, **sistema de tramitação**, **serviço de consulta**, **protocolo de integração** e **fonte nacional de dados**. Um nome de sistema usado por vários tribunais não representa uma instalação única nem prova que todos os acervos, graus ou documentos estejam acessíveis.

## Estrutura jurisdicional e roteamento

| Segmento | Órgãos e graus que precisam ser cobertos | Consequência para a NanoJud |
| --- | --- | --- |
| Justiça Estadual | 27 TJs; 1º grau em varas/juizados e 2º grau nos TJs, com turmas recursais e competências originárias | Cada UF é uma instalação lógica própria. Acervos, sistemas e migrações podem variar por grau, unidade e competência. |
| Justiça Federal | 6 TRFs e respectivas seções/subseções judiciárias; 1º grau nas unidades federais e 2º grau nos TRFs | O código de região do CNJ roteia ao TRF, mas não garante qual sistema/instalação conserva o processo nem sua completude. |
| Justiça do Trabalho | 24 TRTs e varas; TST como instância superior | TRTs e TST são fontes distintas. Movimentos de 1º/2º grau e recursos no TST exigem validação de grau e identidade. |
| Justiça Eleitoral | 27 TREs, zonas/juntas no 1º grau e TSE | TRE/TSE são fontes distintas. A competência eleitoral e a tramitação por grau não devem ser confundidas com TJs estaduais. |
| Justiça Militar da União | STM e auditorias/juízos militares federais | O STM tem alias DataJud; as unidades de 1º grau não devem ser presumidas como acesso independente pelo alias do STM. |
| Justiça Militar Estadual | TJs nos estados sem tribunal militar próprio; TJMMG, TJMRS e TJMSP onde há tribunal especializado | Os três tribunais militares estaduais têm códigos CNJ e aliases DataJud próprios; demais casos permanecem na estrutura do TJ respectivo. |
| Tribunais superiores e órgãos nacionais | STF, STJ, TST, TSE, STM; CNJ e conselhos têm competências administrativas e/ou jurisdicionais próprias | Não inferir que “tribunal superior” tenha um portal ou API comum. O catálogo público de aliases DataJud inclui STJ/TST/TSE/STM, mas não lista alias STF. |

A estrutura dos cinco segmentos, os seis TRFs, os 24 TRTs, os 27 TJs e os graus é descrita pelo [Panorama do Poder Judiciário do CNJ](https://www.cnj.jus.br/poder-judiciario/panorama-e-estrutura-do-poder-judiciario-brasileiro/). A codificação CNJ das regiões e dos três tribunais militares estaduais consta da [Resolução CNJ 65/2008, texto compilado](https://atos.cnj.jus.br/atos/detalhar/atos-normativos?documento=119).

## Famílias de sistemas e serviços

| Família ou serviço | Papel | Tratamento de produto |
| --- | --- | --- |
| PJe | Plataforma processual do CNJ, adaptada/instalada pelos tribunais | Adaptador por tribunal, instalação e grau; não assumir contrato uniforme para consulta pública, autenticação ou documentos. |
| eproc | Sistema processual adotado em diferentes ramos e tribunais | Adaptador por instalação e grau; migração e coexistência devem fazer parte do roteamento. |
| SAJ/e-SAJ | Família de sistemas e portais estaduais, com instalações específicas | “SAJ” em levantamento nacional não comprova que uma URL ou contrato cubra todos os tribunais que o utilizam. |
| Projudi | Sistema mantido pelo CNJ e implantado em instalações locais | Vincular cada integração ao tribunal, acervo e grau demonstrados. |
| Sistemas locais/legados | Exemplos observados neste projeto: DCP, eJUD, SPCv, JPe-Themis e rotas TJMG legadas | Registrar como instalações separadas; não os reduzir a um provedor genérico do tribunal. |
| Sistema Justiça (STJ) | Sistema processual informado pelo STJ no diagnóstico do CNJ | Rota STJ própria; não é sinônimo de DataJud ou de PJe. |
| SEEU | Sistema nacional especializado em execução penal, integrado a sistemas de origem | Escopo especializado; não substitui a consulta geral de conhecimento do tribunal. |
| MNI | Protocolo de interoperabilidade entre sistemas judiciais | Acesso requer endpoint, credenciais e autorização da instalação. Integração institucional não implica endpoint público nem consulta anônima. |
| DataJud | Base nacional de metadados alimentada pelos tribunais; API segmentada em aliases | Fonte nacional complementar. O catálogo público lista 91 aliases em seis grupos (STJ/TST/TSE/STM; TRF1–6; 27 TJs; 27 TREs; TRT1–24; TJMMG/TJMRS/TJMSP). STF não aparece no catálogo. Dados dependem das remessas e não equivalem a autos ou peças. |
| DJEN | Diário nacional de comunicações processuais | Fonte de publicações/comunicações. Não equivale a andamento do portal, prova de tramitação atual ou autos. |
| PDPJ-Br | Plataforma de integração/serviços digitais do Judiciário | Não é um portal único de consulta processual para substituir as instalações de origem. |
| PJeCor | Sistema de processos administrativos/correcionais | Fora da consulta geral de processos judiciais, salvo escopo futuro explicitamente definido. |
| Domicílio Judicial Eletrônico | Canal de comunicações processuais | Não é banco de andamento nem repositório geral de autos. |

O CNJ descreve o PJe como plataforma comum com adaptações por ramo e tribunais ([PJe](https://www.cnj.jus.br/processo-judicial-eletronico-pje/)); a [API Pública DataJud](https://datajud-wiki.cnj.jus.br/api-publica/endpoints/) publica aliases por tribunal; e a [Resolução CNJ 335/2020](https://atos.cnj.jus.br/atos/detalhar/3496) institui a PDPJ-Br mantendo PJe como sistema prioritário do CNJ. A relação de sistemas especiais deve ser interpretada por finalidade: por exemplo, o CNJ descreve o [SEEU](https://www.cnj.jus.br/sistemas/seeu/) como ferramenta de execução penal.

## Evidência e limites do mapa

O [Diagnóstico da Resolução CNJ 324/2020](https://bibliotecadigital.cnj.jus.br/jspui/bitstream/123456789/1092/1/Diagnostico_da_Resolucao_CNJ_324_2020_V4_2026_01_28.pdf), na seção 4.7, resume sistemas informados por 98 órgãos respondentes para a área-fim. É referência panorâmica, não inventário exaustivo e atualizado de cada instalação, grau, unidade ou migração. Há ainda uma inconsistência editorial verificável no próprio relatório: o texto declara “SAJ (5)”, mas lista TJMS, TJAC, TJAL, TJAM, TJMS novamente e TJSP — seis menções e cinco siglas únicas. Não usar essa contagem para atribuir sistema a um tribunal sem confirmação própria.

O mapa nacional define o **universo e a taxonomia**. A matriz operacional em [Fontes e cobertura](fontes.md) continua restrita a rotas e capacidades examinadas neste repositório. Só promover uma linha após evidência da instalação, grau, identidade do processo, paginação e capacidade documental pertinente. Para DataJud e DJEN, documentar indisponibilidade ou ausência sem inferir inexistência do processo.

### Fontes oficiais principais

- [Estrutura do Poder Judiciário — CNJ](https://www.cnj.jus.br/poder-judiciario/panorama-e-estrutura-do-poder-judiciario-brasileiro/)
- [Lista de tribunais — CNJ](https://www.cnj.jus.br/poder-judiciario/tribunais/)
- [Resolução CNJ 65/2008 — numeração única](https://atos.cnj.jus.br/atos/detalhar/atos-normativos?documento=119)
- [API Pública DataJud — aliases](https://datajud-wiki.cnj.jus.br/api-publica/endpoints/)
- [FAQ DataJud — valores de sistema e envio](https://www.cnj.jus.br/sistemas/datajud/perguntas-frequentes/)
- [Diagnóstico CNJ 324/2020 — sistemas informados](https://bibliotecadigital.cnj.jus.br/jspui/bitstream/123456789/1092/1/Diagnostico_da_Resolucao_CNJ_324_2020_V4_2026_01_28.pdf)
- [PJe — CNJ](https://www.cnj.jus.br/processo-judicial-eletronico-pje/)
- [Projudi — CNJ](https://www.cnj.jus.br/sistemas/projudi/)
- [SEEU — CNJ](https://www.cnj.jus.br/sistemas/seeu/)
- [PDPJ-Br — Resolução CNJ 335/2020](https://atos.cnj.jus.br/atos/detalhar/3496)
