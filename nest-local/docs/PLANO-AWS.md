# Plano para rodar o Nest (Libnest2D) na AWS

Este documento descreve os passos para implantar o projeto **nest-local** diretamente na AWS, substituindo os serviços locais (ElasticMQ, DynamoDB Local, MinIO) pelos equivalentes gerenciados da AWS.

---

## 1. Visão geral da arquitetura na AWS

| Componente local   | Serviço AWS              | Observação |
|--------------------|--------------------------|------------|
| ElasticMQ          | **Amazon SQS**            | Fila `nest-jobs` |
| DynamoDB Local     | **Amazon DynamoDB**      | Tabela `nest_jobs` (PK: `job_id`) |
| MinIO              | **Amazon S3**            | Bucket para resultados (ex.: `nest-results-<conta>`) |
| API (FastAPI)      | **ECS Fargate** ou **App Runner** | Serviço HTTP na porta 8080 |
| Worker             | **ECS Fargate** (tasks)  | Consumidor SQS + binário nest_engine |
| Init (one-shot)    | **ECS Fargate** (run once) ou **Script/CLI** | Cria tabela e bucket uma vez |

**Fluxo:** Cliente → API (ALB/App Runner) → DynamoDB + SQS → Worker (Fargate) → DynamoDB + S3. O worker usa o binário C++ (engine) já incluído na imagem.

---

## 2. Pré-requisitos

- Conta AWS com permissões para criar: VPC (ou usar default), ECR, ECS, SQS, DynamoDB, S3, IAM roles, (opcional) Application Load Balancer.
- **AWS CLI** configurado (`aws configure`).
- **Docker** para build das imagens.
- (Opcional) **Terraform** ou **AWS CDK** para IaC; aqui o plano usa passos manuais + CLI.

---

## 3. Passo a passo

### 3.1 Região e conta

Escolha uma região (ex.: `us-east-1`) e defina:

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

---

### 3.2 Criar recursos de infraestrutura (uma vez)

#### 3.2.1 SQS – Fila para jobs

```bash
aws sqs create-queue \
  --queue-name nest-jobs \
  --attributes VisibilityTimeout=300,MessageRetentionPeriod=345600 \
  --region $AWS_REGION
```

Anote a URL da fila (saída do comando ou):

```bash
export SQS_QUEUE_URL=$(aws sqs get-queue-url --queue-name nest-jobs --query QueueUrl --output text)
echo $SQS_QUEUE_URL
```

#### 3.2.2 DynamoDB – Tabela de jobs

```bash
aws dynamodb create-table \
  --table-name nest_jobs \
  --attribute-definitions AttributeName=job_id,AttributeType=S \
  --key-schema AttributeName=job_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION
```

#### 3.2.3 S3 – Bucket para resultados

```bash
export S3_BUCKET=nest-results-${AWS_ACCOUNT_ID}
aws s3 mb s3://${S3_BUCKET} --region $AWS_REGION
```

(Se preferir nome fixo, use um bucket name único globalmente, ex.: `nest-results-meuapp-123`.)

---

### 3.3 Código pronto para AWS (API e Worker)

A API e o Worker já estão preparados para rodar na AWS:

- **API** (`services/api/app.py`): Se `SQS_QUEUE_URL` estiver definida, usa essa URL e os clientes boto3 passam a usar os serviços reais (sem `endpoint_url`), com credenciais da task role.
- **Worker** (`services/worker/worker.py`): Se `SQS_QUEUE_URL` for uma URL SQS real (`https://sqs....`), os clientes DynamoDB, S3 e SQS usam os serviços AWS (sem endpoint customizado).

Na AWS basta definir `SQS_QUEUE_URL` (e não definir `SQS_ENDPOINT`, `DYNAMODB_ENDPOINT`, `S3_ENDPOINT`).

---

### 3.4 Build e push das imagens Docker para o ECR

#### 3.4.1 Criar repositórios ECR

```bash
aws ecr create-repository --repository-name nest-api    --region $AWS_REGION
aws ecr create-repository --repository-name nest-worker  --region $AWS_REGION
```

#### 3.4.2 Login no ECR e build/push

```bash
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

Na pasta `nest-local`:

```bash
# API
docker build -t nest-api ./services/api
docker tag nest-api:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-api:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-api:latest

# Worker (inclui engine)
docker build -t nest-worker ./services/worker
docker tag nest-worker:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-worker:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-worker:latest
```

---

### 3.5 IAM – Roles para ECS

As tasks da API e do Worker precisam de uma **task role** com permissão para:

- SQS: `SendMessage`, `ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes` na fila `nest-jobs`.
- DynamoDB: `PutItem`, `GetItem`, `UpdateItem`, `DescribeTable` na tabela `nest_jobs`.
- S3: `PutObject`, `GetObject` no bucket de resultados.

Crie uma policy (ex.: `nest-ecs-policy`) com essas permissões e uma **role** de tarefa ECS que a assuma. Associe essa role às definições de task da API e do Worker.

Exemplo mínimo de policy (ajuste ARNs da fila, tabela e bucket):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:REGION:ACCOUNT:nest-jobs"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DescribeTable"
      ],
      "Resource": "arn:aws:dynamodb:REGION:ACCOUNT:table/nest_jobs"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::nest-results-ACCOUNT/*"
    }
  ]
}
```

Na AWS, use **task role** (não execution role) para que o código da API/Worker use credenciais temporárias da task. Assim não é necessário configurar `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` nas variáveis de ambiente.

---

### 3.6 ECS – Cluster, Task Definitions e Services

#### 3.6.1 Cluster

```bash
aws ecs create-cluster --cluster-name nest-cluster --region $AWS_REGION
```

#### 3.6.2 Task Definition – API

- **Família:** `nest-api`
- **Rede:** awsvpc (para Fargate).
- **CPU/Memória:** ex. 0.25 vCPU, 512 MiB.
- **Container:** imagem ECR `nest-api:latest`, porta 8080, healthcheck `GET /health`.
- **Variáveis de ambiente (sem credenciais se usar task role):**
  - `SQS_QUEUE_URL` = URL da fila SQS
  - `TABLE_NAME` = `nest_jobs`
  - `S3_BUCKET` = nome do bucket (ex.: `nest-results-${AWS_ACCOUNT_ID}`)
  - `AWS_DEFAULT_REGION` = `$AWS_REGION`
- **Task role:** a role com permissões SQS, DynamoDB e S3.
- **Execution role:** a role padrão ECS para pull de imagem ECR e logs (ex.: `ecsTaskExecutionRole`).

Não defina `SQS_ENDPOINT`, `DYNAMODB_ENDPOINT` nem `S3_ENDPOINT` — o SDK usará os serviços reais da AWS.

#### 3.6.3 Task Definition – Worker

- **Família:** `nest-worker`
- **Container:** imagem ECR `nest-worker:latest`.
- **Variáveis de ambiente:**
  - `SQS_QUEUE_URL` = mesma URL da fila
  - `TABLE_NAME` = `nest_jobs`
  - `S3_BUCKET` = mesmo bucket
  - `AWS_DEFAULT_REGION` = `$AWS_REGION`
- **Task role:** mesma da API.
- **Número de tasks:** pode ser 1 ou mais (escala horizontal pelo número de tasks do serviço ou por métricas SQS).

#### 3.6.4 Serviços ECS

- **nest-api:** tipo Fargate, desired count 1 (ou mais com ALB). Expor porta 8080. Se for acesso público, coloque atrás de um **Application Load Balancer** (ALB) com target group apontando para a porta 8080 e health check em `/health`.
- **nest-worker:** tipo Fargate, desired count 1 ou 2. Sem load balancer; as tasks só consomem da fila SQS.

---

### 3.7 Expor a API (opções)

1. **Application Load Balancer (ALB)**  
   Crie um ALB público, listener HTTPS (opcional) ou HTTP na 80, target group com protocolo HTTP e porta 8080, health check `/health`. Registre o serviço ECS da API no target group (com awsvpc e o security group que permite tráfego do ALB na 8080). Use o DNS do ALB como base URL da API.

2. **AWS App Runner**  
   Em vez de ECS + ALB, você pode criar um serviço App Runner a partir do ECR `nest-api`. App Runner cuida de HTTPS e escalabilidade. Útil se quiser menos gestão de rede/ALB.

3. **API Gateway + integração privada**  
   Para maior controle de tráfego e caching, pode colocar um API Gateway na frente do ALB ou do NLB (interno).

---

### 3.8 Variáveis de ambiente – Resumo

| Variável           | API | Worker | Valor na AWS |
|--------------------|-----|--------|--------------|
| `SQS_QUEUE_URL`    | sim | sim    | URL completa da fila SQS |
| `TABLE_NAME`       | sim | sim    | `nest_jobs` |
| `S3_BUCKET`        | sim | sim    | Nome do bucket S3 |
| `AWS_DEFAULT_REGION` | sim | sim  | ex. `us-east-1` |
| `SQS_ENDPOINT`     | não | não   | Não definir (usa SQS real) |
| `DYNAMODB_ENDPOINT`| não | não   | Não definir |
| `S3_ENDPOINT`      | não | não   | Não definir |
| Credenciais        | não | não   | Usar task role IAM |

---

### 3.9 Init (tabela e bucket) na AWS

O serviço **init** do docker-compose cria tabela e bucket nos serviços locais. Na AWS:

- A **tabela** e o **bucket** você já terão criado nos passos 3.2.2 e 3.2.3.
- Se quiser automatizar em outro ambiente (ex.: outra conta/região), pode:
  - Rodar o script `init_infra.py` **sem** `DYNAMODB_ENDPOINT` e `S3_ENDPOINT` (usa DynamoDB e S3 reais), com credenciais ou role com permissões de criação de tabela e bucket, ou
  - Replicar a lógica em um job one-shot no ECS (task que roda uma vez com a imagem do init) ou em um script no CodeBuild/CLI.

---

## 4. Ordem sugerida de execução

1. Criar SQS, DynamoDB e S3 (3.2).  
2. Ajustar a API para usar `SQS_QUEUE_URL` (3.3).  
3. Criar repositórios ECR e fazer build/push da API e do Worker (3.4).  
4. Criar IAM task role e policy (3.5).  
5. Criar cluster ECS, task definitions (API e Worker) e serviços (3.6).  
6. Configurar ALB (ou App Runner) e apontar o frontend para a URL da API (3.7).  
7. Testar: `POST /jobs`, `GET /jobs/{id}`, verificar resultado no S3 e status no DynamoDB.

---

## 5. Custos (estimativa enxuta)

- **SQS:** custo baixo para baixo volume de mensagens.  
- **DynamoDB:** pay-per-request; baixo custo para poucos jobs/segundo.  
- **S3:** armazenamento e requests mínimos para resultados de nesting.  
- **ECS Fargate:** cobrança por vCPU/memória por tempo de execução; 1 task API (0.25 vCPU, 512 MiB) + 1 task Worker (ex.: 0.5 vCPU, 1 GiB) dão uma base enxuta.  
- **ALB:** custo fixo mensal + uso.  
- **App Runner:** alternativa com preço por vCPU e requisição.

---

## 6. Próximos passos opcionais

- **Terraform/CDK:** codificar toda essa infra (SQS, DynamoDB, S3, ECR, ECS, IAM, ALB) para ambientes múltiplos e CI/CD.  
- **CI/CD:** pipeline (GitHub Actions, CodePipeline, etc.) para build das imagens, push no ECR e atualização do serviço ECS.  
- **Escalabilidade:** aumentar desired count do Worker com base em métrica da fila SQS (ex.: ApproximateNumberOfMessagesVisible).  
- **Segurança:** VPC privada para as tasks, API só acessível via ALB; secrets em Secrets Manager se no futuro houver chaves adicionais.

---

## 7. Referência rápida – Comandos úteis

```bash
# URL da fila
aws sqs get-queue-url --queue-name nest-jobs --query QueueUrl --output text

# Status da tabela
aws dynamodb describe-table --table-name nest_jobs --query Table.TableStatus

# Listar imagens ECR
aws ecr describe-images --repository-name nest-api --query 'imageDetails[*].imageTags'
```

Com esse plano, você consegue rodar o projeto **direto na AWS** usando SQS, DynamoDB e S3 gerenciados, com API e Worker no ECS Fargate.
