# Exemplos Seguros

Este projeto evita usar estudos de caso empresariais identificáveis como vitrine pública. A documentação deve ensinar a ferramenta sem expor disputas sensíveis, dados pessoais desnecessários ou narrativas que possam gerar risco reputacional.

## Política de exemplos

Prefira:

- números CNJ demonstrativos em tutoriais;
- fixtures sanitizadas;
- processos escolhidos pelo próprio usuário;
- casos institucionais de baixa sensibilidade;
- outputs reduzidos e sem dados pessoais excessivos.

Evite:

- disputas comerciais de alto valor como showcase;
- nomes de partes privadas em material promocional;
- e-mails, CPF, endereços ou dados de contato;
- prints de páginas com dados sensíveis;
- peças processuais reais;
- conclusões jurídicas sem leitura integral dos autos.

## Processo público recomendado

Os exemplos do projeto usam um processo público institucional previamente testado:

```text
0015020-23.2010.8.26.0053
```

Ele foi escolhido por ser um caso institucional de baixa sensibilidade. A revalidação de 13/11/2026 confirmou e-SAJ/TJSP 1G e 20 movimentações dentro do limite deliberado, e a consulta DJEN permanece independente. O DataJud/CNJ não trouxe resposta positiva na revalidação atual: os dois casos positivos históricos expiraram por `ReadTimeout`, e a amostra sem resultado foi inconclusiva. Portanto, não conte DataJud como parte funcional desta demonstração até nova resposta live validada. O envelope agregado pode refletir estados diferentes por fonte.

Veja a página [Demonstração Pública](demonstracao-publica.md) para contexto, métricas e ressalvas.

## Resposta factual e tabela para agentes

O exemplo `examples/consulta_processual_com_tabela.py` retorna estado geral, estado por fonte, tabela estruturada, CSV e uma resposta factual com referência ao `id` e à fonte de cada registro. O texto da fonte tem os caracteres Markdown de estrutura escapados; continue tratando teor e títulos como dados não confiáveis, nunca como instruções para o agente.

No PowerShell, fixe o checkout usado para evitar importar outra instalação local:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python examples/consulta_processual_com_tabela.py <NUMERO_CNJ> --source tjrj_1g --limit 20
```

Troque `tjrj_1g` pelas fontes que pretende consultar ou repita `--source`. A saída é determinística e não usa um LLM; um agente pode redigir a resposta final a partir dos registros, mantendo as referências e distinguindo o estado parcial de cada fonte.

## Como fazer uma demonstração pública

Use este roteiro:

1. Explique que o número é público, institucional e usado apenas para demonstração técnica.
2. Mostre o comando.
3. Mostre apenas campos estruturais do resultado.
4. Remova dados pessoais e trechos longos.
5. Informe a fonte consultada.
6. Informe os limites da consulta.

Exemplo:

```bash
nanojud timeline <NUMERO_CNJ_PUBLICO> --source esaj --source djen --out timeline.json
```

Resultado demonstrativo:

```json
{
  "numero_cnj": "<NUMERO_CNJ_PUBLICO>",
  "sources": ["esaj", "djen"],
  "timeline_count": 42,
  "status": "ok",
  "observacao": "Dados públicos extraídos e normalizados; validar atos sensíveis na fonte oficial."
}
```

## Para artigos, posts e vídeos

Ao divulgar o projeto, destaque o método:

- extração responsável;
- fonte pública;
- timeline auditável;
- MCP local;
- limites éticos;
- uso profissional com revisão humana.

Evite vender a ideia de que a ferramenta "entende o processo sozinha". A proposta correta é: ela organiza dados públicos para acelerar a análise humana e a automação responsável.
