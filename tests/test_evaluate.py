"""Testes da lógica de métricas do evaluate.py, um caso por categoria."""

import pytest

from urbanistico.evaluate import avaliar, classificar_registro, letras_da_nota
from urbanistico.schema import Linha, Parametro, RegistroParametro, TipoValor


def _reg(valor=None, parametro=Parametro.CA_BASICO, zona="ZRC", nota=None, tipo=None):
    if tipo is None:
        tipo = TipoValor.NUMERO if valor is not None else TipoValor.NAO_DEFINIDO
    unidades = {Parametro.CA_BASICO: None, Parametro.CA_MAXIMO: None, Parametro.GABARITO: "pav"}
    return RegistroParametro(
        zona=zona,
        linha=Linha.RES_RUB,
        parametro=parametro,
        valor=valor,
        unidade=unidades[parametro],
        tipo_valor=tipo,
        nota=nota,
        fonte="Anexo II",
        pagina=1,
    )


@pytest.mark.parametrize(
    ("gold", "extraido", "esperado"),
    [
        (_reg(1.3), _reg(1.3), "acerto"),
        (_reg(1.3), _reg(1.2999999999), "acerto"),  # ruído de ponto flutuante
        (_reg(None), _reg(None), "acerto"),  # "–" lido como "–"
        (_reg(None), _reg(2.0), "alucinacao"),
        (_reg(1.3), _reg(1.2), "erro_valor"),
        (_reg(1.3), _reg(None), "omissao"),
        (_reg(None), _reg(None, tipo=TipoValor.DE_ORIGEM), "erro_tipo"),
        (_reg(1.3), None, "nao_extraido"),
    ],
)
def test_classificar_registro(gold, extraido, esperado):
    assert classificar_registro(gold, extraido) == esperado


def test_letras_da_nota():
    assert letras_da_nota("(c) com Outorga; (f) incentivos") == {"c", "f"}
    assert letras_da_nota(None) == set()


def test_avaliar_filtra_zonas_e_calcula_taxas():
    gold_regs = [
        _reg(1.0, Parametro.CA_BASICO),
        _reg(None, Parametro.CA_MAXIMO),
        _reg(2.0, Parametro.GABARITO, nota="(b) admite 3"),
        _reg(9.0, Parametro.CA_BASICO, zona="ZR-2"),  # zona não extraída: fora da conta
    ]
    extr_regs = [
        _reg(1.0, Parametro.CA_BASICO),
        _reg(5.0, Parametro.CA_MAXIMO),  # alucinação
        _reg(2.0, Parametro.GABARITO),  # acerto, mas sem a nota
    ]
    resultado = avaliar({r.chave: r for r in gold_regs}, {r.chave: r for r in extr_regs})

    assert resultado["zonas"] == ["ZRC"]
    assert resultado["total"] == 3
    assert resultado["contagem"]["acerto"] == 2
    assert resultado["contagem"]["alucinacao"] == 1
    assert resultado["acuracia"] == pytest.approx(2 / 3)
    assert resultado["taxa_alucinacao"] == pytest.approx(1 / 3)
    assert resultado["acuracia_nota"] == pytest.approx(2 / 3)
    assert resultado["extras"] == []
