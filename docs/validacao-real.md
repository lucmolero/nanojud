# Validação Real

Este projeto evolui com duas camadas de validação: testes offline reproduzíveis e validações reais controladas.

## Corpus Privado

HTMLs, PDFs e saídas reais de processos são úteis para validar robustez, mas não devem ser publicados no repositório sem curadoria. Antes de transformar um caso real em fixture pública:

- remova nomes, documentos, endereços, e-mails, dados bancários e identificadores sensíveis;
- reduza o HTML ao menor trecho que reproduz o comportamento;
- preserve seletores, IDs, classes e estrutura necessários ao parser;
- troque números reais por exemplos sintaticamente válidos quando o número não for essencial;
- nunca publique peças processuais reais, mesmo quando o processo for público.

## Cenários Obrigatórios

O corpus de regressão deve cobrir:

- processo público com `popupSenha` oculto;
- processo realmente restrito, sem `numeroProcesso` público;
- processo não encontrado;
- página de lista de processos antes do detalhe;
- processo com muitas movimentações;
- movimentações carregadas sob demanda (`carregarMovimentacoesAjax.do`, paginação por cursor);
- processo com registros em mais de um grau no DataJud;
- comunicações do DJEN de incidentes (`/NN`);
- processo com muitas partes;
- execução fiscal;
- falência ou recuperação judicial;
- documentos públicos candidatos;
- documentos restritos por senha.

## Testes Ao Vivo

Testes ao vivo consultam fontes externas e podem falhar por rede, indisponibilidade, bloqueio temporário, captcha ou mudança da fonte. Por isso ficam fora do fluxo padrão.

Para rodar no PowerShell:

```bash
$env:NANOJUD_RUN_LIVE = "1"
python -m pytest -m live
```

Em Linux/macOS:

```bash
NANOJUD_RUN_LIVE=1 python -m pytest -m live
```

Use poucos processos, intervalos conservadores e nunca baixe peças em testes automatizados sem autorização explícita.

## Evidência Atual

A validação de 31 de julho de 2026 usou um corpus privado local com 32 HTMLs reais de eSAJ/TJSP. Sem publicar esses arquivos, o projeto confirmou:

- 17 processos públicos extraídos com sucesso;
- 10.310 movimentações parseadas;
- 42 partes principais;
- 2.451 partes em tabelas completas;
- 204 documentos públicos candidatos;
- 816 documentos restritos por senha.

As falhas restantes foram páginas realmente restritas ou não encontradas, que devem continuar retornando exceções controladas.
