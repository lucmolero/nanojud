<p align="center">
  <img
    src="https://raw.githubusercontent.com/lucmolero/nanojud/main/docs/assets/nanojud-logo-primary.svg"
    alt="NanoJud"
    width="420"
  />
</p>

<h1 align="center">NanoJud</h1>

<p align="center">
  <strong>Dados judiciais públicos, estruturados e rastreáveis.</strong>
</p>

<p align="center">
  Consulte e organize informações públicas do eSAJ/TJSP, DataJud/CNJ e DJEN usando Python, linha de comando ou agentes de IA compatíveis com MCP.
</p>

<p align="center">
  <a href="https://github.com/lucmolero/nanojud/actions/workflows/ci.yml">
    <img src="https://github.com/lucmolero/nanojud/actions/workflows/ci.yml/badge.svg" alt="CI" />
  </a>
  <a href="https://github.com/lucmolero/nanojud/actions/workflows/docs.yml">
    <img src="https://github.com/lucmolero/nanojud/actions/workflows/docs.yml/badge.svg" alt="Docs" />
  </a>
  <a href="https://github.com/lucmolero/nanojud/actions/workflows/codeql.yml">
    <img src="https://github.com/lucmolero/nanojud/actions/workflows/codeql.yml/badge.svg" alt="CodeQL" />
  </a>
  <a href="https://github.com/lucmolero/nanojud/releases">
    <img src="https://img.shields.io/github/v/release/lucmolero/nanojud" alt="Release" />
  </a>
  <a href="https://pypi.org/project/nanojud/">
    <img src="https://img.shields.io/pypi/v/nanojud.svg" alt="PyPI" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" />
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" />
  </a>
</p>

<p align="center">
  <a href="#comece-aqui">Comece aqui</a>
  ·
  <a href="https://lucmolero.github.io/nanojud/">Documentação</a>
  ·
  <a href="#uso-com-agentes-de-ia">Uso com IA</a>
  ·
  <a href="#uso-responsável">Uso responsável</a>
  ·
  <a href="https://github.com/lucmolero/nanojud/releases">Releases</a>
</p>

---

> [!IMPORTANT]
> **Status: beta público.**
>
> O projeto já oferece API Python, CLI, cliente configurável e servidor MCP local, mas continua em evolução. As fontes judiciais consultadas são externas e podem alterar páginas, contratos, disponibilidade ou limites sem aviso.
>
> Confirme informações relevantes nos sistemas oficiais antes de utilizá-las em atividades profissionais.

> [!NOTE]
> Este é um projeto independente. Não é um produto oficial do TJSP, CNJ, eSAJ ou DataJud.
>
> A biblioteca não contorna autenticação, senha, captcha, segredo de justiça ou restrições técnicas das fontes consultadas.

## Primeiros passos em 2 minutos

Advogado(a) e não programa? Siga o **[Guia do advogado](docs/guia-do-advogado.md)**, com instalação passo a passo no Windows, tarefas do dia a dia e solução de problemas. Em resumo, com o Python 3.10 ou mais novo instalado:

```bash
python -m pip install "nanojud[pdf]"
nanojud consultar 0015020-23.2010.8.26.0053
```

```text
Processo 0015020-23.2010.8.26.0053
------------------------------------------------------------
Classe:               Mandado de Segurança Cível
Vara / órgão:         7ª Vara de Fazenda Pública
Última movimentação:  23/08/2026
                      Certidão de Não Consulta ao Teor da Informação - Contagem de Prazo do Ato
Fonte:                eSAJ/TJSP
```

Outros comandos: `partes`, `linha-do-tempo`, `djen`, `datajud` e `extrato`. Use `nanojud --ajuda` para ver todos.

## Visão geral

O `nanojud` é uma camada local e auditável para consultar, estruturar e organizar dados judiciais públicos.

O projeto transforma informações dispersas em resultados adequados para:

* consultas jurídicas assistidas;
* linhas do tempo processuais;
* relatórios internos;
* automações locais;
* scripts e notebooks;
* integrações com sistemas;
* agentes de IA compatíveis com MCP;
* exportações estruturadas para análise.

A proposta é permitir que profissionais do Direito e equipes técnicas utilizem fontes públicas judiciais sem perder a origem, o contexto e os limites de cada informação.

## Fontes integradas

| Fonte           | Conteúdo consultado                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------------------- |
| **eSAJ/TJSP**   | Dados básicos, partes, movimentações, audiências, petições, incidentes, apensos e documentos públicos candidatos |
| **DataJud/CNJ** | Dados processuais estruturados e normalizados                                                                    |
| **DJEN**        | Comunicações e publicações judiciais                                                                             |

A disponibilidade e a cobertura dependem das informações publicadas por cada fonte.

## Principais recursos

### Para profissionais do Direito

* Consulta de processos públicos por número CNJ.
* Organização de dados básicos e movimentações.
* Construção de timelines cronológicas.
* Consolidação de informações provenientes de fontes diferentes.
* Identificação da origem de cada conjunto de dados.
* Exportação de resultados para arquivos estruturados.
* Uso por meio de agentes de IA locais.

### Para integrações e automações

* API Python de alto nível.
* Cliente configurável para rotinas profissionais.
* Interface de linha de comando.
* Servidor MCP local por `stdio`.
* Exportação para JSON, JSONL, CSV e SQLite.
* Timeout, retry, backoff e rate limit.
* Cache local opcional.
* Logging e sessões HTTP injetáveis.
* Contratos tipados e exceções públicas.

### Para segurança e qualidade

* Testes automatizados sem rede com fixtures sanitizadas.
* Testes opcionais contra fontes reais.
* Compatibilidade com Python 3.10, 3.11, 3.12 e 3.13.
* Cobertura mínima de testes exigida pelo CI.
* CodeQL, `pip-audit`, lint, type check e validação de pacote.
* Pacote marcado como tipado com `py.typed`.
* Documentação de LGPD, governança, ameaças e uso responsável.

---

# Comece aqui

Escolha o caminho mais adequado ao seu perfil.

| Perfil                                            | Caminho recomendado                               |
| ------------------------------------------------- | ------------------------------------------------- |
| Advogado usando Claude Code ou outro agente local | [Uso com agentes de IA](#uso-com-agentes-de-ia)   |
| Usuário sem Git                                   | [Baixar o projeto como ZIP](#baixar-sem-usar-git) |
| Desenvolvedor Python                              | [Instalação técnica](#instalação-técnica)         |
| Usuário de terminal                               | [Uso pela CLI](#uso-pela-cli)                     |
| Usuário de MCP                                    | [Servidor MCP local](#servidor-mcp-local)         |
| Contribuidor                                      | [Desenvolvimento](#desenvolvimento)               |

---

# Uso com agentes de IA

O projeto pode ser preparado e utilizado por agentes que tenham acesso à pasta local e ao terminal do computador, como Claude Code e outros agentes de desenvolvimento.

Você não precisa conhecer Git, Python ou os comandos internos do projeto para seguir esse caminho.

> [!WARNING]
> Uma IA utilizada apenas pelo navegador, sem acesso aos arquivos e ao terminal do seu computador, não conseguirá instalar ou executar o projeto localmente.

## Baixar sem usar Git

1. Abra a página do repositório no GitHub.
2. Clique em **Code**.
3. Clique em **Download ZIP**.
4. Extraia o arquivo para uma pasta do computador.
5. Abra essa pasta no Claude Code ou em outro agente local.
6. Envie ao agente a instrução abaixo.

## Instrução para preparar o projeto

Copie e cole esta mensagem no agente:

```text
Prepare este projeto para uso jurídico local.

Leia primeiro o README.md e entenda a estrutura do projeto.

Identifique meu sistema operacional e prepare o ambiente automaticamente.

Crie um ambiente virtual isolado, atualize o pip, instale o projeto com os recursos de CLI e MCP e valide se a instalação está funcionando.

Use o Python do ambiente virtual e não instale dependências globalmente quando isso puder ser evitado.

Não altere o código-fonte durante a instalação.

Se este agente aceitar servidores MCP, configure o servidor MCP local usando o ambiente virtual do projeto. Se não aceitar, mantenha a CLI disponível e explique de forma simples como utilizá-la.

Não tente acessar processos sigilosos, contornar autenticação, senha, captcha ou qualquer restrição técnica. Não solicite credenciais judiciais.

Ao terminar, informe:

1. se a instalação foi concluída;
2. se a biblioteca foi importada corretamente;
3. se a CLI está funcionando;
4. se o MCP foi configurado;
5. quais fontes estão disponíveis;
6. como abrir e usar o projeto novamente;
7. e qual é o próximo passo para consultar um processo público.
```

O agente deverá executar as etapas necessárias e apresentar apenas as decisões que realmente dependam de você.

## Resultado esperado

Ao final da preparação, o agente deverá apresentar um resumo semelhante a este:

```text
Preparação concluída.

- Biblioteca instalada: sim
- CLI disponível: sim
- MCP configurado: sim ou não
- Ambiente utilizado: .venv
- Código-fonte alterado: não

Agora envie o número CNJ público do processo que deseja consultar.
```

## Consultar um processo com o agente

Depois da instalação, envie uma instrução como:

```text
Consulte o processo público de número:

0015020-23.2010.8.26.0053

Apresente:

- os dados básicos;
- a última movimentação;
- uma linha do tempo em ordem cronológica;
- as informações encontradas no eSAJ, DataJud e DJEN;
- eventuais diferenças entre as fontes;
- a data e a origem de cada informação relevante.

Separe claramente:

1. dados obtidos diretamente das fontes;
2. dados normalizados pelo projeto;
3. explicações ou inferências produzidas pela IA.

Não trate análises produzidas pela IA como informações oficiais do tribunal.
```

Substitua o número utilizado no exemplo pelo número CNJ público que deseja consultar.

## Outros pedidos úteis

```text
Resuma as movimentações mais importantes deste processo.
```

```text
Mostre apenas as movimentações dos últimos 90 dias.
```

```text
Compare os dados encontrados no eSAJ, DataJud e DJEN.
```

```text
Gere uma linha do tempo objetiva com data, evento e fonte.
```

```text
Exporte os dados públicos deste processo para JSON.
```

```text
Identifique divergências ou informações ausentes entre as fontes.
```

---

# Demonstração pública

Para demonstrações, tutoriais e testes manuais, o projeto utiliza o seguinte processo público:

```text
0015020-23.2010.8.26.0053
```

Trata-se de um Mandado de Segurança Cível envolvendo sindicato e Administração Pública estadual.

Em uma validação manual realizada em 31 de julho de 2026, o projeto obteve dados do eSAJ/TJSP, DataJud/CNJ e DJEN e gerou uma timeline agregada sem falhas registradas naquela execução.

O eSAJ passou a carregar as movimentações sob demanda depois dessa validação, e a lib foi ajustada em outubro de 2026. Neste processo, o DataJud indexa apenas o registro de um incidente (Requisição de Pequeno Valor) sob o mesmo número, e por isso `divergencias` no envelope aponta diferenças de classe, distribuição e última movimentação em relação ao eSAJ. Isso vem das fontes, não da lib.

Os resultados podem mudar, pois dependem de fontes externas atualizadas continuamente.

Consulte a demonstração completa em:

* [Demonstração pública](docs/demonstracao-publica.md)
* [Exemplos seguros](docs/exemplos-seguros.md)

---

# Instalação

## Requisitos

* Python 3.10 ou superior.
* Acesso à internet para instalação e consultas.
* Terminal ou agente local com acesso ao terminal.

## Instalar pelo PyPI

Para usar a biblioteca, CLI e consultas principais:

```bash
python -m pip install nanojud
```

Para instalar tambem o servidor MCP local e leitura de PDFs publicos em memoria:

```bash
python -m pip install "nanojud[mcp]"
```

Depois valide:

```bash
python -c "import nanojud; print(nanojud.__version__)"
nanojud --help
```

## MCP direto com uvx

Para clientes MCP que aceitam comando externo, a forma mais simples e nao manter projeto clonado:

```bash
uvx --from "nanojud[mcp]" nanojud-mcp
```

Exemplo de configuracao MCP:

```json
{
  "mcpServers": {
    "nanojud": {
      "command": "uvx",
      "args": ["--from", "nanojud[mcp]", "nanojud-mcp"]
    }
  }
}
```

## Desenvolvimento local

Use este caminho apenas se voce quer contribuir, rodar testes ou alterar o codigo.

```bash
git clone https://github.com/lucmolero/nanojud.git
cd nanojud
```

Tambem e possivel baixar o projeto por **Code -> Download ZIP**.

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mcp]"
```

## Linux ou macOS

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mcp]"
```

## Validar a instalação

```bash
python -c "import nanojud; print('nanojud instalado com sucesso')"
```

```bash
nanojud --help
```

Também é possível executar a CLI pelo módulo:

```bash
python -m nanojud.cli --help
```

---

# Uso pela CLI

A CLI fala português e, no terminal, mostra o resultado em texto legível. Ao redirecionar a saída ou usar `--out`, gera JSON.

```bash
# resumo: classe, vara, situação e última movimentação
nanojud consultar 0015020-23.2010.8.26.0053

# partes e advogados por polo (TJSP)
nanojud partes 0015020-23.2010.8.26.0053

# os 20 andamentos mais recentes, de todas as fontes
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --recentes-primeiro --limite 20

# novidades desde uma data
nanojud linha-do-tempo 0015020-23.2010.8.26.0053 --desde 2026-08-01

# intimações e publicações do DJEN
nanojud djen 0015020-23.2010.8.26.0053 --desde 2026-01-01

# qualquer tribunal, pelo DataJud
nanojud datajud 0032991-06.2012.8.19.0066 --out datajud.json

# extrato completo, para guardar ou entregar a uma IA
nanojud extrato 0015020-23.2010.8.26.0053 --out extrato.json
```

Se o terminal não reconhecer `nanojud`, use `python -m nanojud`. Consulte o [Guia da CLI](docs/cli.md) e o [Guia do advogado](docs/guia-do-advogado.md).

---

# Uso rápido em Python

```python
from nanojud import api

numero = "0015020-23.2010.8.26.0053"

resumo = api.search_processo(numero)
print(resumo["classe"])

extrato = api.get_extrato(numero)
print(extrato["dados_basicos"])

comunicacoes = api.consultar_djen(numero)
print(len(comunicacoes))

datajud = api.consultar_datajud(numero)
print(datajud["classe"])
```

A API pública do DataJud/CNJ utiliza uma chave pública documentada pelo próprio CNJ.

A biblioteca inclui a chave vigente como fallback. Caso o CNJ altere essa chave, defina `NANOJUD_DATAJUD_API_KEY` ou informe `api_key` explicitamente. Também há compatibilidade com `DATAJUD_API_KEY` e `CNJ_DATAJUD_API_KEY`.

---

# Cliente configurável

Para automações, jobs e integrações profissionais, use o cliente configurável:

```python
from nanojud import NanoJudClient, NanoJudConfig

client = NanoJudClient(
    NanoJudConfig(
        timeout=20,
        rate_limit_interval=1.0,
        cache_enabled=True,
        cache_ttl_seconds=6 * 60 * 60,
    )
)

resumo = client.search_processo(
    "0015020-23.2010.8.26.0053"
)

print(resumo["classe"])
```

Consulte:

* [Cliente configurável](docs/client.md)
* [API Reference](docs/api-reference.md)
* [Contratos de dados](docs/contracts.md)
* [Tratamento de erros](docs/errors.md)

---

# Servidor MCP local

O projeto inclui um servidor MCP local opcional por `stdio`.

Ele permite que agentes e clientes compatíveis consultem e estruturem dados judiciais sem a necessidade de expor um endpoint público.

## Instalação

```bash
python -m pip install "nanojud[mcp]"
```

## Execução direta

```bash
nanojud-mcp
```

Ou:

```bash
python -m nanojud.mcp_server
```

> [!NOTE]
> Executar o servidor e configurá-lo em um cliente MCP são etapas diferentes.
>
> O cliente deve registrar o comando do servidor e, preferencialmente, utilizar o executável Python localizado dentro do ambiente virtual `.venv`.

As ferramentas MCP disponíveis incluem:

* validação de números CNJ;
* extração de números CNJ contidos em textos;
* consulta ao eSAJ/TJSP;
* consulta ao DataJud/CNJ;
* consulta ao DJEN;
* geração de envelopes versionados;
* criação de timelines cronológicas;
* leitura em memória de documentos públicos candidatos, quando tecnicamente possível.

## Documentos públicos

A ferramenta de leitura de documentos não salva PDFs em disco.

Quando a fonte fornece um PDF público, os bytes podem ser processados em memória e o texto extraído com `pypdf`.

Continuam fora do escopo:

* documentos protegidos por senha;
* documentos dependentes de captcha;
* processos sigilosos;
* conteúdo sujeito a autenticação;
* materiais com restrição de acesso.

Consulte:

* [MCP local](docs/mcp-local.md)
* [Aprendizados MCP](docs/aprendizados-mcp.md)

---

# Exemplo de saída

```json
{
  "numero": "0015020-23.2010.8.26.0053",
  "classe": "Mandado de Segurança Cível",
  "assunto": "Organização Político-administrativa / Administração Pública",
  "foro": "Foro Central - Fazenda Pública/Acidentes",
  "vara": "7ª Vara de Fazenda Pública",
  "ultima_movimentacao": "Extinta a Execução/Cumprimento da Sentença pela Satisfação da Obrigação",
  "ultima_data": "2026-07-19",
  "url": "https://esaj.tjsp.jus.br/cpopg/...",
  "status": "ok",
  "mensagem": "Processo consultado com sucesso"
}
```

> [!CAUTION]
> Em demonstrações públicas, reduza os resultados e sanitize nomes, documentos, dados pessoais e trechos extensos.
>
> Para trabalhos profissionais, consulte apenas processos escolhidos legitimamente pelo próprio usuário e confirme informações relevantes nas fontes oficiais.

---

# Arquitetura

O fluxo principal do projeto é:

```text
eSAJ/TJSP ─┐
DataJud/CNJ ├──> clientes e parsers ──> normalização ──> API / CLI / MCP
DJEN ──────┘                                  │
                                              └──> JSON / JSONL / CSV / SQLite
```

Principais módulos:

| Módulo                    | Responsabilidade                        |
| ------------------------- | --------------------------------------- |
| `nanojud.api`        | API pública de alto nível               |
| `nanojud.client`     | Cliente configurável                    |
| `nanojud.config`     | Timeout, cache, rate limit e User-Agent |
| `nanojud.cache`      | Cache local JSON opcional               |
| `nanojud.esaj`       | Consulta e parsing do eSAJ/TJSP         |
| `nanojud.datajud`    | Cliente DataJud/CNJ                     |
| `nanojud.djen`       | Cliente de comunicações do DJEN         |
| `nanojud.extraction` | Envelopes versionados de extração       |
| `nanojud.timeline`   | Timeline cronológica                    |
| `nanojud.exports`    | Exportadores estruturados               |
| `nanojud.mcp_server` | Servidor MCP local                      |
| `nanojud.cli`        | Interface de linha de comando           |
| `nanojud.utils`      | Normalização e funções auxiliares       |

Consulte a documentação completa:

* [Arquitetura](docs/architecture.md)
* [Metodologia](docs/metodologia.md)
* [Reprodutibilidade](docs/reprodutibilidade.md)

---

# Qualidade e confiabilidade

O projeto utiliza práticas de engenharia voltadas a previsibilidade, manutenção e auditoria.

## Controles automatizados

* CI em Python 3.10, 3.11, 3.12 e 3.13.
* Gate mínimo de cobertura de testes de 90%.
* CodeQL.
* Auditoria de dependências.
* Lint e formatação.
* Checagem de tipos com `mypy`.
* Build e validação de pacote.
* Testes sem rede com fixtures sanitizadas.
* Testes ao vivo opcionais, separados do CI.
* Releases versionadas com `wheel`, `sdist` e notas públicas.

## Validação com cenários reais

O projeto também é validado em um corpus interno não publicado, utilizado para ampliar a cobertura de layouts e cenários reais sem expor HTMLs, PDFs, peças processuais ou estudos empresariais identificáveis.

Na validação mais recente, esse corpus continha:

* 17 processos públicos;
* 32 HTMLs reais;
* 10.310 movimentações parseadas;
* 42 partes principais;
* 2.451 partes em tabelas completas;
* 204 documentos públicos candidatos;
* 816 documentos identificados como restritos por senha.

Os documentos restritos foram identificados como indisponíveis. Seu conteúdo não integra o escopo público da biblioteca.

Consulte:

* [Validação real](docs/validacao-real.md)
* [Fixtures](docs/fixtures.md)
* [Modelo de ameaças](docs/threat-model.md)
* [Segurança](SECURITY.md)

---

# Limitações conhecidas

O projeto depende de fontes externas e, por isso, não pode garantir:

* disponibilidade contínua dos portais;
* estabilidade permanente do HTML;
* presença das mesmas informações em todas as fontes;
* cobertura idêntica entre tribunais;
* atualização simultânea dos dados;
* acesso a documentos protegidos ou sigilosos;
* validade jurídica de análises produzidas por agentes de IA.

Resultados incompletos ou divergentes devem ser apresentados de forma explícita, sem preenchimento inventado.

A ausência de uma informação em uma consulta não significa necessariamente que ela não exista na fonte oficial.

---

# Uso responsável

Esta biblioteca deve ser utilizada apenas para consulta e organização de informações públicas ou legitimamente acessíveis pelo usuário.

O projeto não tem como objetivo:

* burlar autenticação;
* contornar captcha;
* acessar processos sigilosos;
* superar restrições técnicas;
* contornar limites definidos pelos tribunais;
* coletar dados pessoais sem finalidade legítima;
* substituir a conferência nas fontes oficiais;
* substituir orientação jurídica profissional.

Ao utilizar agentes de IA:

* diferencie dados obtidos das fontes e análises geradas pelo modelo;
* não trate inferências como fatos oficiais;
* não envie credenciais judiciais sem necessidade e autorização;
* evite expor dados pessoais em logs ou demonstrações;
* mantenha rastreabilidade da origem das informações;
* revise resultados antes de utilizá-los profissionalmente.

Leia antes de usar o projeto em rotinas recorrentes:

* [Uso responsável](docs/uso-responsavel.md)
* [LGPD](docs/lgpd.md)
* [Modelo de ameaças](docs/threat-model.md)
* [Governança](docs/governanca.md)

---

# Status e roadmap

O projeto está em fase beta.

Já estão disponíveis:

* validação de número CNJ;
* API pública;
* CLI;
* cliente configurável;
* eSAJ/TJSP;
* DataJud/CNJ;
* DJEN;
* cache opcional;
* rate limit;
* contratos tipados;
* servidor MCP local;
* testes automatizados;
* build e releases.

Continuam em evolução:

* cobertura de cenários reais do eSAJ;
* exportadores analíticos;
* documentação publicada;
* estabilidade dos contratos durante o beta;
* ampliação dos exemplos profissionais.

Acompanhe:

* [SPECS.md](SPECS.md)
* [CHANGELOG.md](CHANGELOG.md)
* [Roadmap](docs/roadmap.md)
* [Releases](https://github.com/lucmolero/nanojud/releases)

---

# Desenvolvimento

## Instalar dependências

```bash
python -m pip install -e ".[dev]"
```

## Executar os testes

```bash
python -m pytest --cov
```

## Executar verificações de qualidade

```bash
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
```

## Testes ao vivo

Os testes ao vivo ficam desativados por padrão.

No Windows PowerShell:

```powershell
$env:NANOJUD_RUN_LIVE = "1"
python -m pytest -m live
```

No Linux ou macOS:

```bash
export NANOJUD_RUN_LIVE=1
python -m pytest -m live
```

## Antes de abrir um pull request

```bash
python -m pytest --cov
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
python -m build
python -m twine check dist/*
```

Consulte:

* [Contribuindo](CONTRIBUTING.md)
* [Governança](docs/governanca.md)
* [Segurança](SECURITY.md)

---

# Documentação

## Para começar

* [Quickstart](docs/quickstart.md)
* [Instalação com IA](docs/instalacao-com-ia.md)
* [Para advogados](docs/para-advogados.md)
* [Demonstração pública](docs/demonstracao-publica.md)
* [Exemplos seguros](docs/exemplos-seguros.md)

## Para utilizar e integrar

* [MCP local](docs/mcp-local.md)
* [Aprendizados MCP](docs/aprendizados-mcp.md)
* [Cliente configurável](docs/client.md)
* [API Reference](docs/api-reference.md)
* [Guia da CLI](docs/cli.md)
* [Contratos de dados](docs/contracts.md)
* [Erros](docs/errors.md)

## Para entender o projeto

* [Arquitetura](docs/architecture.md)
* [Metodologia](docs/metodologia.md)
* [Reprodutibilidade](docs/reprodutibilidade.md)
* [Fixtures](docs/fixtures.md)
* [Validação real](docs/validacao-real.md)

## Segurança, governança e responsabilidade

* [Uso responsável](docs/uso-responsavel.md)
* [LGPD](docs/lgpd.md)
* [Modelo de ameaças](docs/threat-model.md)
* [Governança](docs/governanca.md)
* [Segurança](SECURITY.md)

## Evolução e contribuição

* [Roadmap](docs/roadmap.md)
* [Contribuindo](CONTRIBUTING.md)
* [Changelog](CHANGELOG.md)

---

# Citação

Para uso acadêmico, técnico ou institucional, utilize o arquivo:

* [CITATION.cff](CITATION.cff)

---

# Licença

Distribuído sob a licença MIT.

Consulte:

* [LICENSE](LICENSE)

---

# Autor

**Luciano Molero** · `lucmolero`

Atuação na intersecção entre Direito, engenharia de software e automação jurídica.

* [LinkedIn](https://www.linkedin.com/in/luciano-molero/)

---

<p align="center">
  <strong>Infraestrutura aberta para dados judiciais públicos, com rastreabilidade, responsabilidade e integração local.</strong>
</p>
