# Demonstração pública

Use o número CNJ `0015020-23.2010.8.26.0053` para conhecer a consulta do e-SAJ/TJSP e as demais fontes que responderem no momento do teste. Trata-se de um exemplo público. Os dados e a disponibilidade podem mudar; execute os comandos antes de mostrar qualquer resultado como atual.

## Roteiro

Com a candidata 0.6.0 instalada conforme o [quickstart](quickstart.md):

```bash
nanojud consultar 0015020-23.2010.8.26.0053
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
nanojud djen 0015020-23.2010.8.26.0053
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --recentes-primeiro --limite 20
```

Anote a hora da consulta, as fontes que responderam, o grau, o estado de completude e os avisos. Se uma fonte estiver indisponível, apresente essa falha como parte do resultado. Não some movimentos e comunicações como se fossem registros equivalentes; eles podem descrever o mesmo evento.

## Demonstração com agente

```text
Consulte 0015020-23.2010.8.26.0053 com a NanoJud. Mostre uma tabela com data, tipo de registro, descrição curta, fonte e grau. Informe o estado e a hora da coleta por fonte, destaque divergências e diga quais conclusões exigem leitura das peças. Separe fatos extraídos de interpretações.
```

Uma demonstração responsável mostra como conferir o resultado no portal de origem. Evite reproduzir documentos integrais ou dados pessoais desnecessários em apresentações públicas. Consulte a [matriz de fontes](fontes.md) para entender o alcance de cada integração.
