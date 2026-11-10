# Agente de Inteligência Urbanística

Transforma a lei de uso e ocupação do solo de Londrina em uma tabela consultável, usando um LLM
para extrair os parâmetros urbanísticos de cada zona, e mede com rigor o quanto essa extração é
confiável.

**Objetivo final:** dada uma zona, o agente responde o que e como pode ser construído ali,
citando a lei.

**Fonte:** Lei nº 13.905/2024 de Londrina, Anexo II (Quadros de Parâmetros Urbanísticos de Uso e
Ocupação do Solo), [Câmara Municipal de Londrina](https://www.cml.pr.gov.br/proposicoes/Leis/0/9/0/222790).

## Resultado atual

Avaliação do prompt `extracao_v1` contra um gabarito montado à mão: 5 zonas, 84 valores
(`zona + linha + parametro`).

| métrica | resultado |
|---|---|
| Acurácia | **100%** (84/84) |
| Taxa de alucinação | **0%** |
| Acerto de notas de rodapé | **100%** |
| Falhas de validação (Pydantic) | 0 |

Custo, tokens e latência estão em [Métricas por versão do prompt](#métricas-por-versão-do-prompt).
Antes de tirar conclusões, veja as [Limitações](#limitações).

## O que é extraído

**Zonas do MVP** (uma página do Anexo II por zona):

| zona | nome | página |
|---|---|---|
| ZRC | Zona do Ribeirão Cafezal | 1 |
| ZR-2 | Zona Residencial 2 | 3 |
| ZUM-1 | Zona de Uso Misto 1 | 5 |
| ZC-1 | Zona Comercial 1 | 7 |
| ZEU-RES | Zona de Expansão Urbana Residencial | 17 |

**Parâmetros:**

| parâmetro | coluna do quadro | unidade |
|---|---|---|
| `taxa_ocupacao_terreo` | Taxa de ocupação máxima: subsolo, térreo e 1º pav | % |
| `taxa_ocupacao_demais` | Taxa de ocupação máxima: demais pavimentos | % |
| `ca_basico` | Coeficiente de Aproveitamento: básico | — |
| `ca_maximo` | Coeficiente de Aproveitamento: máximo | — |
| `gabarito` | Gabarito máximo | pavimentos |
| `permeabilidade_min` | Taxa de Permeabilidade mínima | % |
| `recuo_frontal` | Recuo mínimo | m |

Ficam fora do escopo por enquanto: Anexo III (usos permitidos), mapas, lote, frente,
afastamentos e outras cidades.

## Como funciona

```
PDF do Anexo II ──► recorte da página ──► Gemini + prompt versionado ──► JSON
                                                                          │
     gabarito manual ──► evaluate.py ◄── CSV por zona ◄── validação Pydantic
                          acurácia, alucinação, notas      (célula a célula)
```

1. **Recorte** (`extract.py`): só a página da zona vai para o modelo, em PDF.
2. **Extração** (`llm.py`): o Gemini recebe o prompt de `prompts/` e responde em JSON, com o
   schema do Pydantic imposto na própria chamada. Cada chamada registra modelo, tokens, custo,
   latência e erro em `logs/llm.jsonl`.
3. **Validação** (`schema.py`): o JSON é validado pelo Pydantic. Se o objeto inteiro falhar, a
   validação é refeita célula a célula: o que é válido é aproveitado, e cada célula inválida
   vira uma falha registrada. **Nunca um valor inventado.**
4. **Avaliação** (`evaluate.py`): compara a extração com `data/gold/gabarito.csv` e classifica
   cada valor.

### Modelo de dados

Formato longo, com chave `zona + linha + parametro`. A `linha` é a linha do quadro, e cada uma
vale para todos os usos listados nela:

| `linha` | usos cobertos |
|---|---|
| `RES-RUB` | Unifamiliar ou Bifamiliar (RUB), Multifamiliar em Condomínio (RMC-RUB) |
| `RES-RMV` | Multifamiliar vertical (RMV), RMC-RMV / RCM-RMV (só onde o quadro tem essa linha) |
| `NAO-RES` | Misto (M), CS-\*, Ind-\*, IPP e demais usos da linha |

Colunas: `zona, linha, parametro, valor, unidade, tipo_valor, nota, fonte, pagina`.

- `tipo_valor = numero`: a célula tem um número.
- `tipo_valor = nao_definido`: o quadro mostra "–". O valor fica vazio, o que **não** significa
  zero nem "sem limite".
- `tipo_valor = de_origem`: reservado para as ZEICs, que herdam o parâmetro da zona de origem
  (ainda não implementado).
- `nota`: a nota de rodapé que condiciona o valor, por exemplo
  `(b) admite 3 pavimentos se a inclinação do terreno for acima de 15%`.

### Como a avaliação classifica cada valor

| categoria | significado |
|---|---|
| `acerto` | mesmo tipo e, se for número, mesmo valor |
| `alucinacao` | o quadro não tem número, mas a extração trouxe um. **É o erro mais grave.** |
| `erro_valor` | os dois são número, mas diferentes |
| `omissao` | o quadro tem número, mas a extração disse que não há |
| `erro_tipo` | tipos não numéricos diferentes |
| `nao_extraido` | o valor não veio (falha do modelo ou da validação) |

A nota de rodapé é avaliada à parte, pela letra: (a), (b)… O texto da nota pode ser um resumo,
então só a letra precisa bater.

## Métricas por versão do prompt

| prompt | data | modelo | acurácia | alucinação | acerto de notas | tokens entrada / saída (5 zonas) | latência média |
|---|---|---|---|---|---|---|---|
| [`extracao_v1`](prompts/extracao_v1.md) | 2026-11-10 | `gemini-3.5-flash` | 100% (84/84) | 0% | 100%¹ | 11.799 / 13.864 | 14,0 s por zona |

¹ A primeira avaliação marcou 95,2% de acerto de notas por um bug na métrica, e não por erro do
modelo. O texto de 4 notas tinha "altura (H)", e o "(H)" era contado como uma letra de nota a
mais. A correção ([PR #11](https://github.com/marcos-yudi/Urbanistic-Agent/pull/11)) passou a
aceitar só letras minúsculas, como as notas do Anexo II. Reavaliada a mesma extração, o acerto
foi de 100%.

- **Custo:** zero, no nível gratuito do AI Studio.
- **Disponibilidade:** uma das 6 chamadas falhou com `503 UNAVAILABLE` (modelo sobrecarregado) e
  foi repetida. A falha fica registrada no log.

A regra do projeto: cada nova versão de prompt é um arquivo novo em `prompts/`, com a métrica
registrada aqui. Uma mudança que piora a acurácia não entra na `main`.

## Limitações

- **Amostra pequena:** são 84 valores em 5 zonas. O Anexo II tem 18 quadros, e o resultado ainda
  não diz nada sobre os outros 13. Entre eles estão as 3 ZEICs (Casoni, Heimtal e Espírito
  Santo), que herdam parâmetros da zona de origem e ainda não são tratadas.
- **Prompt escrito olhando as mesmas páginas:** o v1 foi ajustado às armadilhas desses 5 quadros
  (colunas que mudam de posição, CA mínimo × básico, recuo × afastamento). Ele não contém
  nenhum valor do gabarito, mas o teste real de generalização são as zonas que ainda não foram
  avaliadas.
- **Uma medição só:** com temperatura 0 a variação é pequena, mas ainda não foi medida com
  várias execuções.
- **Notas longas:** o modelo nem sempre resume a nota como o prompt pede. Às vezes copia o texto
  quase inteiro. A métrica por letra não pega isso.

## Como rodar

Requisitos: Python 3.13 e uma chave do [Google AI Studio](https://aistudio.google.com/).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # versões exatas do ambiente
pip install -e . --no-deps         # instala o pacote urbanistico (código em src/)
```

Crie um `.env` na raiz (ele fica fora do git):

```
GEMINI_API_KEY=sua-chave
GEMINI_MODEL=gemini-3.5-flash
# Opcional: preço em USD por 1 milhão de tokens, para estimar custo no log
# GEMINI_PRECO_ENTRADA_USD=
# GEMINI_PRECO_SAIDA_USD=
```

Baixe o Anexo II na [fonte](https://www.cml.pr.gov.br/proposicoes/Leis/0/9/0/222790) e salve como
`data/raw/ANEXO II.pdf`. Os PDFs não ficam no git.

```bash
python -m urbanistico.extract --todas                 # as 5 zonas do MVP
python -m urbanistico.extract --zona ZRC --pagina 1   # uma zona
python -m urbanistico.evaluate                        # métricas contra o gabarito
```

A extração gera `data/output/extracao_<ZONA>.csv` e `data/output/falhas_<ZONA>.csv`.

Para desenvolver:

```bash
pytest                      # testes, com o LLM mockado (não gastam chamada)
ruff check . && ruff format .
```

## Estrutura

```
data/gold/gabarito.csv       gabarito manual (84 valores, 5 zonas)
data/raw/                    PDFs da lei (fora do git)
prompts/extracao_v1.md       prompt de extração, versionado
src/urbanistico/
  llm.py                     única porta de chamada ao Gemini, com log de tokens, custo e latência
  schema.py                  schema Pydantic e regras contra alucinação
  extract.py                 recorte da página, extração e validação célula a célula
  evaluate.py                métricas contra o gabarito
tests/                       testes do schema, da extração e da avaliação
docs/                        arquitetura, custos e IAM do Google Cloud
```

## Decisões de projeto

- **Nunca inventar valor.** O que não está no documento vira nulo ou `nao_definido`. O schema
  rejeita número com `tipo_valor` não numérico e vice-versa, e confere faixas plausíveis (taxa
  entre 0 e 100, gabarito inteiro ≥ 1).
- **A página de origem não depende do modelo.** `zona`, `pagina` e `fonte` vêm de quem chama, e
  não da resposta do LLM.
- **Formato largo na extração, longo no armazenamento.** O modelo responde uma linha com os 7
  campos (fica mais difícil pular um parâmetro). O resto do pipeline usa uma linha por valor.
- **Exemplos fictícios no prompt.** Usar valores do gabarito como exemplo vazaria a avaliação.
- **Segredos só no ambiente.** Chave e modelo vêm do `.env`, que nunca vai para o git.

## Próximos passos

- [ ] Gabarito e avaliação das demais zonas do Anexo II
- [ ] Parâmetros de lote, frente e afastamentos
- [ ] `load.py`: carga no BigQuery
- [ ] Agente com *tool calling* que responde por zona citando a lei
- [ ] API (FastAPI) e demo (Streamlit)
- [ ] CI no GitHub Actions: testes, lint e avaliação a cada mudança de prompt

A infraestrutura no Google Cloud já está desenhada, com custo mínimo e corte automático de
faturamento:

- [`docs/gcp_custos.md`](docs/gcp_custos.md): regras de custo e teto de R$ 50/mês
- [`docs/gcp_corte_faturamento.md`](docs/gcp_corte_faturamento.md): implementação e teste do corte
- [`docs/gcp_iam.md`](docs/gcp_iam.md): contas de serviço com menor privilégio

## Desenvolvimento com Claude Code

Este projeto está sendo desenvolvido com o uso do [Claude Code](https://claude.com/claude-code),
assistente de programação da Anthropic. As regras de trabalho com o assistente estão no
[`CLAUDE.md`](CLAUDE.md). As decisões de escopo, o gabarito, os prompts e a análise de erros
são de autoria do projeto. O código gerado com o assistente é revisado antes de entrar na `main`.
