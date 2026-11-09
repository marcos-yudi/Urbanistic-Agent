"""Extração dos parâmetros de um quadro do Anexo II (uma zona, uma página) com o LLM.

Fluxo: recorta a página do PDF → envia ao Gemini com o prompt versionado → valida com
``ExtracaoZona``. Se a validação do objeto inteiro falhar, valida célula a célula: o que for
válido é aproveitado e cada célula inválida vira uma falha registrada no log (nunca um valor
inventado). Na avaliação, a célula com falha conta como ``nao_extraido``.

Uso: ``python -m urbanistico.extract --zona ZRC --pagina 1`` ou ``--todas`` (zonas do MVP)
"""

import argparse
import csv
import json
import logging
import re
from pathlib import Path

import pymupdf
from pydantic import ValidationError

from urbanistico import llm
from urbanistico.schema import UNIDADES, ExtracaoZona, Linha, Parametro, RegistroParametro

CAMINHO_ANEXO_II = Path("data/raw/ANEXO II.pdf")
PASTA_PROMPTS = Path("prompts")
PASTA_SAIDA = Path("data/output")
FONTE = "Anexo II"
COLUNAS_CSV = list(RegistroParametro.model_fields)

# Zonas do MVP → página do quadro no Anexo II (uma zona por página).
ZONAS_MVP: dict[str, int] = {"ZRC": 1, "ZR-2": 3, "ZUM-1": 5, "ZC-1": 7, "ZEU-RES": 17}

log = logging.getLogger(__name__)


def recortar_pagina(caminho_pdf: Path, pagina: int) -> bytes:
    """Devolve um PDF só com a página pedida (1-indexada), para mandar ao LLM o mínimo."""
    with pymupdf.open(caminho_pdf) as origem, pymupdf.open() as destino:
        if not 1 <= pagina <= origem.page_count:
            raise ValueError(f"página {pagina} fora do PDF ({origem.page_count} páginas)")
        destino.insert_pdf(origem, from_page=pagina - 1, to_page=pagina - 1)
        return destino.tobytes()


def carregar_prompt(versao: str, zona: str, pagina: int) -> str:
    texto = (PASTA_PROMPTS / f"extracao_{versao}.md").read_text(encoding="utf-8")
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.DOTALL).strip()  # tira notas internas
    # replace em vez de str.format: o prompt pode ter chaves literais (JSON de exemplo).
    return texto.replace("{zona}", zona).replace("{pagina}", str(pagina))


def _validar_por_celula(
    dados: dict, zona: str, pagina: int
) -> tuple[list[RegistroParametro], list[dict]]:
    """Plano B quando o objeto inteiro não valida: aproveita célula a célula."""
    registros: list[RegistroParametro] = []
    falhas: list[dict] = []
    vistas: set[Linha] = set()

    for item in dados.get("linhas") or []:
        nome_linha = item.get("linha") if isinstance(item, dict) else None
        try:
            linha = Linha(nome_linha)
        except ValueError:
            falhas.append(
                {
                    "zona": zona,
                    "linha": nome_linha,
                    "parametro": None,
                    "erro": f"linha desconhecida: {nome_linha!r}",
                }
            )
            continue
        if linha in vistas:
            falhas.append(
                {
                    "zona": zona,
                    "linha": linha.value,
                    "parametro": None,
                    "erro": "linha repetida; mantida a primeira ocorrência",
                }
            )
            continue
        vistas.add(linha)

        for parametro in Parametro:
            celula = item.get(parametro.value)
            try:
                if not isinstance(celula, dict):
                    raise ValueError("célula ausente na resposta do LLM")
                registros.append(
                    RegistroParametro(
                        zona=zona,
                        linha=linha,
                        parametro=parametro,
                        valor=celula.get("valor"),
                        unidade=UNIDADES[parametro],
                        tipo_valor=celula.get("tipo_valor"),
                        nota=celula.get("nota"),
                        fonte=FONTE,
                        pagina=pagina,
                    )
                )
            except (ValidationError, ValueError) as erro:
                falhas.append(
                    {
                        "zona": zona,
                        "linha": linha.value,
                        "parametro": parametro.value,
                        "erro": str(erro),
                    }
                )
    return registros, falhas


def interpretar_resposta(
    texto: str, zona: str, pagina: int
) -> tuple[list[RegistroParametro], list[dict]]:
    """Converte o JSON do LLM em registros canônicos + lista de falhas.

    ``zona`` e ``pagina`` vêm de quem chamou, nunca do LLM: a página de origem não pode
    depender do modelo."""
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        return [], [
            {"zona": zona, "linha": None, "parametro": None, "erro": f"JSON inválido: {erro}"}
        ]
    if not isinstance(dados, dict):
        return [], [
            {
                "zona": zona,
                "linha": None,
                "parametro": None,
                "erro": "resposta não é um objeto JSON",
            }
        ]

    dados.update(zona=zona, pagina=pagina, fonte=FONTE)
    try:
        return ExtracaoZona.model_validate(dados).para_formato_longo(), []
    except ValidationError:
        return _validar_por_celula(dados, zona, pagina)


def extrair_zona(
    zona: str,
    pagina: int,
    versao_prompt: str = "v1",
    caminho_pdf: Path = CAMINHO_ANEXO_II,
) -> tuple[list[RegistroParametro], list[dict]]:
    prompt = carregar_prompt(versao_prompt, zona, pagina)
    pdf_pagina = recortar_pagina(caminho_pdf, pagina)
    texto, _ = llm.gerar_json(
        prompt,
        pdf_pagina,
        ExtracaoZona,
        contexto={"zona": zona, "pagina": pagina, "prompt": versao_prompt},
    )
    registros, falhas = interpretar_resposta(texto, zona, pagina)
    for falha in falhas:
        log.warning("falha de validação: %s", falha)
    return registros, falhas


def _formatar_valor(valor: float | None) -> str:
    """Como no gabarito: vazio para nulo, inteiro sem '.0', decimal com ponto."""
    if valor is None:
        return ""
    return str(int(valor)) if valor == int(valor) else str(valor)


def salvar_csv(registros: list[RegistroParametro], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_CSV)
        escritor.writeheader()
        for registro in registros:
            linha = registro.model_dump(mode="json")
            linha["valor"] = _formatar_valor(registro.valor)
            escritor.writerow({k: "" if v is None else v for k, v in linha.items()})


def salvar_falhas(falhas: list[dict], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=["zona", "linha", "parametro", "erro"])
        escritor.writeheader()
        escritor.writerows(falhas)


def extrair_e_salvar(zona: str, pagina: int, versao_prompt: str = "v1") -> None:
    registros, falhas = extrair_zona(zona, pagina, versao_prompt)
    saida = PASTA_SAIDA / f"extracao_{zona}.csv"
    salvar_csv(registros, saida)
    salvar_falhas(falhas, PASTA_SAIDA / f"falhas_{zona}.csv")
    print(f"{zona}: {len(registros)} registros válidos → {saida}; {len(falhas)} falhas")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai quadros do Anexo II com o LLM.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--zona", help="uma zona (exige --pagina)")
    grupo.add_argument("--todas", action="store_true", help="todas as zonas do MVP")
    parser.add_argument("--pagina", type=int)
    parser.add_argument("--prompt", default="v1", help="versão do prompt (ex.: v1)")
    args = parser.parse_args()
    if args.zona and args.pagina is None:
        parser.error("--zona exige --pagina")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    zonas = ZONAS_MVP if args.todas else {args.zona: args.pagina}
    for zona, pagina in zonas.items():
        extrair_e_salvar(zona, pagina, args.prompt)


if __name__ == "__main__":
    main()
