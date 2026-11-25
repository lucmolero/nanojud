# Para advogados

A NanoJud reúne informações processuais em uma estrutura que pode ser consultada por uma pessoa, por um script Python ou por um agente conectado ao MCP local. Ela mostra a fonte de cada dado e permite verificar se a coleta ficou incompleta.

## Rotinas que a biblioteca apoia

- Consultar capa, partes e movimentações nas fontes com essa capacidade.
- Conferir comunicações publicadas no DJEN separadamente dos andamentos.
- Organizar uma linha do tempo e exportar registros para conferência ou tabela.
- Identificar peças e obter um documento individual quando a fonte e a sessão permitirem.
- Consultar uma lista de números CNJ sem perder o estado de cada processo quando uma fonte falhar.

A [matriz de fontes](fontes.md) mostra por tribunal e grau quais dessas capacidades foram observadas. Um índice de peças não garante que todos os PDFs estejam acessíveis. A situação descrita em uma movimentação também não determina, sozinha, prazo ou providência.

## Uma consulta típica

1. Confirme o número CNJ e escolha a fonte adequada ao tribunal e ao grau.
2. Faça a [primeira consulta](quickstart.md) ou peça a um agente que use o [MCP local](mcp-local.md).
3. Guarde o número, a fonte, o grau, a data da coleta e o estado de completude junto com o resultado.
4. Leia a publicação ou a peça relevante antes de concluir o que ocorreu.
5. Confira atos sensíveis diretamente no sistema do tribunal.

Para acesso que exige identificação, a biblioteca pode receber uma sessão autenticada ou a senha processual pelo fluxo disponibilizado pela fonte. A permissão efetiva é determinada pelo próprio portal e pode variar por processo e documento. Veja [guia do advogado](guia-do-advogado.md) e [extração](extraction.md).

## Trabalhar com um agente

Um pedido útil é:

```text
Consulte o processo <NÚMERO_CNJ> com a NanoJud. Informe fonte, grau, data da coleta, estado da resposta, últimos movimentos e comunicações disponíveis. Separe fatos encontrados de inferências. Indique quais peças precisam ser lidas para responder à pergunta jurídica e registre dados ausentes ou divergentes.
```

O agente pode apresentar uma tabela ou resumo, mas a origem e os limites de cada linha precisam continuar visíveis. Veja [instalação com IA](instalacao-com-ia.md) e [uso responsável](uso-responsavel.md).
