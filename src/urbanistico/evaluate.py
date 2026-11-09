"""Avaliação da extração contra o gabarito manual (data/gold/gabarito.csv).

Uso: ``python -m urbanistico.evaluate`` (lê todos os data/output/extracao_*.csv)

A avaliação considera só as zonas presentes na extração. A nota de rodapé é avaliada
separadamente (pelas letras "(a)", "(b)"...), fora da acurácia principal.
"""

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path

from urbanistico.schema import Linha, Parametro, RegistroParametro, TipoValor

CAMINHO_GABARITO = Path("data/gold/gabarito.csv")
PASTA_SAIDA = Path("data/output")

Chave = tuple[str, Linha, Parametro]

# Ordem de exibição; "extra" fica fora porque não tem par no gabarito.
CATEGORIAS = ["acerto", "alucinacao", "erro_valor", "omissao", "erro_tipo", "nao_extraido"]


def carregar_registros(caminho: Path) -> dict[Chave, RegistroParametro]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        registros = [RegistroParametro(**linha) for linha in csv.DictReader(arquivo)]
    por_chave: dict[Chave, RegistroParametro] = {}
    for registro in registros:
        if registro.chave in por_chave:
            raise ValueError(f"chave repetida em {caminho}: {registro.chave}")
        por_chave[registro.chave] = registro
    return por_chave


# ---------------------------------------------------------------------------
# Lógica de métricas — REVISÃO DO YUDI (implementada pelo Claude a pedido)
# ---------------------------------------------------------------------------


def classificar_registro(gold: RegistroParametro, extraido: RegistroParametro | None) -> str:
    """Classifica uma chave do gabarito comparando com o valor extraído.

    - acerto:       mesmo tipo_valor e, se número, mesmo valor
    - alucinacao:   gabarito sem número (ex.: "–") e a extração trouxe número  ← a mais grave
    - erro_valor:   os dois são número, mas diferentes
    - omissao:      gabarito tem número e a extração disse que não há
    - erro_tipo:    tipos não numéricos diferentes (ex.: nao_definido × de_origem)
    - nao_extraido: a chave não veio na extração (falha do LLM ou da validação)
    """
    if extraido is None:
        return "nao_extraido"
    gold_numero = gold.tipo_valor == TipoValor.NUMERO
    extraido_numero = extraido.tipo_valor == TipoValor.NUMERO
    if gold_numero and extraido_numero:
        # abs_tol cobre ruído de ponto flutuante (1.3 lido como 1.2999999).
        return "acerto" if math.isclose(gold.valor, extraido.valor, abs_tol=1e-6) else "erro_valor"
    if not gold_numero and extraido_numero:
        return "alucinacao"
    if gold_numero and not extraido_numero:
        return "omissao"
    return "acerto" if gold.tipo_valor == extraido.tipo_valor else "erro_tipo"


def letras_da_nota(nota: str | None) -> set[str]:
    """'(c) com Outorga; (f) incentivos' → {'c', 'f'}."""
    return set(re.findall(r"\(([a-z])\)", nota or "", flags=re.IGNORECASE))


def avaliar(gold: dict[Chave, RegistroParametro], extracao: dict[Chave, RegistroParametro]) -> dict:
    """Compara a extração com o gabarito, restrito às zonas presentes na extração."""
    zonas = {chave[0] for chave in extracao}
    gold_filtrado = {k: v for k, v in gold.items() if k[0] in zonas}

    detalhes = []
    for chave, registro_gold in sorted(gold_filtrado.items()):
        registro_extraido = extracao.get(chave)
        categoria = classificar_registro(registro_gold, registro_extraido)
        nota_ok = registro_extraido is not None and letras_da_nota(
            registro_gold.nota
        ) == letras_da_nota(registro_extraido.nota)
        detalhes.append(
            {
                "chave": chave,
                "categoria": categoria,
                "esperado": registro_gold,
                "obtido": registro_extraido,
                "nota_ok": nota_ok,
            }
        )

    total = len(detalhes)
    contagem = Counter(d["categoria"] for d in detalhes)
    por_parametro: dict[str, Counter] = {}
    for d in detalhes:
        por_parametro.setdefault(d["chave"][2].value, Counter())[d["categoria"]] += 1

    return {
        "zonas": sorted(zonas),
        "total": total,
        "contagem": {c: contagem.get(c, 0) for c in CATEGORIAS},
        "acuracia": contagem["acerto"] / total if total else 0.0,
        "taxa_alucinacao": contagem["alucinacao"] / total if total else 0.0,
        "acuracia_nota": sum(d["nota_ok"] for d in detalhes) / total if total else 0.0,
        "extras": sorted(set(extracao) - set(gold_filtrado)),
        "por_parametro": por_parametro,
        "detalhes": detalhes,
    }


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


def _descrever(registro: RegistroParametro | None) -> str:
    """Três estados explícitos para nunca confundir faltante com zero."""
    if registro is None:
        return "não extraído"
    if registro.tipo_valor == TipoValor.NUMERO:
        return f"{registro.valor:g} {registro.unidade or ''}".strip()
    if registro.tipo_valor == TipoValor.NAO_DEFINIDO:
        return "não definido no quadro (–)"
    return registro.tipo_valor.value


def imprimir_relatorio(resultado: dict) -> None:
    total = resultado["total"]
    print(f"Zonas avaliadas: {', '.join(resultado['zonas'])} ({total} chaves do gabarito)")
    print(f"Acurácia:          {resultado['acuracia']:.1%}")
    print(f"Taxa de alucinação: {resultado['taxa_alucinacao']:.1%}")
    print(f"Acerto de notas:    {resultado['acuracia_nota']:.1%}  (fora da acurácia principal)")
    print("\nPor categoria:")
    for categoria, n in resultado["contagem"].items():
        print(f"  {categoria:<13} {n}")
    if resultado["extras"]:
        print(f"  {'extra':<13} {len(resultado['extras'])}  (chaves fora do gabarito)")

    print("\nPor parâmetro (acertos/total):")
    for parametro, contagem in resultado["por_parametro"].items():
        print(f"  {parametro:<22} {contagem['acerto']}/{sum(contagem.values())}")

    erros = [d for d in resultado["detalhes"] if d["categoria"] != "acerto" or not d["nota_ok"]]
    if erros:
        print("\nDivergências:")
        for d in erros:
            zona, linha, parametro = d["chave"]
            rotulo = d["categoria"] if d["categoria"] != "acerto" else "nota"
            print(
                f"  [{rotulo}] {zona} {linha.value} {parametro.value}: "
                f"esperado {_descrever(d['esperado'])}, obtido {_descrever(d['obtido'])}"
            )
            if rotulo == "nota":
                obtida = d["obtido"].nota if d["obtido"] else None
                print(f"      nota esperada: {d['esperado'].nota!r} | obtida: {obtida!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia a extração contra o gabarito.")
    parser.add_argument("--gabarito", type=Path, default=CAMINHO_GABARITO)
    parser.add_argument(
        "--extracao",
        type=Path,
        nargs="*",
        help="CSVs da extração (padrão: data/output/extracao_*.csv)",
    )
    args = parser.parse_args()

    arquivos = args.extracao or sorted(PASTA_SAIDA.glob("extracao_*.csv"))
    if not arquivos:
        raise SystemExit("nenhum CSV de extração encontrado; rode urbanistico.extract antes")

    extracao: dict[Chave, RegistroParametro] = {}
    for arquivo in arquivos:
        extracao.update(carregar_registros(arquivo))
    imprimir_relatorio(avaliar(carregar_registros(args.gabarito), extracao))


if __name__ == "__main__":
    main()
