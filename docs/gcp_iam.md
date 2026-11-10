# Papéis IAM no Google Cloud

Quem acessa o quê no GCP e com quais papéis. Princípio: **menor privilégio**. Cada parte do
sistema tem a própria identidade e só os papéis de que precisa, dados no recurso mais específico
possível.

## Decisão

Duas contas de serviço, uma por função. Nenhuma usa chave JSON.

| conta de serviço | quem usa | nível do projeto | dataset `urbanistico` | bucket dos PDFs |
|---|---|---|---|---|
| `sa-pipeline` | GitHub Actions (`pipeline.yml`: `ingest.py` → `load.py`) | `roles/bigquery.jobUser` | `roles/bigquery.dataEditor` | `roles/storage.objectAdmin` |
| `sa-agente` | API FastAPI e Streamlit (Cloud Run) | `roles/bigquery.jobUser` | `roles/bigquery.dataViewer` | nenhum |
| Yudi (conta pessoal) | desenvolvimento e administração | Owner | — | — |

### Por quê

- **Duas contas em vez de uma.** O agente fica exposto na internet pela API. Se ele for
  comprometido, só consegue ler: não apaga nem altera a tabela de parâmetros.
- **`bigquery.jobUser` e não `bigquery.user`.** Rodar uma consulta ou um *load job* exige criar
  um job, e o `jobUser` permite só isso. O `bigquery.user` também deixa criar datasets e listar
  todos os do projeto, o que nenhuma das contas precisa.
- **Papéis de dados no dataset, nunca no projeto.** No nível do projeto, o `dataEditor` daria
  escrita em todo dataset que vier a existir. Dado no `urbanistico`, vale só ali.
- **`storage.objectAdmin` só no bucket.** O `ingest.py` grava e substitui PDFs (por isso não
  basta o `objectCreator`), mas só naquele bucket.
- **Sem chave JSON.** O GitHub Actions autentica por *Workload Identity Federation* (token de
  curta duração, restrito a este repositório), e o Cloud Run usa a conta anexada ao serviço.
  Assim, nenhum segredo de GCP vai para o `.env`, para os *secrets* do GitHub ou para o git.

### Custo

Quem tem `jobUser` consegue gastar processamento do BigQuery. Há três barreiras, em camadas:

1. `maximum_bytes_billed` no `QueryJobConfig` de toda consulta feita pelo código (ex.: 100 MB).
   A consulta que passar disso falha sem cobrar.
2. Uma cota personalizada no projeto: *BigQuery API → Query usage per day* (ex.: 10 GB/dia).
3. O corte de faturamento em R$ 45, a última barreira (`docs/gcp_custos.md` e `docs/gcp_corte_faturamento.md`).

## Como aplicar

Os comandos abaixo rodam uma vez, ao configurar o projeto. Ajuste as variáveis antes.

```bash
PROJETO=meu-projeto-gcp
NUMERO_PROJETO=$(gcloud projects describe $PROJETO --format='value(projectNumber)')
REGIAO=southamerica-east1
BUCKET=gs://$PROJETO-pdfs
REPO_GITHUB=MarcosYudi/Urbanistic-Agent

SA_PIPELINE=sa-pipeline@$PROJETO.iam.gserviceaccount.com
SA_AGENTE=sa-agente@$PROJETO.iam.gserviceaccount.com
```

### 1. Contas de serviço

```bash
gcloud iam service-accounts create sa-pipeline --project=$PROJETO \
  --display-name="Pipeline: ingestão e carga"
gcloud iam service-accounts create sa-agente --project=$PROJETO \
  --display-name="Agente: só leitura"
```

### 2. Nível do projeto: só `jobUser`

```bash
for SA in $SA_PIPELINE $SA_AGENTE; do
  gcloud projects add-iam-policy-binding $PROJETO \
    --member="serviceAccount:$SA" --role="roles/bigquery.jobUser" --condition=None
done
```

### 3. Nível do dataset

Os papéis de dataset são dados com DCL no próprio BigQuery, que é a forma mais direta de dar
acesso a um dataset:

```bash
bq query --project_id=$PROJETO --use_legacy_sql=false "
GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`$PROJETO.urbanistico\`
  TO 'serviceAccount:$SA_PIPELINE';
GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`$PROJETO.urbanistico\`
  TO 'serviceAccount:$SA_AGENTE';
"
```

### 4. Nível do bucket

```bash
gcloud storage buckets add-iam-policy-binding $BUCKET \
  --member="serviceAccount:$SA_PIPELINE" --role="roles/storage.objectAdmin"
```

### 5. GitHub Actions sem chave (Workload Identity Federation)

```bash
gcloud iam workload-identity-pools create github --project=$PROJETO \
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc repo --project=$PROJETO \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == '$REPO_GITHUB'"

# Só este repositório pode se passar pela sa-pipeline.
gcloud iam service-accounts add-iam-policy-binding $SA_PIPELINE --project=$PROJETO \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$NUMERO_PROJETO/locations/global/workloadIdentityPools/github/attribute.repository/$REPO_GITHUB"
```

No workflow (`.github/workflows/pipeline.yml`):

```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: projects/<NUMERO_PROJETO>/locations/global/workloadIdentityPools/github/providers/repo
      service_account: sa-pipeline@<PROJETO>.iam.gserviceaccount.com
```

### 6. Cloud Run com a conta do agente

```bash
gcloud run deploy agente-urbanistico --project=$PROJETO --region=$REGIAO \
  --service-account=$SA_AGENTE --min-instances=0 ...
```

O `--min-instances=0` deixa o serviço escalar a zero, em linha com a regra de custo mínimo.

## Verificação

Para fazer os testes como cada conta, a sua conta pessoal precisa de
`roles/iam.serviceAccountTokenCreator` nelas.

```bash
# sa-agente: a leitura funciona...
bq query --impersonate_service_account=$SA_AGENTE --use_legacy_sql=false \
  "SELECT COUNT(*) FROM \`$PROJETO.urbanistico.parametros\`"
# ...e a escrita precisa FALHAR com "Access Denied".
bq query --impersonate_service_account=$SA_AGENTE --use_legacy_sql=false \
  "DELETE FROM \`$PROJETO.urbanistico.parametros\` WHERE FALSE"

# sa-pipeline: não pode criar dataset novo (precisa FALHAR).
bq mk --impersonate_service_account=$SA_PIPELINE --dataset $PROJETO:teste_indevido

# No nível do projeto, as duas contas devem ter só roles/bigquery.jobUser.
gcloud projects get-iam-policy $PROJETO --flatten="bindings[].members" \
  --filter="bindings.members:sa-" --format="table(bindings.role, bindings.members)"
```

## Fora deste documento

- A conta da Cloud Run function que corta o faturamento precisa de `roles/billing.projectManager`
  (ou `billing.admin` na conta de faturamento). Comandos em `docs/gcp_corte_faturamento.md`.
- A chave do Gemini (`GEMINI_API_KEY`) não é IAM do GCP: fica no `.env` local e, no Cloud Run e no
  Actions, no Secret Manager ou nos *secrets* do GitHub. Nesse caso, a conta que lê o segredo
  precisa de `roles/secretmanager.secretAccessor` só naquele segredo.
