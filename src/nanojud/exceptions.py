"""Exceções públicas do nanojud."""

import requests


class NanoJudError(Exception):
    """Classe base para erros previstos da biblioteca."""


class FormatoCNJInvalido(NanoJudError, ValueError):
    """Número CNJ ausente, mal formatado ou com dígito verificador inválido."""


class URLInvalida(NanoJudError, ValueError):
    """URL fora do domínio e caminho esperados pelo cliente."""


class ConsultaIndisponivel(NanoJudError):
    """Fonte remota indisponível, resposta inválida ou falha de comunicação."""


class ConsultaInconclusiva(ConsultaIndisponivel):
    """O portal respondeu, mas a busca específica não produziu resultado verificável."""


class ProcessoNaoEncontrado(NanoJudError):
    """A fonte consultada não retornou uma página de processo válida."""


class DocumentoNaoEncontrado(NanoJudError):
    """A fonte não listou o documento solicitado entre os acessíveis."""


class AcessoRestrito(NanoJudError):
    """A fonte indicou bloqueio, captcha, autenticação, senha ou restrição de acesso."""


class CredencialAusente(NanoJudError):
    """Credencial necessária para uma fonte pública não foi informada."""


class ArquivoInvalido(NanoJudError):
    """Arquivo de entrada ausente, ilegível ou fora do formato esperado."""


class DestinoInvalido(NanoJudError):
    """Destino de saída inválido ou conflitante com um arquivo de entrada."""


class EntradaLoteInvalida(NanoJudError):
    """Arquivo de CNJs de lote ilegível ou não codificado em UTF-8."""


class DownloadIndisponivel(NanoJudError):
    """Não foi possível baixar a peça pública solicitada."""


def mensagem_erro_segura(exc: BaseException) -> str:
    """Oculta detalhes de transporte que podem conter URLs e tokens."""
    if isinstance(exc, requests.RequestException):
        return f"Falha HTTP ({type(exc).__name__})."
    return str(exc)
