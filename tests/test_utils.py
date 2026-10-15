from nanojud.exceptions import FormatoCNJInvalido
from nanojud.normalization import extrair_numeros_cnj
from nanojud.sources import normalizar_fonte
from nanojud.utils import (
    classificar_polo,
    limpar,
    nome_arquivo_seguro,
    normalizar_chave,
    normalizar_numero_cnj,
    validar_numero_cnj,
)


def test_limpar_normaliza_espacos():
    assert limpar("  texto\n com\t espaços  ") == "texto com espaços"


def test_normalizar_chave_remove_acentos_e_pontuacao():
    assert normalizar_chave("Última movimentação:") == "ultima_movimentacao"


def test_nome_arquivo_seguro_remove_caracteres_perigosos():
    assert nome_arquivo_seguro("Ação / Processo nº 1") == "A_o_Processo_n_1"


def test_classificar_polo():
    assert classificar_polo("Autor") == "ativo"
    assert classificar_polo("Réu") == "passivo"
    assert classificar_polo("Terceiro interessado") is None


def test_normalizar_e_validar_numero_cnj():
    numero = normalizar_numero_cnj("10765392020198260100")

    assert numero == "1076539-20.2019.8.26.0100"
    assert validar_numero_cnj(numero) == numero
    assert validar_numero_cnj(numero, segmento=None, tribunal=None) == numero


def test_normalizar_numero_cnj_rejeita_tamanho_invalido():
    try:
        normalizar_numero_cnj("123")
    except FormatoCNJInvalido as exc:
        assert "20" in str(exc)
    else:
        raise AssertionError("CNJ com tamanho invalido deveria falhar")


def test_extrair_numeros_cnj_ignora_candidato_invalido():
    texto = "Processo 1076539-21.2019.8.26.0100"

    assert extrair_numeros_cnj(texto) == []


def test_validar_numero_cnj_rejeita_digito_invalido():
    try:
        validar_numero_cnj("1076539-21.2019.8.26.0100")
    except FormatoCNJInvalido as exc:
        assert "Dígito" in str(exc)
    else:
        raise AssertionError("Dígito inválido deveria gerar FormatoCNJInvalido")


def test_validar_numero_cnj_rejeita_segmento_e_tribunal():
    numero = "1076539-20.2019.8.26.0100"

    for kwargs in [{"segmento": "7"}, {"tribunal": "25"}]:
        try:
            validar_numero_cnj(numero, **kwargs)
        except FormatoCNJInvalido:
            pass
        else:
            raise AssertionError("Escopo incompatível deveria gerar FormatoCNJInvalido")


def test_adicionar_unico():
    from nanojud.utils import adicionar_unico

    valores = ["um"]
    adicionar_unico(valores, "um")
    adicionar_unico(valores, "dois")
    adicionar_unico(valores, "")

    assert valores == ["um", "dois"]


def test_normalizar_fonte_rejeita_desconhecida():
    try:
        normalizar_fonte("projudi")
    except ValueError as exc:
        assert "Fonte desconhecida" in str(exc)
    else:
        raise AssertionError("Fonte desconhecida deveria falhar")


def test_classificar_polo_aceita_abreviaturas_do_esaj():
    assert classificar_polo("Imptte") == "ativo"
    assert classificar_polo("Imptdo") == "passivo"
    assert classificar_polo("Apelte ") == "ativo"
    assert classificar_polo("Interesda.") is None
