# Urbanistic-Agent

Intenções com o projeto.
- Transformar a lei de uso e ocupação do solo de Londrina em uma tabela.
- Parâmetros:
  - Taxa de ocupação.
  - Coeficiente de aproveitamento.
  - Gabarito de Altura.
  - Recuo frontal.
  - Taxa de permeabilidade. 
- Medição de acurácia, alucinação etc da LLM.
- Pipeline: PDF bruto --> extração --> banco --> consulta.

Resultado esperado:
- Dado uma zona, o modelo de LLM diz o que e como pode ser construído naquele local.

## Métricas por versão do prompt

Avaliação com `python -m urbanistico.evaluate` contra `data/gold/gabarito.csv`: 5 zonas do MVP
(ZRC, ZR-2, ZUM-1, ZC-1, ZEU-RES), 84 chaves `zona + linha + parametro`.

| prompt | data | modelo | acurácia | alucinação | acerto de notas | tokens entrada / saída (total) | latência média |
|---|---|---|---|---|---|---|---|
| `extracao_v1` | 2026-11-10 | `gemini-3.5-flash` | 100% (84/84) | 0% | 95,2%¹ | 11.799 / 13.864 | 14,0 s por zona |

¹ As 4 divergências de nota (recuo frontal de ZUM-1 e ZC-1) têm a letra certa. O texto obtido
contém "altura (H)", que a métrica conta como uma letra de nota a mais. Comparando só as letras
de nota, o acerto seria 100%.

Custo: zero, no nível gratuito do AI Studio. Uma chamada da ZEU-RES falhou com
`503 UNAVAILABLE` (modelo sobrecarregado) e foi repetida; a falha está registrada em
`logs/llm.jsonl`.

## Desenvolvimento com Claude Code

Este projeto está sendo desenvolvido com o uso do [Claude Code](https://claude.com/claude-code),
assistente de programação da Anthropic. As regras de trabalho com o assistente estão no
[`CLAUDE.md`](CLAUDE.md). As decisões de escopo, o gabarito, os prompts e a análise de erros
são de autoria do projeto. O código gerado com o assistente é revisado antes de entrar na `main`.
