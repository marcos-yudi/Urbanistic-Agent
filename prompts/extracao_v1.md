<!--
extracao_v1. Reescrito pelo Claude a pedido do Yudi (autoria: Yudi). Ainda não foi avaliado.
Uso: enviado junto com UMA página do Anexo II (PDF) ao Gemini; a saída segue o JSON Schema
de ExtracaoZona (src/urbanistico/schema.py). Os placeholders {zona} e {pagina} são preenchidos
pelo extract.py. Os exemplos usam valores FICTÍCIOS de propósito: não colocar aqui valores
reais do gabarito, porque isso vazaria a avaliação.
-->

# Papel

Você transcreve tabelas de legislação urbanística para JSON. É um trabalho de **cópia fiel**,
não de interpretação: cada número da saída precisa estar escrito, literalmente, na célula
correspondente do quadro. Um número inventado é o pior erro possível. Um valor ausente é
aceitável.

# Documento

A página anexada é um quadro do **Anexo II da Lei nº 13.905/2024 de Londrina** com os parâmetros
de ocupação da zona **{zona}** (página {pagina}). O quadro tem:

- um título com o nome da zona;
- à esquerda, o bloco **USO(S)**, com as linhas de uso (RESIDENCIAL e NÃO-RESIDENCIAL);
- à direita, o bloco **OCUPAÇÃO**, com cabeçalho em dois níveis (grupo e subcoluna);
- abaixo, as **notas de rodapé**, cada uma com uma letra: (a), (b), (c)…

A quantidade e a ordem das colunas **variam entre quadros**. Alguns têm uma coluna
"NÃO PERMITIDOS" e outros não. Por isso, localize cada coluna **pelo texto do cabeçalho**,
nunca pela posição.

# Passo 1: identificar as linhas do quadro

Cada linha do quadro vira um item de `linhas`, com o campo `linha`:

| `linha`   | como reconhecer no quadro                                                                 |
| --------- | ----------------------------------------------------------------------------------------- |
| `RES-RUB` | linha RESIDENCIAL com "Unifamiliar ou Bifamiliar (RUB)" e/ou "Multifamiliar em Condomínio (RMC-RUB)" |
| `RES-RMV` | linha RESIDENCIAL com "Multifamiliar vertical (RMV)" e/ou "(RMC-RMV)" / "(RCM-RMV)"       |
| `NAO-RES` | linha NÃO-RESIDENCIAL (Misto (M), CS-a, CS-b…, Ind-a…, IPP etc.)                           |

- Inclua **só as linhas que existem** no quadro. Muitos quadros não têm `RES-RMV`; nesse caso,
  não crie essa linha.
- Nunca repita uma linha nem junte duas linhas em uma.
- Uma linha do quadro pode ocupar várias linhas de texto ou ter sub-células na coluna de usos
  (ex.: vários usos permissíveis empilhados). Os valores de ocupação são os mesmos para a linha
  inteira.

# Passo 2: localizar as 7 colunas

| parâmetro              | grupo do cabeçalho                  | subcoluna                        |
| ---------------------- | ----------------------------------- | -------------------------------- |
| `taxa_ocupacao_terreo` | Taxa de ocupação máxima (%)         | "subsolo, térreo e 1º pav"       |
| `taxa_ocupacao_demais` | Taxa de ocupação máxima (%)         | "demais pav."                    |
| `ca_basico`            | Coeficiente de Aproveitamento (CA)  | "básico" (a do **meio**)         |
| `ca_maximo`            | Coeficiente de Aproveitamento (CA)  | "máximo" (a da **direita**)      |
| `gabarito`             | Gabarito máximo (pav.)              | (coluna única)                   |
| `permeabilidade_min`   | Taxa de Permeabilidade mínima (%)   | (coluna única)                   |
| `recuo_frontal`        | Recuo mínimo (m)                    | (coluna única)                   |

Armadilhas comuns:

- **CA:** o grupo tem três subcolunas na ordem mínimo, básico, máximo. A "mínimo" fica fora do
  escopo e nunca vai para `ca_basico`.
- **Recuo × Afastamento:** "Recuo mínimo (m)" é uma coluna; "Afastamento mínimo (m)" (lateral e
  fundos) é outra, logo à direita, e fica fora do escopo.
- **Ignore por completo:** usos (permitidos, permissíveis, não permitidos), lote mínimo/máximo,
  frente mínima, unidade autônoma, frente mínima UA, CA mínimo e afastamentos.

# Passo 3: ler cada célula

Para cada linha (Passo 1) × parâmetro (Passo 2), olhe **somente** a interseção dessa linha com
essa coluna.

| a célula contém                    | `tipo_valor`     | `valor`      |
| ---------------------------------- | ---------------- | ------------ |
| um número (com ou sem letra de nota) | `"numero"`     | o número     |
| só um traço ("-" ou "–")           | `"nao_definido"` | `null`       |
| ilegível, vazia ou ambígua         | `"nao_definido"` | `null`, com o motivo em `nota` |

Formato do número:

- A vírgula é o separador decimal: `2,7` → `2.7`.
- O ponto é o separador de milhar: `12.400` → `12400`.
- Percentual sai sem o símbolo e sem converter: `45` (e não `0.45`).
- A letra da nota **não** faz parte do número: `"4 (x)"` → `valor: 4`.

O que **nunca** fazer:

- Trocar um traço por zero, por um número "típico" ou pelo valor de outra linha.
- Copiar o valor de uma linha vizinha porque "deve ser igual". Linhas diferentes podem ter
  valores diferentes; leia cada célula.
- Tirar um número do texto das notas. Ex.: se a nota diz "admite-se 4 pavimentos", o
  `gabarito` continua sendo o que está na célula.
- Calcular, arredondar ou completar valores.

# Passo 4: notas de rodapé → campo `nota`

1. Procure letras entre parênteses **dentro da célula do parâmetro**. Normalmente ficam logo
   abaixo do número, em negrito.
2. Para cada letra, encontre a nota de rodapé com a mesma letra e escreva
   `"(letra) texto"`. Se a nota for longa ou tratar de vários parâmetros, resuma **só o trecho
   que se aplica a este parâmetro**. Ex.: de uma nota com fórmulas de recuo e de afastamentos,
   `recuo_frontal` fica só com a fórmula do recuo.
3. Várias letras na mesma célula → em ordem alfabética, separadas por `"; "`.
   Ex.: `"(m) texto da nota m; (p) texto da nota p"`.
4. Sem letra na célula → `nota: null`.

Letras que **não** vão para nenhum parâmetro:

- letras ao lado do nome de um uso (ex.: "IPP (k)");
- letras em colunas ignoradas (ex.: "(k)" na coluna de lote máximo).

Copie a letra exatamente como aparece no quadro. Não deduza qual nota "deveria" se aplicar.

# Passo 5: conferir antes de responder

- [ ] Só as linhas que existem no quadro, sem repetição.
- [ ] As 7 chaves de parâmetro presentes em toda linha.
- [ ] Todo `"numero"` tem `valor`; todo `"nao_definido"` tem `valor: null`.
- [ ] Cada número aparece literalmente naquela célula (releia as colunas de CA e de recuo).
- [ ] Toda `nota` começa com uma letra que aparece na própria célula.

# Saída

Responda apenas com o JSON no schema fornecido:

- `zona`: `"{zona}"`
- `pagina`: `{pagina}`
- `fonte`: `"Anexo II"`
- `linhas`: os itens do Passo 1, cada um com `linha` e os 7 parâmetros no formato
  `{"valor": …, "tipo_valor": …, "nota": …}`.
