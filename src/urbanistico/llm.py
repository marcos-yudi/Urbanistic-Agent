"""Ponto único de chamada ao LLM (Gemini).

Toda chamada registra uma linha em ``logs/llm.jsonl`` com modelo, tokens, custo estimado,
latência e erro (regra do projeto). Modelo e chave vêm do ambiente (``.env``).
"""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

CAMINHO_LOG = Path("logs/llm.jsonl")


def _preco_por_milhao(variavel: str) -> float | None:
    """Preço em USD por 1 milhão de tokens, lido do ambiente.

    Fica fora do código porque o preço muda por modelo e com o tempo; sem a variável,
    o custo é registrado como nulo (no nível gratuito o custo real é zero)."""
    bruto = os.getenv(variavel)
    return float(bruto) if bruto else None


def _estimar_custo(tokens_entrada: int | None, tokens_saida: int | None) -> float | None:
    preco_entrada = _preco_por_milhao("GEMINI_PRECO_ENTRADA_USD")
    preco_saida = _preco_por_milhao("GEMINI_PRECO_SAIDA_USD")
    if preco_entrada is None or preco_saida is None:
        return None
    return ((tokens_entrada or 0) * preco_entrada + (tokens_saida or 0) * preco_saida) / 1e6


def _registrar(evento: dict) -> None:
    CAMINHO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CAMINHO_LOG.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")


def gerar_json(
    prompt: str,
    pdf_bytes: bytes,
    schema: type[BaseModel],
    contexto: dict | None = None,
) -> tuple[str, dict]:
    """Envia o prompt + uma página em PDF e devolve o JSON (texto cru) e as métricas da chamada.

    A validação pelo Pydantic fica com quem chama (``extract.py``), para que falhas de
    validação possam ser tratadas célula a célula. ``contexto`` (ex.: zona, página, versão do
    prompt) é só gravado no log.
    """
    load_dotenv()
    modelo = os.environ["GEMINI_MODEL"]
    cliente = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    metricas: dict = {
        "horario": datetime.now(UTC).isoformat(),
        "modelo": modelo,
        **(contexto or {}),
        "tokens_entrada": None,
        "tokens_saida": None,
        "custo_usd": None,
        "latencia_s": None,
        "erro": None,
    }
    inicio = time.perf_counter()
    try:
        resposta = cliente.models.generate_content(
            model=modelo,
            contents=[types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                # JSON Schema puro (com $defs e enums) gerado pelo próprio Pydantic.
                response_json_schema=schema.model_json_schema(),
            ),
        )
        uso = resposta.usage_metadata
        if uso is not None:
            metricas["tokens_entrada"] = uso.prompt_token_count
            # Tokens de raciocínio ("thinking") também são cobrados como saída.
            metricas["tokens_saida"] = (uso.candidates_token_count or 0) + (
                uso.thoughts_token_count or 0
            )
        metricas["custo_usd"] = _estimar_custo(metricas["tokens_entrada"], metricas["tokens_saida"])
        texto = resposta.text or ""
    except Exception as erro:
        metricas["erro"] = f"{type(erro).__name__}: {erro}"
        raise
    finally:
        metricas["latencia_s"] = round(time.perf_counter() - inicio, 3)
        _registrar(metricas)
    return texto, metricas
