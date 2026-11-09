# Google Cloud: custo mínimo e corte automático

Regras de custo do projeto para quando o Google Cloud entrar (GCS, BigQuery, Cloud Run).
Decisão do Yudi em 2026-11-09. Valem para qualquer infraestrutura proposta no projeto.

## Regras

1. **Gratuito sempre que possível.** Usar o nível gratuito de cada serviço. Quando não houver,
   escolher a opção mais barata.
2. **Nada ligado sem uso.** Os serviços só rodam enquanto alguém está executando o programa.
   Nenhuma VM, nenhuma instância mínima, nada rodando à toa.
3. **Teto de R$ 50 por mês, com corte real.** Ao atingir o limite, o projeto **é desligado
   de fato**: o faturamento é desvinculado e todos os serviços pagos param até o mês seguinte.
   **Só alertar não basta.**

## Por que um orçamento sozinho não resolve

No Google Cloud, um orçamento (*budget*) **só envia alertas**: ele não bloqueia nem limita
gastos. Para que o serviço pare, é preciso automatizar o corte:

```
Orçamento (BRL) ──► tópico Pub/Sub ──► Cloud Run function ──► Cloud Billing API
  gasto atual        notificação          compara o gasto        desvincula o faturamento
  do mês             várias vezes ao dia  com o limite           do projeto (corte)
```

## Configuração do corte

1. **Conta de faturamento em BRL**, para o orçamento e o limite ficarem em reais.
2. **Orçamento** no projeto, com valor de R$ 50/mês e período mensal. Alertas por e-mail em
   50%, 90% e 100%, só para acompanhamento.
3. **Ligar o orçamento a um tópico Pub/Sub** (opção "Conectar um tópico do Pub/Sub ao
   orçamento"). O Google publica no tópico o gasto atual (`costAmount`) e o valor do orçamento
   (`budgetAmount`) várias vezes ao dia.
4. **Função de corte** (Cloud Run function, disparada pelo tópico):
   - lê `costAmount` da mensagem;
   - se `costAmount >= LIMITE_CORTE`, chama `projects.updateBillingInfo` da Cloud Billing API
     com `billingAccountName: ""`, o que desvincula o faturamento do projeto;
   - se o faturamento já estiver desvinculado, não faz nada (a mensagem chega várias vezes).
5. **Conta de serviço da função** com permissão para desvincular o faturamento, por exemplo
   o papel *Project Billing Manager* no projeto. A função não recebe nenhuma outra permissão.
6. **`LIMITE_CORTE = R$ 45`**, e não R$ 50. Os custos aparecem no faturamento com atraso de
   algumas horas, então o gasto real pode passar um pouco do valor que disparou o corte. A folga
   de R$ 5 serve para o total do mês não ultrapassar R$ 50.
7. **Testar o corte** antes de usar o projeto de verdade: publicar no tópico uma mensagem falsa
   com `costAmount` acima do limite e conferir que o faturamento foi desvinculado.

## O que acontece no corte

- Todos os serviços pagos do projeto param: Cloud Run, as consultas cobradas do BigQuery e o
  armazenamento além do gratuito. A própria função de corte deixa de rodar, e isso não é problema.
- **Risco:** com o faturamento desvinculado por muito tempo, o Google pode apagar recursos
  pagos. Os dados que importam (gabarito, prompts, código) ficam no git. As saídas podem ser
  geradas de novo pelo pipeline.
- **Religar:** no mês seguinte, vincular a conta de faturamento ao projeto de novo, manualmente
  (Faturamento → Gerenciar projetos). O religamento é manual de propósito, para que alguém veja
  por que o teto foi atingido.

## Escolhas por serviço

| serviço | configuração |
|---|---|
| Cloud Run (API) | `min-instances=0` (escala a zero), `max-instances` baixo (ex.: 2) |
| Pipeline | Cloud Run **Jobs**, disparado manualmente ou pelo GitHub Actions; nada agendado à toa |
| BigQuery | nível gratuito (10 GB armazenados, 1 TB consultado/mês); `maximum_bytes_billed` em toda consulta |
| Cloud Storage | região com nível gratuito (ex.: `us-central1`), classe Standard, poucos MB |
| Gemini | chave do AI Studio no nível gratuito (fica fora da conta do GCP; se um dia usar o nível pago ligado a este projeto, o corte também o desliga) |
| VMs (Compute Engine) | **não usar** |

## Checklist antes de ligar o GCP

- [ ] Conta de faturamento em BRL
- [ ] Orçamento de R$ 50/mês ligado a um tópico Pub/Sub
- [ ] Função de corte com `LIMITE_CORTE = 45` e a conta de serviço com permissão mínima
- [ ] Corte testado com mensagem falsa
- [ ] Cloud Run com `min-instances=0` e `maximum_bytes_billed` nas consultas do BigQuery
