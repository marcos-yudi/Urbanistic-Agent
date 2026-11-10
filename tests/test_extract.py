"""Testes do extract.py com o LLM mockado (sem chamada real ao Gemini)."""

import json

import pytest

from urbanistico import extract, llm
from urbanistico.schema import Parametro, TipoValor


def _celula(valor, nota=None):
    if valor is None:
        return {"valor": None, "tipo_valor": "nao_definido", "nota": nota}
    return {"valor": valor, "tipo_valor": "numero", "nota": nota}


def _linha(nome, ca_basico):
    return {
        "linha": nome,
        "taxa_ocupacao_terreo": _celula(50),
        "taxa_ocupacao_demais": _celula(50),
        "ca_basico": _celula(ca_basico),
        "ca_maximo": _celula(None),
        "gabarito": _celula(2, "(b) admite 3 pavimentos"),
        "permeabilidade_min": _celula(20),
        "recuo_frontal": _celula(5),
    }


def _resposta(**sobrescrever):
    dados = {
        # zona e página erradas de propósito: devem ser sobrescritas.
        "zona": "ZONA-ERRADA",
        "pagina": 99,
        "fonte": "outra",
        "linhas": [_linha("RES-RUB", 1), _linha("NAO-RES", 2)],
    }
    dados.update(sobrescrever)
    return dados


@pytest.fixture
def mock_llm(monkeypatch, tmp_path):
    """Substitui o Gemini por uma resposta fixa e não toca no PDF real."""

    def configurar(dados):
        texto = dados if isinstance(dados, str) else json.dumps(dados)
        monkeypatch.setattr(llm, "gerar_json", lambda *a, **k: (texto, {}))
        monkeypatch.setattr(extract, "recortar_pagina", lambda *a, **k: b"%PDF-falso")

    return configurar


def test_resposta_valida_gera_14_registros(mock_llm):
    mock_llm(_resposta())
    registros, falhas = extract.extrair_zona("ZRC", 1)
    assert falhas == []
    assert len(registros) == 14
    assert {r.zona for r in registros} == {"ZRC"}
    assert {r.pagina for r in registros} == {1}
    assert {r.fonte for r in registros} == {"Anexo II"}


def test_nao_definido_e_preservado(mock_llm):
    mock_llm(_resposta())
    registros, _ = extract.extrair_zona("ZRC", 1)
    ca_max = [r for r in registros if r.parametro == Parametro.CA_MAXIMO]
    assert all(r.tipo_valor == TipoValor.NAO_DEFINIDO and r.valor is None for r in ca_max)


def test_celula_invalida_vira_falha_e_resto_e_aproveitado(mock_llm):
    dados = _resposta()
    dados["linhas"][1]["taxa_ocupacao_terreo"] = _celula(150)  # fora de 0–100
    mock_llm(dados)
    registros, falhas = extract.extrair_zona("ZRC", 1)
    assert len(registros) == 13
    assert len(falhas) == 1
    assert falhas[0]["linha"] == "NAO-RES"
    assert falhas[0]["parametro"] == "taxa_ocupacao_terreo"
    # mesmo no plano B, zona e página vêm de quem chamou
    assert {(r.zona, r.pagina) for r in registros} == {("ZRC", 1)}


def test_numero_com_tipo_nao_definido_vira_falha(mock_llm):
    dados = _resposta()
    dados["linhas"][0]["gabarito"] = {"valor": 3, "tipo_valor": "nao_definido", "nota": None}
    mock_llm(dados)
    registros, falhas = extract.extrair_zona("ZRC", 1)
    assert len(registros) == 13
    assert [(f["linha"], f["parametro"]) for f in falhas] == [("RES-RUB", "gabarito")]


def test_linha_repetida_mantem_a_primeira(mock_llm):
    dados = _resposta(linhas=[_linha("RES-RUB", 1), _linha("RES-RUB", 9)])
    mock_llm(dados)
    registros, falhas = extract.extrair_zona("ZRC", 1)
    assert len(registros) == 7
    assert {r.valor for r in registros if r.parametro == Parametro.CA_BASICO} == {1}
    assert len(falhas) == 1


def test_json_invalido_nao_gera_registros(mock_llm):
    mock_llm("isto não é json")
    registros, falhas = extract.extrair_zona("ZRC", 1)
    assert registros == []
    assert "JSON inválido" in falhas[0]["erro"]


def test_csv_tem_formato_do_gabarito(mock_llm, tmp_path):
    mock_llm(_resposta())
    registros, _ = extract.extrair_zona("ZRC", 1)
    caminho = tmp_path / "extracao_ZRC.csv"
    extract.salvar_csv(registros, caminho)
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "zona,linha,parametro,valor,unidade,tipo_valor,nota,fonte,pagina"
    assert "ZRC,RES-RUB,taxa_ocupacao_terreo,50,%,numero,,Anexo II,1" in linhas
    assert "ZRC,RES-RUB,ca_maximo,,,nao_definido,,Anexo II,1" in linhas


def test_prompt_preenche_zona_e_pagina():
    prompt = extract.carregar_prompt("v1", "ZRC", 1)
    assert "**ZRC**" in prompt
    assert "{zona}" not in prompt and "{pagina}" not in prompt
    assert "<!--" not in prompt  # notas internas não vão para o LLM


def test_recortar_pagina_rejeita_pagina_inexistente(tmp_path):
    import pymupdf

    caminho = tmp_path / "uma_pagina.pdf"
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(caminho)
    assert extract.recortar_pagina(caminho, 1).startswith(b"%PDF")
    with pytest.raises(ValueError):
        extract.recortar_pagina(caminho, 2)


def test_zonas_mvp_batem_com_o_gabarito():
    """Toda zona do --todas tem gabarito na mesma página, e vice-versa."""
    import csv

    with open("data/gold/gabarito.csv", encoding="utf-8", newline="") as arquivo:
        gold = {(r["zona"], int(r["pagina"])) for r in csv.DictReader(arquivo)}
    assert set(extract.ZONAS_MVP.items()) == gold
