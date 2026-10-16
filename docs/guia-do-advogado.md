# Guia do advogado: do zero à primeira consulta

Este guia é para quem nunca usou o `nanojud` e não programa. Em cerca de 10 minutos você instala a ferramenta e consulta um processo público pelo terminal do computador.

O `nanojud` consulta, em três fontes públicas, os dados de um processo a partir do número CNJ:

| Fonte | O que traz | Cobertura |
| ----- | ---------- | --------- |
| **eSAJ** (TJSP) | Dados do processo, partes e advogados, movimentações, situação | Somente TJSP |
| **DataJud** (CNJ) | Classe, órgão julgador, assuntos e movimentações, por grau | Todos os tribunais |
| **DJEN** (CNJ) | Intimações e publicações do Diário de Justiça Eletrônico | Todos os tribunais |

Ele **só consulta dados públicos**. Não acessa processos em segredo de justiça nem protegidos por senha, e não substitui a conferência no site do tribunal antes de qualquer ato.

## 1. O que você precisa

- Um computador com Windows, macOS ou Linux e acesso à internet.
- O **Python 3.10 ou mais novo**.

### Instalar o Python no Windows

1. Abra [python.org/downloads](https://www.python.org/downloads/) e baixe a versão mais recente.
2. Execute o instalador e **marque a caixa "Add python.exe to PATH"** na primeira tela. Sem isso o terminal não encontra o Python.
3. Clique em "Install Now".

Para conferir, abra o terminal (veja abaixo) e digite `python --version`. Deve aparecer algo como `Python 3.12.4`.

### Abrir o terminal

- **Windows:** aperte a tecla Windows, digite `PowerShell` e abra o "Windows PowerShell".
- **macOS:** abra o aplicativo "Terminal".
- **Linux:** abra o "Terminal" do seu sistema.

## 2. Instalar o nanojud

No terminal, digite e aperte Enter:

```bash
python -m pip install "nanojud[pdf]"
```

O `[pdf]` inclui o leitor de PDF, necessário para ler sentenças e decisões (seção 5). Depois confira:

```bash
nanojud --versao
```

Deve aparecer `nanojud 0.5.3` (ou mais novo).

> Se o terminal disser que `nanojud` não é reconhecido, use o mesmo comando por meio do Python: `python -m nanojud --versao`. Em todos os exemplos abaixo você pode trocar `nanojud` por `python -m nanojud`.
>
> No Windows, se `python` não for reconhecido, tente `py` no lugar (`py -m pip install nanojud`).

## 3. Primeira consulta

Use o número do processo no padrão CNJ (20 dígitos). Pode digitar com ou sem pontos e traços:

```bash
nanojud consultar 0015020-23.2010.8.26.0053
```

Resultado:

```text
Processo 0015020-23.2010.8.26.0053
------------------------------------------------------------
Classe:               Mandado de Segurança Cível
Assunto:              Organização Político-administrativa / Administração Pública
Foro:                 Foro Central - Fazenda Pública/Acidentes
Vara / órgão:         7ª Vara de Fazenda Pública
Juiz:                 JULIANA BRESCANSIN DEMARCHI MOLINA
Última movimentação:  23/08/2026
                      Certidão de Não Consulta ao Teor da Informação - Contagem de Prazo do Ato -
                      Expedida
Fonte:                eSAJ/TJSP
Link:                 https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=...
```

A consulta leva de 1 a 15 segundos. O processo acima é o exemplo público usado na documentação; os dados mudam conforme o tribunal atualiza o andamento.

## 4. Tarefas do dia a dia

Troque o número pelo do seu processo.

| Eu quero... | Comando |
| ----------- | ------- |
| Ver classe, vara, situação e a última movimentação | `nanojud consultar NUMERO` |
| Ver as partes e os advogados de cada polo (TJSP) | `nanojud partes NUMERO` |
| Ver os 20 andamentos mais recentes, de todas as fontes | `nanojud linha-do-tempo NUMERO --recentes-primeiro --limite 20` |
| Ver só o que aconteceu desde uma data | `nanojud linha-do-tempo NUMERO --desde 2026-01-01` |
| Ver intimações e publicações do Diário | `nanojud djen NUMERO` |
| Ver publicações a partir de uma data | `nanojud djen NUMERO --desde 2026-01-01` |
| Consultar processo de outro tribunal (fora do TJSP) | `nanojud consultar NUMERO` ou `nanojud datajud NUMERO` |
| Salvar tudo em arquivo para guardar ou enviar | `nanojud extrato NUMERO --out extrato.json` |
| Ler o texto de uma sentença ou decisão pública | veja a seção 5 |

Todo comando aceita `--ajuda` para listar as opções, por exemplo `nanojud linha-do-tempo --ajuda`.

### Salvar o resultado

Qualquer comando aceita `--out ARQUIVO`:

```bash
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --formato texto --out andamentos.txt
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
```

O arquivo é gravado na pasta em que o terminal está aberto. O formato `texto` é para ler; o `json` guarda todos os campos e serve para planilhas, sistemas ou para entregar a uma IA.

## 5. Ler sentenças e decisões públicas

Primeiro gere o extrato com a verificação das peças, depois leia:

```bash
nanojud extrato 1002159-28.2023.8.26.0248 --inspecionar-pecas --out extrato.json
nanojud ler-pecas extrato.json --limite 2
```

O `ler-pecas` mostra o texto de até 2 peças públicas, sem salvar PDF. Se aparecer `pdf_parser_indisponivel`, instale o leitor com `python -m pip install "nanojud[pdf]"`. Peças restritas por senha não são acessadas. A leitura leva cerca de 10 segundos, porque o eSAJ exige que o processo seja reaberto antes.

Para guardar os PDFs: `nanojud baixar extrato.json --out pecas`.

## 6. Como ler o resultado

- **Fonte:** cada andamento da linha do tempo indica de onde veio: `eSAJ`, `DataJud` (com o grau, como `G1`, `G2`, `TR`) ou `DJEN`.
- **Datas:** no formato dia/mês/ano. Fontes diferentes podem registrar o mesmo ato em dias diferentes.
- **Incidente `/47`:** no DJEN, uma comunicação marcada como `incidente /47` pertence a um incidente do processo (por exemplo, requisição de pequeno valor), não ao processo principal.
- **Graus:** o DataJud guarda um registro para cada grau de jurisdição. Um processo que subiu em recurso aparece em `G1` e `G2`.
- **Diferenças entre fontes:** o `nanojud` mostra o que cada fonte informa. Quando elas divergem (por exemplo, classe diferente), o comando `extract` lista as diferenças no campo `divergencias`. Quem decide qual está certa é você, conferindo no site do tribunal.

## 7. Se algo der errado

| O que apareceu | O que significa | O que fazer |
| -------------- | --------------- | ----------- |
| `nanojud não é reconhecido` | O terminal não achou o programa | Use `python -m nanojud ...` ou reinstale o Python marcando "Add python.exe to PATH" |
| `Número CNJ deve ter 20 dígitos` | O número está incompleto ou com erro de digitação | Confira os 20 dígitos; o formato é `0000000-00.0000.0.00.0000` |
| `Dígito verificador CNJ inválido` | O número não existe com esse formato | Copie o número direto da petição ou do sistema do tribunal |
| `O eSAJ não retornou informações para este número` | O processo pode ser sigiloso, de outro sistema ou de outro tribunal | Se for de outro tribunal, use `nanojud consultar` (usa o DataJud) |
| `O processo ou documento exige senha` | Há senha ou segredo de justiça | A ferramenta só vê dados públicos; consulte no site do tribunal |
| `Falha de comunicação`, `retornou HTTP 5xx` ou demora de mais de 1 minuto | A fonte está lenta ou fora do ar (o DataJud oscila em horário de pico) | Aguarde alguns minutos e tente de novo |
| `eSAJ recusou a consulta por múltiplas consultas simultâneas` | Consultas seguidas rápidas demais | A ferramenta já espera entre consultas; aguarde alguns segundos e repita |
| Letras estranhas no lugar de acentos | Terminal antigo do Windows | Use o "Windows PowerShell" ou o "Terminal do Windows" |

## 8. Consultando vários processos

O eSAJ recusa consultas com menos de cerca de 1 segundo de intervalo, por isso a ferramenta já espera entre uma consulta e outra. Para uma carteira de processos, consulte um de cada vez, sem abrir várias janelas ao mesmo tempo, e evite horários de pico. Veja o [uso responsável](uso-responsavel.md).

## 9. Usando com uma IA (Claude Code e similares)

Se você prefere pedir em linguagem natural, o `nanojud` também funciona com agentes de IA. Veja [Instalação com IA](instalacao-com-ia.md). Mesmo assim, confira atos importantes na fonte oficial: o que a IA escreve a partir dos dados é interpretação dela, não informação do tribunal.

## Glossário

- **Número CNJ:** numeração única dos processos judiciais, com 20 dígitos (`NNNNNNN-DD.AAAA.J.TR.OOOO`).
- **eSAJ:** sistema de consulta de processos do Tribunal de Justiça de São Paulo.
- **DataJud:** base nacional de dados processuais do Conselho Nacional de Justiça.
- **DJEN:** Diário de Justiça Eletrônico Nacional, com intimações e publicações.
- **Movimentação / andamento:** cada ato registrado no processo.
- **Grau:** instância do processo. `G1` é o primeiro grau, `G2` o segundo; `TR` é turma recursal e `JE`, juizado especial.
- **Incidente:** processo derivado do principal, como cumprimento de sentença ou requisição de pequeno valor.
- **Situação:** estado do processo no eSAJ, como "Extinto" ou "Em andamento".
- **JSON:** formato de arquivo com todos os campos, lido por programas e por IA.
