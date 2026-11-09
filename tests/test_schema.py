import csv
from pathlib import Path

import pytest
from pydantic import ValidationError

from urbanistico.schema import (
    ExtracaoZona,
    Linha,
    LinhaExtraida,
    Parametro,
    RegistroParametro,
    TipoValor,
    ValorExtraido,
)

CAMINHO_GABARITO = Path(__file__).resolve().parents[1] / "data" / "gold" / "gabarito.csv"


def carregar_gabarito() -> list[dict]:
    with open(CAMINHO_GABARITO, encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def registro_valido(**alteracoes) -> dict:
    base = {
        "zona": "ZRC",
        "linha": "RES-RUB",
        "parametro": "taxa_ocupacao_terreo",
        "valor": "50",
        "unidade": "%",
        "tipo_valor": "numero",
        "nota": "",
        "fonte": "Anexo II",
        "pagina": "1",
    }
    base.update(alteracoes)
    return base


# --- Gabarito ---------------------------------------------------------------


def test_gabarito_inteiro_valida():
    linhas = carregar_gabarito()
    registros = [RegistroParametro(**linha) for linha in linhas]
    assert len(registros) == 84
    assert len({r.chave for r in registros}) == len(registros), "chave duplicada no gabarito"


def test_vazio_do_csv_vira_none():
    r = RegistroParametro(
        **registro_valido(parametro="ca_maximo", valor="", unidade="", tipo_valor="nao_definido")
    )
    assert r.valor is None
    assert r.unidade is None
    assert r.nota is None


# --- Regras que devem falhar ------------------------------------------------


@pytest.mark.parametrize(
    "alteracoes",
    [
        {"valor": "", "tipo_valor": "numero"},  # numero sem valor
        {"valor": "0", "tipo_valor": "nao_definido"},  # "–" virou zero
        {"unidade": "m"},  # unidade errada
        {"valor": "150"},  # taxa acima de 100%
        {"parametro": "gabarito", "valor": "2.5", "unidade": "pav"},  # pavimento fracionado
        {"parametro": "ca_basico", "valor": "1", "unidade": "%"},  # CA não tem unidade
        {"pagina": "0"},
        {"linha": "RES-XYZ"},
    ],
)
def test_registro_invalido(alteracoes):
    with pytest.raises(ValidationError):
        RegistroParametro(**registro_valido(**alteracoes))


def test_valor_extraido_nao_definido_com_numero_falha():
    with pytest.raises(ValidationError):
        ValorExtraido(valor=1.0, tipo_valor=TipoValor.NAO_DEFINIDO)


def test_linha_extraida_sem_parametro_falha():
    numero = {"valor": 50, "tipo_valor": "numero"}
    dados = {"linha": "RES-RUB", **{p.value: numero for p in Parametro}}
    del dados["recuo_frontal"]
    with pytest.raises(ValidationError):
        LinhaExtraida(**dados)


def test_extracao_com_linha_repetida_falha():
    linha = _linhas_zum1()[0]
    with pytest.raises(ValidationError):
        ExtracaoZona(zona="ZUM-1", pagina=5, linhas=[linha, linha])


# --- Conversão largo → longo ------------------------------------------------


def _v(valor=None, nota=None) -> ValorExtraido:
    tipo = TipoValor.NUMERO if valor is not None else TipoValor.NAO_DEFINIDO
    return ValorExtraido(valor=valor, tipo_valor=tipo, nota=nota)


def _linhas_zum1() -> list[LinhaExtraida]:
    nota_recuo = "(a) acima de 9 m de altura: R = H/10"
    comum = {
        "taxa_ocupacao_terreo": _v(70),
        "taxa_ocupacao_demais": _v(70),
        "ca_maximo": _v(),
        "permeabilidade_min": _v(20),
    }
    return [
        LinhaExtraida(
            linha=Linha.RES_RUB, ca_basico=_v(1.3), gabarito=_v(), recuo_frontal=_v(5), **comum
        ),
        LinhaExtraida(
            linha=Linha.RES_RMV,
            ca_basico=_v(3),
            gabarito=_v(8),
            recuo_frontal=_v(5, nota_recuo),
            **comum,
        ),
        LinhaExtraida(
            linha=Linha.NAO_RES,
            ca_basico=_v(3),
            gabarito=_v(8),
            recuo_frontal=_v(5, nota_recuo),
            **comum,
        ),
    ]


def test_para_formato_longo_bate_com_gabarito_zum1():
    extracao = ExtracaoZona(zona="ZUM-1", pagina=5, linhas=_linhas_zum1())
    obtido = {r.chave: r for r in extracao.para_formato_longo()}

    esperado = {
        r.chave: r
        for r in (RegistroParametro(**linha) for linha in carregar_gabarito())
        if r.zona == "ZUM-1"
    }

    assert len(obtido) == 21
    assert obtido == esperado
