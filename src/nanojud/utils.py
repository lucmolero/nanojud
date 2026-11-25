"""Utility helpers for nanojud."""

import math
import re
import stat
import tempfile
import unicodedata
from pathlib import Path

from .exceptions import DestinoInvalido, FormatoCNJInvalido

CNJ_RE = re.compile(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$")
MAX_TIMEOUT_SECONDS = 24 * 60 * 60


def salvar_pdf_atomico(conteudo: bytes, destino: Path) -> None:
    """Publica bytes já validados no mesmo volume do destino."""
    try:
        with tempfile.TemporaryDirectory(dir=destino.parent, prefix=".nanojud-") as pasta:
            temporario = Path(pasta) / "peca.pdf"
            temporario.write_bytes(conteudo)
            temporario.replace(destino)
    except OSError as exc:
        raise DestinoInvalido(f"Não foi possível gravar o PDF em '{destino}'.") from exc


def tamanho_pdf_existente_valido(caminho: Path, max_bytes: int) -> int | None:
    """Retorna o tamanho de um PDF local regular válido, ou None se não for seguro reutilizá-lo."""
    try:
        if caminho.is_symlink():
            return None
        metadados = caminho.stat()
        if not stat.S_ISREG(metadados.st_mode) or not 5 <= metadados.st_size <= max_bytes:
            return None
        with caminho.open("rb") as arquivo:
            if not arquivo.read(5).startswith(b"%PDF"):
                return None
        return metadados.st_size
    except OSError:
        return None


def validar_inteiro(valor: object, *, nome: str, minimo: int, maximo: int | None = None) -> int:
    """Valida um inteiro de fronteira sem aceitar bool como subtipo de int."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        if maximo is not None:
            raise ValueError(f"{nome} deve ser um inteiro entre {minimo} e {maximo}.")
        raise ValueError(f"{nome} deve ser um inteiro válido.")
    if valor < minimo or (maximo is not None and valor > maximo):
        if maximo is None:
            raise ValueError(f"{nome} deve ser pelo menos {minimo}.")
        raise ValueError(f"{nome} deve estar entre {minimo} e {maximo}.")
    return valor


def validar_timeout(timeout: object, *, nome: str = "timeout") -> float:
    """Rejeita timeouts de rede que possam remover o limite operacional."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError(f"{nome} deve ser finito e estar entre 0 e 86400 segundos.")
    try:
        finito = math.isfinite(timeout)
    except OverflowError:
        finito = False
    if not finito or timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"{nome} deve ser finito e estar entre 0 e 86400 segundos.")
    return float(timeout)


def validar_ttl_cache(ttl_seconds: object) -> int:
    """Valida TTL inteiro não negativo; zero significa que o cache não expira."""
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 0:
        raise ValueError("cache_ttl_seconds deve ser um inteiro não negativo.")
    return ttl_seconds


def validar_prazo_total(prazo_total: object) -> None:
    """Valida o limite de espera total; None desativa explicitamente esse limite."""
    if prazo_total is None:
        return
    if isinstance(prazo_total, bool) or not isinstance(prazo_total, (int, float)):
        raise ValueError("prazo_total deve ser None ou ficar entre 0 e 86400 segundos.")
    try:
        finito = math.isfinite(prazo_total)
    except OverflowError:
        finito = False
    if not finito or prazo_total < 0 or prazo_total > MAX_TIMEOUT_SECONDS:
        raise ValueError("prazo_total deve ser None ou ficar entre 0 e 86400 segundos.")


def limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip()


def nome_arquivo_seguro(texto: str, fallback: str = "processo") -> str:
    nome = re.sub(r"[^A-Za-z0-9_.-]", "_", limpar(texto))
    nome = re.sub(r"_+", "_", nome).strip("_.")
    return nome or fallback


def normalizar_numero_cnj(numero: str) -> str:
    """Normaliza um CNJ aceitando entrada já pontuada ou apenas dígitos."""
    valor = limpar(numero)
    if CNJ_RE.match(valor):
        return valor

    digitos = re.sub(r"\D", "", valor)
    if len(digitos) != 20:
        raise FormatoCNJInvalido("Número CNJ deve ter 20 dígitos.")
    return (
        f"{digitos[:7]}-{digitos[7:9]}."
        f"{digitos[9:13]}.{digitos[13]}.{digitos[14:16]}.{digitos[16:]}"
    )


def validar_numero_cnj(numero: str, segmento: str | None = "8", tribunal: str | None = "26") -> str:
    """Valida formato, escopo TJSP e dígito verificador de número CNJ."""
    normalizado = normalizar_numero_cnj(numero)
    match = CNJ_RE.match(normalizado)
    if not match:
        raise FormatoCNJInvalido("Número fora do formato CNJ esperado.")

    sequencial, dv, ano, seg, tr, origem = match.groups()
    if segmento is not None and seg != segmento:
        raise FormatoCNJInvalido("Número CNJ não pertence ao segmento esperado.")
    if tribunal is not None and tr != tribunal:
        raise FormatoCNJInvalido("Número CNJ não pertence ao escopo eSAJ/TJSP.")

    base = f"{sequencial}{ano}{seg}{tr}{origem}"
    calculado = 98 - (int(f"{base}00") % 97)
    if f"{calculado:02d}" != dv:
        raise FormatoCNJInvalido("Dígito verificador CNJ inválido.")
    return normalizado


def eh_tjsp(numero_cnj: str) -> bool:
    """Indica se o número CNJ (com máscara) é da Justiça Estadual de São Paulo."""
    return numero_cnj.split(".")[-3:-1] == ["8", "26"]


def normalizar_chave(texto: str) -> str:
    chave = unicodedata.normalize("NFKD", limpar(texto))
    chave = "".join(ch for ch in chave if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "_", chave).strip("_")


POLOS_ATIVOS = {
    "autor",
    "autora",
    "requerente",
    "reqte",
    "reqnte",
    "exequente",
    "exeqte",
    "credor",
    "credora",
    "embargante",
    "embargte",
    "impetrante",
    "imptte",
    "apelante",
    "apelte",
    "apte",
    "agravante",
    "agvte",
    "reclamante",
    "reclamte",
    "aut",
    "justica_publica",
    "ministerio_publico",
    "ministerio_publico_do_estado_de_sao_paulo",
}

POLOS_PASSIVOS = {
    "reu",
    "re",
    "requerido",
    "requerida",
    "reqdo",
    "reqda",
    "executado",
    "executada",
    "exectdo",
    "exectda",
    "devedor",
    "devedora",
    "embargado",
    "embargada",
    "embargdo",
    "embargda",
    "averiguado",
    "averiguada",
    "falido",
    "falida",
    "impetrado",
    "impetrada",
    "imptdo",
    "imptda",
    "apelado",
    "apelada",
    "apeldo",
    "apelda",
    "apdo",
    "agravado",
    "agravada",
    "agvdo",
    "reclamado",
    "reclamada",
    "reclamdo",
    "indiciado",
    "indiciada",
    "acusado",
    "acusada",
    "querelado",
    "querelada",
    "denunciado",
    "denunciada",
}


def classificar_polo(tipo: str) -> str | None:
    tipo_normalizado = normalizar_chave(tipo)
    if tipo_normalizado in POLOS_ATIVOS:
        return "ativo"
    if tipo_normalizado in POLOS_PASSIVOS:
        return "passivo"
    return None


def adicionar_unico(lista: list, valor: str) -> None:
    if valor and valor not in lista:
        lista.append(valor)
