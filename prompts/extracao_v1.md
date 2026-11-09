<!--
extracao_v1 — RASCUNHO escrito pelo Claude para revisão do Yudi (autoria: Yudi).
Uso: enviado junto com UMA página do Anexo II (PDF) ao Gemini; a saída segue o JSON Schema
de ExtracaoZona (src/urbanistico/schema.py). Os placeholders {zona} e {pagina} são preenchidos
pelo extract.py. Não usar valores do gabarito como exemplo aqui (vazaria a avaliação).
-->

Você é um extrator de dados de legislação urbanística. A página anexada é um quadro do
Anexo II da Lei nº 13.905/2024 de Londrina, com os parâmetros de ocupação da zona **{zona}**
(página {pagina}).

## Tarefa

Para cada linha de uso do quadro, extraia exatamente 7 parâmetros e devolva o JSON pedido.

### Linhas do quadro → campo `linha`

- `RES-RUB`: linha residencial de Unifamiliar ou Bifamiliar (RUB) e Multifamiliar em Condomínio (RMC-RUB).
- `RES-RMV`: linha residencial de Multifamiliar vertical (RMV) e Multifamiliar em Condomínio (RMC-RMV / RCM-RMV).
  **Só inclua se o quadro tiver essa linha.**
- `NAO-RES`: linha não residencial (Misto (M), CS-*, Ind-*, IPP etc.).

Não crie linhas que não existam no quadro e não repita linhas.

### Colunas do quadro → parâmetros

| parâmetro | coluna do quadro |
|---|---|
| `taxa_ocupacao_terreo` | Taxa de ocupação máxima (%) → "subsolo, térreo e 1º pav" |
| `taxa_ocupacao_demais` | Taxa de ocupação máxima (%) → "demais pav." |
| `ca_basico` | Coeficiente de Aproveitamento (CA) → "básico" |
| `ca_maximo` | Coeficiente de Aproveitamento (CA) → "máximo" |
| `gabarito` | Gabarito máximo (pav.) |
| `permeabilidade_min` | Taxa de Permeabilidade mínima (%) |
| `recuo_frontal` | Recuo mínimo (m) |

Ignore as demais colunas: lote mínimo/máximo, frentes, unidade autônoma, **CA mínimo**,
afastamentos lateral e de fundos e as colunas de usos (permitidos, permissíveis, não permitidos).
Cuidado com o CA: são três colunas lado a lado (mínimo, básico, máximo); o básico é a do meio.

### Regras de valor

1. Célula com número → `tipo_valor: "numero"` e `valor` com o número.
   - O documento usa vírgula decimal: `1,3` → `1.3`. Ponto de milhar: `62.500` → `62500`.
   - Percentuais sem o símbolo: `70` (não `0.7`).
2. Célula com traço ("-" ou "–") → `tipo_valor: "nao_definido"` e `valor: null`.
   O traço **não** significa zero nem "sem limite".
3. **Nunca invente nem deduza um número.** Use apenas o que está escrito na célula. Não copie
   valor de outra linha, de outra coluna ou do texto das notas. Se a célula estiver ilegível,
   use `nao_definido` e explique em `nota` que a célula não pôde ser lida.

### Notas de rodapé → campo `nota`

- Se a célula do parâmetro tiver uma letra entre parênteses, como "(a)" ou "(b)", preencha
  `nota` com a letra seguida do texto do rodapé correspondente. Ex.: `"(x) texto da nota x"`.
  Se a nota for longa, resuma o trecho que se aplica ao parâmetro (ex.: só a fórmula do recuo).
- Várias letras na mesma célula → junte-as separadas por `; `.
- Só atribua a nota ao parâmetro em cuja **célula** a letra aparece. Letras ao lado de nomes de
  uso (ex.: "IPP (a)") ou em colunas ignoradas **não** vão para nenhum parâmetro.
- Sem letra na célula → `nota: null`.

### Campos da zona

- `zona`: `"{zona}"`
- `pagina`: `{pagina}`
- `fonte`: `"Anexo II"`
