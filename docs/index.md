---
hide:
  - navigation
  - toc
---

> **Versão em preparação.** Esta documentação descreve a candidata 0.6.0 do repositório. A [versão publicada no PyPI](https://pypi.org/project/nanojud/) pode ter menos recursos. Consulte a [matriz de fontes](fontes.md) antes de instalar para uma rotina profissional.

<main class="legal-home">
  <section class="legal-hero" aria-labelledby="legal-home-title">
    <div class="legal-hero__copy">
      <div class="legal-brandline">
        <img src="assets/nanojud-icon.svg" alt="" />
        <span>NanoJud</span>
      </div>
      <p class="legal-kicker">Consulta processual em Python e MCP</p>
      <h1 id="legal-home-title">Consulte processos, confira a origem e trabalhe com dados estruturados.</h1>
      <p class="legal-lede">
        Para advogados, equipes e agentes de IA: capa, andamento, comunicações e peças acessíveis, com estado de
        completude por fonte. Use API Python, linha de comando ou servidor MCP local e gere tabelas e respostas
        fundamentadas nos registros encontrados.
      </p>
      <div class="legal-actions" aria-label="Ações principais">
        <a class="legal-button legal-button--primary" href="quickstart/">Começar pelo quickstart</a>
        <a class="legal-button" href="instalacao-com-ia/">Instalar com IA</a>
        <a class="legal-button" href="demonstracao-publica/">Ver demonstração</a>
        <a class="legal-button legal-button--ghost" href="fontes/">Ver cobertura por fonte</a>
        <a class="legal-button legal-button--ghost" href="https://github.com/lucmolero/nanojud">GitHub</a>
      </div>
    </div>

    <div class="legal-hero__system" aria-label="Fluxo técnico de dados jurídicos">
      <div class="legal-system__top">
        <span class="legal-dot legal-dot--green"></span>
        <span>consulta com proveniência</span>
      </div>
      <div class="legal-flow">
        <div class="legal-node">
          <strong>01</strong>
          <span>CNJ validado</span>
        </div>
        <div class="legal-connector"></div>
        <div class="legal-node">
          <strong>02</strong>
          <span>Fonte consultada</span>
        </div>
        <div class="legal-connector"></div>
        <div class="legal-node legal-node--active">
          <strong>03</strong>
          <span>Dados e limites</span>
        </div>
      </div>
      <pre><code>CNJ → fonte → resultado
       ↘ grau e data da coleta
       ↘ estado e avisos
       ↘ registros e documentos disponíveis</code></pre>
    </div>
  </section>

  <section class="legal-signal-grid" aria-label="Sinais de confiança do projeto">
    <article>
      <strong>Estados claros</strong>
      <span>resultado completo ou parcial por fonte</span>
    </article>
    <article>
      <strong>Contratos</strong>
      <span>contratos públicos e <code>py.typed</code></span>
    </article>
    <article>
      <strong>Testes</strong>
      <span>verificações automatizadas no repositório</span>
    </article>
    <article>
      <strong>LGPD</strong>
      <span>uso responsável documentado</span>
    </article>
  </section>

  <section class="legal-section legal-section--split">
    <div>
      <p class="legal-section__eyebrow">Aplicações</p>
      <h2>Base técnica para produtos, escritórios e pesquisa aplicada.</h2>
    </div>
    <p>
      O projeto foi desenhado para unir engenharia de software, responsabilidade jurídica e abertura acadêmica. Ele
      transforma consultas processuais em dados estruturados para fluxos verificáveis, com origem e limites de acesso
      explícitos para cada fonte.
    </p>
  </section>

  <section class="legal-card-grid" aria-label="Casos de uso">
    <article>
      <span class="legal-card__label">Advocacia</span>
      <h3>Rotinas repetíveis</h3>
      <p>Consulta, estruturação e extração de informações públicas para reduzir retrabalho operacional com revisão humana.</p>
    </article>
    <article>
      <span class="legal-card__label">Legaltech</span>
      <h3>Produto sobre base aberta</h3>
      <p>Contratos tipados, cliente configurável, cache opt-in e erros previsíveis para integração profissional.</p>
    </article>
    <article>
      <span class="legal-card__label">Academia</span>
      <h3>Metodologia explícita</h3>
      <p>Documentação sobre reprodutibilidade, fixtures sanitizadas, limitações e validação controlada.</p>
    </article>
    <article>
      <span class="legal-card__label">IA local</span>
      <h3>Agentes com MCP</h3>
      <p>Instalação guiada para Claude Code, Codex, Gemini e clientes compatíveis com MCP local por <code>stdio</code>.</p>
    </article>
  </section>

  <section class="legal-section legal-section--accent">
    <div>
      <p class="legal-section__eyebrow">Engenharia verificável</p>
      <h2>Código, contratos e limites documentados.</h2>
      <p>
        O repositório combina parser, cliente, CLI, documentação, testes sem rede, testes live opcionais, validação de
        build, auditoria de dependências, changelog, governança, segurança e notas de release versionadas.
      </p>
    </div>
    <div class="legal-checklist" aria-label="Camadas de qualidade">
      <span>Testes automatizados</span>
      <span>Type checking</span>
      <span>Lint e formatação</span>
      <span>Build validado</span>
      <span>Threat model</span>
      <span>Uso responsável</span>
    </div>
  </section>

  <section class="legal-code-section" aria-labelledby="legal-code-title">
    <div>
      <p class="legal-section__eyebrow">Primeiro uso</p>
      <h2 id="legal-code-title">Instale, consulte e trabalhe com dados estruturados.</h2>
      <p>
        A API favorece fluxos claros: configurar limites, consultar uma fonte pública e receber um extrato pronto para
        auditoria, persistência ou integração com agentes internos. Para uso assistido por IA, siga a jornada de
        instalação com MCP local.
      </p>
    </div>
    <pre><code>from nanojud import NanoJudClient, NanoJudConfig

client = NanoJudClient(
    NanoJudConfig(
        timeout=20,
        rate_limit_interval=1.0,
        cache_enabled=True,
    )
)

extrato = client.get_extrato("0015020-23.2010.8.26.0053")
print(extrato["dados_basicos"]["classe"])
print(len(extrato["movimentacoes"]))</code></pre>
  </section>

  <section class="legal-footer-cta">
    <div>
      <p class="legal-section__eyebrow">Projeto independente</p>
      <h2>Consulte a cobertura antes de usar.</h2>
      <p>
        <strong>NanoJud</strong> não é um produto oficial do TJSP, CNJ, eSAJ ou DataJud. A biblioteca organiza
        consultas a fontes públicas ou legitimamente acessíveis pelo usuário.
      </p>
    </div>
    <div class="legal-actions">
      <a class="legal-button legal-button--primary" href="quickstart/">Abrir quickstart</a>
      <a class="legal-button" href="instalacao-com-ia/">Jornada com IA</a>
      <a class="legal-button" href="exemplos-seguros/">Exemplos seguros</a>
    </div>
  </section>
</main>
