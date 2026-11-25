# v0.6.0 — candidata

Esta versão está em preparação e **ainda não foi publicada**. As notas descrevem o código candidato; a matriz de [fontes e cobertura](fontes.md) define quais integrações têm observação operacional e quais permanecem em validação.

## Mudanças previstas

- Python 3.11.5 a 3.14 passa a ser a faixa suportada. A retirada de Python 3.10 é uma alteração de compatibilidade e exige revisão das dependências e CI antes da publicação.
- Consulta DJEN detalhada com paginação, estado de completude e preservação de páginas obtidas antes de uma falha.
- Exportação tabular em Python, CLI e MCP, com colunas de proveniência e proteção do CSV contra interpretação de fórmulas.
- Lotes de consultas e documentos por processo, com resultado individual e manifesto dos arquivos baixados.
- e-SAJ/TJSP 2G, PJe/TJMG 1G, TJRJ 1G e MNI por instalação como integrações de capacidades distintas. Consulte a matriz antes de escolher uma fonte.
- Correções de isolamento da sessão de autenticação e-SAJ, fechamento da conexão SQLite e tipagem dos contratos de extração.

## Compatibilidade e acesso

Consultas de capa e movimentos, publicações, índice de peças e download são capacidades separadas. Acesso a peça depende da fonte e da sessão. O DJEN não fornece autos; MNI exige configuração de uma instalação; DataJud depende de resposta do índice correspondente. A integração eproc/TJSP ainda não possui consulta positiva ponta a ponta comprovada e permanece experimental.

## Antes da publicação

Em 13/11/2026, a matriz Linux local para Python 3.11–3.14, a suíte Windows, a instalação limpa do wheel 0.6.0, os smokes Python/CLI/MCP, a auditoria de dependências e `twine check` passaram para o artefato identificado em `reports/arquivo/candidate-0.6.0-linux-matrix-2026-11-13.sha256`. Isso não substitui a revisão editorial final nem a decisão de publicar. Antes da publicação, reconcilie os exemplos públicos com o mesmo pacote, execute TestPyPI e repita os gates afetados caso código ou metadados do pacote mudem.
