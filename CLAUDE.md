# Agente de Inteligência Urbanística

Pipeline que extrai parâmetros urbanísticos da lei de uso e ocupação do solo de Londrina (Lei nº 13.905/2024, Anexo II) com LLM, valida, guarda no BigQuery e mede a acurácia contra um gabarito manual. Projeto de portfólio do Yudi (dados + engenharia de IA).

## Escopo atual (MVP)

- Fonte: **Anexo II** apenas. Cada quadro ocupa exatamente uma página, uma zona por página.
- Zonas do MVP e páginas: ZRC (1), ZR-2 (3), ZUM-1 (5), ZC-1 (7), ZEU-RES (17).
- Parâmetros: `taxa_ocupacao_terreo`, `taxa_ocupacao_demais`, `ca_basico`, `ca_maximo`, `gabarito`, `permeabilidade_min`, `recuo_frontal`.
- Fora do escopo por enquanto: Anexo III (usos permitidos), mapas, outras cidades, afastamentos/lote/frente (entram na semana 1).

## Stack

Python · `google-genai` (Gemini) · Pydantic · pdfplumber / PyMuPDF · pandas · Google Cloud Storage · BigQuery · FastAPI · Docker · Streamlit · GitHub Actions · pytest · ruff

## Estrutura

```
data/raw/            PDFs (fora do git)
data/gold/gabarito.csv
prompts/             versões do prompt de extração (extracao_v1.md, v2...)
src/urbanistico/     ingest, parse, schema, llm, extract, load, evaluate, agent
api/main.py          FastAPI
app/streamlit_app.py
sql/                 create_tables.sql, consultas.sql
notebooks/
tests/
.github/workflows/   ci.yml, eval.yml, pipeline.yml
```

## Comandos

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest                      # testes
ruff check . && ruff format .
python -m urbanistico.evaluate   # acurácia contra o gabarito
```

Após instalar uma biblioteca nova: `pip freeze > requirements.txt`.

## Modelo de dados

**Chave:** `zona` + `linha` + `parametro`.

`linha` = linha do quadro do Anexo II, e cada uma vale para todos os usos listados nela:

| linha | usos cobertos |
|---|---|
| `RES-RUB` | RUB, RMC-RUB |
| `RES-RMV` | RMV, RMC-RMV / RCM-RMV (só onde o quadro tem essa linha) |
| `NAO-RES` | M, CS-*, Ind-*, IPP e demais listados na linha |

`gabarito.csv` (formato longo, uma linha por valor):
`zona, linha, parametro, valor, unidade, tipo_valor, nota, fonte, pagina`

- `tipo_valor`: `numero` | `nao_definido` (o quadro mostra "–") | `de_origem` (ZEICs, futuro).
- `nao_definido` tem `valor` vazio. Não é zero e não é "sem limite".
- `nota`: texto da nota de rodapé que condiciona o valor, por exemplo "(b) admite 3 pavimentos se a inclinação for acima de 15%".
- Decimais com **ponto** (`1.3`), nunca vírgula.

## Regras do projeto

- **Nunca inventar valor.** Se não estiver no documento, o valor é nulo ou `nao_definido`. Alucinação é a métrica mais grave.
- Todo valor extraído guarda a **página de origem**.
- A saída do LLM é sempre JSON validado pelo Pydantic. O que falhar na validação vira nulo e é registrado no log.
- Toda chamada ao LLM passa por `llm.py`, que registra tokens, custo, latência e erros.
- Modelo e chaves vêm de variáveis de ambiente (`GEMINI_API_KEY`, `GEMINI_MODEL`), via `.env`. **Nunca** colocar chaves, senhas ou `.env` no código ou no git.
- Prompts ficam em `prompts/`, versionados. Nova versão = novo arquivo + métrica registrada no README.
- Uma mudança que **piora a acurácia** do `evaluate.py` não entra na `main`.

## Como trabalhar comigo

- **Planeje antes de codar.** Para qualquer tarefa com mais de um arquivo, proponha o plano e espere aprovação.
- **Partes de autoria do Yudi:** `prompts/`, `schema.py`, a lógica de métricas do `evaluate.py` e a análise de erros. Nessas partes, revise, sugira e explique, mas não reescreva sem pedido explícito.
- Mudanças pequenas e focadas, uma tarefa por vez. Não altere arquivos fora do escopo pedido.
- Para cada mudança, diga **como verificar** (teste, comando ou métrica).
- Explique escolhas técnicas não óbvias em uma ou duas frases.
- Escreva código e comentários em português, com nomes de variáveis em português sem acento (como `taxa_ocupacao`).
- Commits no formato Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), um por tarefa. Uma branch por funcionalidade.
- Não faça `git push` nem altere a `main` sem pedir.
