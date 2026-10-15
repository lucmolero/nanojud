"""Exceções públicas do nanojud."""


class NanoJudError(Exception):
    """Classe base para erros previstos da biblioteca."""


class FormatoCNJInvalido(NanoJudError, ValueError):
    """Número CNJ ausente, mal formatado ou com dígito verificador inválido."""


class URLInvalida(NanoJudError, ValueError):
    """URL fora do domínio e caminho esperados pelo cliente."""


class ConsultaIndisponivel(NanoJudError):
    """Fonte remota indisponível, resposta inválida ou falha de comunicação."""


class ProcessoNaoEncontrado(NanoJudError):
    """A fonte consultada não retornou uma página de processo válida."""


class AcessoRestrito(NanoJudError):
    """A fonte indicou bloqueio, captcha, autenticação, senha ou restrição de acesso."""


class CredencialAusente(NanoJudError):
    """Credencial necessária para uma fonte pública não foi informada."""


class ArquivoInvalido(NanoJudError):
    """Arquivo de entrada ausente, ilegível ou fora do formato esperado."""


class DownloadIndisponivel(NanoJudError):
    """Não foi possível baixar a peça pública solicitada."""
