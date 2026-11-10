# Corte de faturamento: implementação

Passo a passo para implementar o corte automático descrito em [`gcp_custos.md`](gcp_custos.md).
As regras, o motivo do limite de R$ 45, o que acontece no corte e as escolhas por serviço estão
lá. Aqui ficam só os comandos, o código, o teste e o religamento.

```
Orçamento (R$ 50, BRL) ──publica o custo──▶ Pub/Sub `orcamento-alertas`
                                                  │
                                                  ▼
                              Cloud Run function `cortar-faturamento`
                              custo ≥ LIMITE_CORTE? → desvincula o faturamento
```

## Variáveis

```bash
PROJETO=meu-projeto-gcp
CONTA_FATURAMENTO=XXXXXX-XXXXXX-XXXXXX   # gcloud billing accounts list
REGIAO=us-central1
TOPICO=orcamento-alertas
SA_CORTE=sa-corte-faturamento@$PROJETO.iam.gserviceaccount.com
```

## 1. Tópico e orçamento

```bash
gcloud pubsub topics create $TOPICO --project=$PROJETO

# A moeda do orçamento precisa ser a da conta de faturamento (BRL).
gcloud billing budgets create --billing-account=$CONTA_FATURAMENTO \
  --display-name="teto-urbanistico" \
  --budget-amount=50BRL \
  --filter-projects=projects/$PROJETO \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0 \
  --notifications-rule-pubsub-topic=projects/$PROJETO/topics/$TOPICO
```

Se o `gcloud` reclamar de permissão para publicar no tópico, ligue o tópico pelo console
(*Faturamento → Orçamentos e alertas → teto-urbanistico → Conectar um tópico do Pub/Sub*). O console
dá a permissão de publicação sozinho.

## 2. Conta de serviço da function

Ela só precisa poder desvincular o faturamento **deste** projeto:

```bash
gcloud iam service-accounts create sa-corte-faturamento --project=$PROJETO \
  --display-name="Corte de faturamento"

gcloud projects add-iam-policy-binding $PROJETO \
  --member="serviceAccount:$SA_CORTE" --role="roles/billing.projectManager" --condition=None
```

O `billing.projectManager` permite vincular e desvincular o faturamento do projeto, sem acesso à
conta de faturamento em si (pagamentos, outros projetos).

## 3. Código da function

`infra/corte_faturamento/main.py`:

```python
"""Desliga o faturamento do projeto quando o custo do mês chega ao limite."""

import base64
import json
import os

import functions_framework
from google.cloud import billing_v1

PROJETO = os.environ["PROJETO"]
LIMITE_CORTE = float(os.environ.get("LIMITE_CORTE", "45"))
# SIMULAR=true só registra no log o que faria; útil no primeiro teste.
SIMULAR = os.environ.get("SIMULAR", "false").lower() == "true"


@functions_framework.cloud_event
def cortar_faturamento(evento):
    dados = json.loads(base64.b64decode(evento.data["message"]["data"]))
    custo = float(dados["costAmount"])
    moeda = dados["currencyCode"]

    # Moeda errada quebra a comparação com o limite: falha alto em vez de ignorar.
    if moeda != "BRL":
        raise ValueError(f"orçamento em {moeda}, esperado BRL; corte não avaliado")

    print(f"custo do mês: R$ {custo:.2f} (limite R$ {LIMITE_CORTE:.2f})")
    if custo < LIMITE_CORTE:
        return

    cliente = billing_v1.CloudBillingClient()
    nome = f"projects/{PROJETO}"
    # A mensagem chega várias vezes ao dia: se já está desligado, não faz nada.
    if not cliente.get_project_billing_info(name=nome).billing_enabled:
        print("faturamento já está desligado")
        return
    if SIMULAR:
        print("SIMULAR=true: o faturamento SERIA desligado agora")
        return

    cliente.update_project_billing_info(
        name=nome,
        project_billing_info=billing_v1.ProjectBillingInfo(billing_account_name=""),
    )
    print(f"faturamento DESLIGADO em {PROJETO} (custo R$ {custo:.2f})")
```

`infra/corte_faturamento/requirements.txt`:

```
functions-framework==3.*
google-cloud-billing==1.*
```

## 4. Deploy

Comece com `SIMULAR=true`:

```bash
gcloud functions deploy cortar-faturamento --gen2 --project=$PROJETO --region=$REGIAO \
  --runtime=python312 --source=infra/corte_faturamento --entry-point=cortar_faturamento \
  --trigger-topic=$TOPICO \
  --service-account=$SA_CORTE --trigger-service-account=$SA_CORTE \
  --set-env-vars=PROJETO=$PROJETO,LIMITE_CORTE=45,SIMULAR=true \
  --memory=256Mi --max-instances=1

# O gatilho do Pub/Sub chama a function como a SA_CORTE.
gcloud functions add-invoker-policy-binding cortar-faturamento --gen2 \
  --project=$PROJETO --region=$REGIAO --member="serviceAccount:$SA_CORTE"
```

## 5. Testar antes de usar o projeto

Faça o teste com o projeto ainda vazio. Nesse estado, o corte não derruba nada importante.

```bash
# a) Abaixo do limite: a function só registra o custo.
gcloud pubsub topics publish $TOPICO --project=$PROJETO \
  --message='{"budgetDisplayName":"teste","costAmount":10.0,"budgetAmount":50.0,"currencyCode":"BRL"}'

# b) Acima do limite com SIMULAR=true: o log diz "SERIA desligado".
gcloud pubsub topics publish $TOPICO --project=$PROJETO \
  --message='{"budgetDisplayName":"teste","costAmount":46.0,"budgetAmount":50.0,"currencyCode":"BRL"}'

gcloud functions logs read cortar-faturamento --gen2 --project=$PROJETO --region=$REGIAO --limit=20
```

c) Corte real: faça o redeploy com `SIMULAR=false` (mesmo comando do passo 4) e publique de novo a
mensagem de R$ 46. Depois confira:

```bash
gcloud billing projects describe $PROJETO   # deve mostrar billingEnabled: false
```

d) Religue o projeto (seção abaixo) e confirme que voltou `billingEnabled: true`.

O corte só está pronto quando os passos de a) a d) funcionaram. Depois disso, a function fica em
produção com `SIMULAR=false`.

## Religar o projeto (manual)

```bash
gcloud billing projects link $PROJETO --billing-account=$CONTA_FATURAMENTO
```

Atenção: o orçamento é **mensal**. Se você religar no mesmo mês do corte, o custo acumulado
continua acima do limite, e a próxima mensagem do orçamento desliga o projeto de novo. Há duas
saídas:

- **esperar o mês seguinte** (o padrão, coerente com o teto), ou
- religar de forma consciente no mesmo mês: subir o `LIMITE_CORTE` da function **e** o valor do
  orçamento. Isso aumenta o teto e precisa de decisão explícita.

Antes de religar, descubra o que gastou (*Faturamento → Relatórios*, agrupando por serviço) e
corrija a causa.

## Limitação

O custo chega ao orçamento com atraso, que pode passar de um dia. A folga de R$ 5 cobre o uso
normal deste projeto, mas um pico muito rápido (ex.: um laço chamando o Gemini pago) pode passar
de R$ 50 antes de o corte disparar. Por isso as barreiras de [`gcp_custos.md`](gcp_custos.md)
(escala a zero, `maximum_bytes_billed`, `max-instances`) continuam sendo a primeira defesa.
