# Guia do advogado

A NanoJud ajuda a reunir dados de um processo, conferir a origem de cada registro e identificar o que precisa de leitura nos autos. Este guia descreve a candidata 0.6.0 do repositório; a [versão publicada no PyPI](https://pypi.org/project/nanojud/) pode ter comandos diferentes até o lançamento.

## Preparar o computador

Instale Python 3.11.5 a 3.14. No Windows, confira `python --version` no PowerShell; se o comando não existir, instale o Python pelo [site oficial](https://www.python.org/downloads/) e habilite a opção de adicioná-lo ao PATH. Abra a pasta do repositório no terminal e siga o [quickstart](quickstart.md) para criar o ambiente e instalar a candidata. Ao fim, confirme a versão com `nanojud --versao`.

## Fazer a primeira consulta

```bash
nanojud consultar 0015020-23.2010.8.26.0053
```

O número acima é um exemplo público do TJSP. A saída resume o que a fonte retornou naquele momento; nomes, datas, movimentos e tempo de resposta podem mudar. Se o comando `nanojud` não for encontrado após ativar o ambiente, execute `python -m nanojud` com os mesmos argumentos.

Para ver movimentos em ordem de data e comunicações do diário:

```bash
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --recentes-primeiro --limite 20
nanojud djen 0015020-23.2010.8.26.0053
```

Uma publicação do DJEN não é a própria peça nem substitui o andamento do portal. Fontes podem usar datas ou descrições diferentes para um mesmo fato.

## Guardar o resultado

```bash
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
```

O arquivo fica na pasta atual. `extrato` consulta o e-SAJ/TJSP; para outro tribunal, veja os comandos e as fontes compatíveis na [referência da CLI](cli.md). Trate o JSON e os PDFs obtidos como dados do processo: escolha uma pasta apropriada e compartilhe apenas com quem deve recebê-los.

## Consultar peças

Um andamento pode apontar para um documento, mas isso não garante que o arquivo esteja disponível. Na consulta do e-SAJ/TJSP:

```bash
nanojud extrato 0015020-23.2010.8.26.0053 --inspecionar-pecas --out extrato.json
nanojud ler-pecas extrato.json --limite 2
```

O resultado informa quais peças foram localizadas e o estado de cada tentativa. Para documentos condicionados à identificação do advogado ou a senha processual, a integração aceita uma sessão ou credencial pelo fluxo do portal. A autorização é conferida pelo próprio tribunal. Consulte [extração](extraction.md) e [CLI](cli.md) para os modos disponíveis; não trate um PDF individual como cópia integral dos autos.

## Consultar uma carteira

Coloque um número CNJ por linha em `processos.txt` e execute:

```bash
nanojud batch processos.txt --source esaj --source djen --out resultados.jsonl
```

Cada linha de saída corresponde a um processo e preserva sucesso, falha ou resultado parcial. Revise a [matriz de cobertura](fontes.md) antes de selecionar outra fonte. Uma resposta vazia ou uma fonte indisponível não prova que o processo inexista.

## Interpretar para uma providência

Registre número CNJ, fonte, grau, data da coleta, último ato e estado de completude. Leia a peça pertinente e confira a publicação e o andamento no sistema oficial antes de calcular prazo ou recomendar uma medida. Um agente pode organizar esses dados em tabela ou resumo, desde que separe o que a fonte informou das inferências jurídicas. Veja [instalação com IA](instalacao-com-ia.md) e [uso responsável](uso-responsavel.md).
