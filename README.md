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

## Desenvolvimento com Claude Code

Este projeto está sendo desenvolvido com o uso do [Claude Code](https://claude.com/claude-code),
assistente de programação da Anthropic. As regras de trabalho com o assistente estão no
[`CLAUDE.md`](CLAUDE.md). As decisões de escopo, o gabarito, os prompts e a análise de erros
são de autoria do projeto. O código gerado com o assistente é revisado antes de entrar na `main`.
