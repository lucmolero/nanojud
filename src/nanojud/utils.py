"""Utility helpers for nanojud."""

import re
import unicodedata

from .exceptions import FormatoCNJInvalido

CNJ_RE = re.compile(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$")


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
