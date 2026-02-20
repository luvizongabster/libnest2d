# Passo a passo: criar a infra do Nest na AWS do zero

Siga os passos **na ordem**. Cada bloco de comandos pode ser copiado e colado no terminal (mantenha as variáveis `AWS_REGION` e `AWS_ACCOUNT_ID` definidas entre os passos).

---

## Pré-requisitos

- **AWS CLI** instalado e configurado (`aws configure` com Access Key e Secret).
- **Docker** instalado e em execução (para build das imagens).
- Terminal na pasta **`nest-local`** do projeto (para builds e paths relativos).

---

## Passo 1 – Região e conta

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Região: $AWS_REGION | Conta: $AWS_ACCOUNT_ID"
```

Se aparecer um número de conta, está ok. Troque `us-east-1` por outra região se quiser (ex.: `sa-east-1`).

---

## Passo 2 – SQS (fila de jobs)

```bash
aws sqs create-queue \
  --queue-name nest-jobs \
  --attributes VisibilityTimeout=300,MessageRetentionPeriod=345600 \
  --region $AWS_REGION
```

Depois anote a URL da fila:

```bash
export SQS_QUEUE_URL=$(aws sqs get-queue-url --queue-name nest-jobs --query QueueUrl --output text)
echo $SQS_QUEUE_URL
```

Guarde esse valor; você vai usar nas task definitions do ECS.

---

## Passo 3 – DynamoDB (tabela de jobs)

```bash
aws dynamodb create-table \
  --table-name nest_jobs \
  --attribute-definitions AttributeName=job_id,AttributeType=S \
  --key-schema AttributeName=job_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION
```

Aguarde a tabela ficar `ACTIVE` (alguns segundos). Para conferir:

```bash
aws dynamodb describe-table --table-name nest_jobs --query Table.TableStatus --output text
```

---

## Passo 4 – S3 (bucket de resultados)

```bash
export S3_BUCKET=nest-results-${AWS_ACCOUNT_ID}
aws s3 mb s3://${S3_BUCKET} --region $AWS_REGION
echo "Bucket: $S3_BUCKET"
```

Se der erro de “bucket already exists”, use outro nome, por exemplo:

```bash
export S3_BUCKET=nest-results-${AWS_ACCOUNT_ID}-nest
aws s3 mb s3://${S3_BUCKET} --region $AWS_REGION
```

---

## Passo 5 – ECR (repositórios das imagens)

```bash
aws ecr create-repository --repository-name nest-api   --region $AWS_REGION
aws ecr create-repository --repository-name nest-worker --region $AWS_REGION
```

---

## Passo 6 – Build e push das imagens Docker

**Se quiser fazer os builds na AWS (sem Docker na sua máquina), use o guia [BUILD-AWS.md](BUILD-AWS.md)** para configurar CodeBuild e, se desejar, CodePipeline. Depois volte aqui no Passo 7.

**Opção com build local:** login no ECR:

```bash
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

**Importante:** execute os comandos abaixo **dentro da pasta `nest-local`** (onde está o `docker-compose.yml`).

```bash
cd /caminho/para/nest-local
```

Substitua `/caminho/para/nest-local` pela pasta real do projeto. Depois:

```bash
# API
docker build -t nest-api ./services/api
docker tag nest-api:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-api:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-api:latest

# Worker (inclui o engine C++)
docker build -t nest-worker ./services/worker
docker tag nest-worker:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-worker:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-worker:latest
```

Se der erro de build no worker (engine C++), confira o README do projeto para dependências (CMake, compilador, etc.).

---

## Passo 7 – IAM (permissões para API e Worker)

As tasks do ECS vão usar uma **task role** para acessar SQS, DynamoDB e S3. Não use Access Key nas variáveis de ambiente.

### 7.1 Criar a policy

Salve o JSON abaixo em um arquivo, trocando `REGION` e `ACCOUNT` pelos valores reais (ou use o comando que já substitui).

**Opção A – arquivo `nest-task-policy.json` na pasta `nest-local`:**

Conteúdo (ajuste REGION e ACCOUNT ou use o script abaixo):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:REGION:ACCOUNT:nest-jobs"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:DescribeTable"
      ],
      "Resource": "arn:aws:dynamodb:REGION:ACCOUNT:table/nest_jobs"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::BUCKET_NAME/*"
    }
  ]
}
```

**Opção B – gerar o arquivo com a CLI (na pasta nest-local):**

```bash
cat > nest-task-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:${AWS_REGION}:${AWS_ACCOUNT_ID}:nest-jobs"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:DescribeTable"
      ],
      "Resource": "arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT_ID}:table/nest_jobs"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_BUCKET}/*"
    }
  ]
}
EOF
```

Criar a policy na AWS:

```bash
aws iam create-policy \
  --policy-name nest-ecs-task-policy \
  --policy-document file://nest-task-policy.json
```

Anote o **Arn** da policy na saída (ex.: `arn:aws:iam::123456789012:policy/nest-ecs-task-policy`). Use no próximo passo como `NEST_TASK_POLICY_ARN`.

### 7.2 Criar a role de tarefa ECS

```bash
# Criar role que o ECS pode assumir
aws iam create-role \
  --role-name nest-ecs-task-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }]
  }'
```

Anexar a policy à role (substitua pelo ARN que anotou):

```bash
export NEST_TASK_POLICY_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:policy/nest-ecs-task-policy
aws iam attach-role-policy \
  --role-name nest-ecs-task-role \
  --policy-arn $NEST_TASK_POLICY_ARN
```

### 7.3 Execution role (pull de imagem e logs)

Se você já tem a role `ecsTaskExecutionRole` (padrão em muitas contas), use ela. Senão, crie:

```bash
aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }]
  }'

aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

O ARN da execution role para as task definitions é:

```bash
export EXECUTION_ROLE_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole
export TASK_ROLE_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:role/nest-ecs-task-role
echo "Execution: $EXECUTION_ROLE_ARN"
echo "Task:      $TASK_ROLE_ARN"
```

---

## Passo 8 – ECS – Cluster e rede

Crie o cluster:

```bash
aws ecs create-cluster --cluster-name nest-cluster --region $AWS_REGION
```

Para Fargate você precisa de uma VPC com subnets. Use a **VPC padrão** da sua conta (recomendado para começar). Obtenha subnets e security group:

```bash
# Subnets (públicas da VPC default; use a mesma VPC para as duas)
export SUBNET_1=$(aws ec2 describe-subnets --filters "Name=default-for-az,Values=true" --query 'Subnets[0].SubnetId' --output text --region $AWS_REGION)
export SUBNET_2=$(aws ec2 describe-subnets --filters "Name=default-for-az,Values=true" --query 'Subnets[1].SubnetId' --output text --region $AWS_REGION)
export DEFAULT_VPC=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text --region $AWS_REGION)
export DEFAULT_SG=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$DEFAULT_VPC" "Name=group-name,Values=default" --query 'SecurityGroups[0].GroupId' --output text --region $AWS_REGION)
echo "Subnet1: $SUBNET_1 | Subnet2: $SUBNET_2 | SG: $DEFAULT_SG"
```

Se alguma variável vier vazia, verifique no Console EC2 > VPC > Subnets e Security Groups e defina manualmente.

---

## Passo 9 – ECS – Task Definition da API

Crie um arquivo `nest-api-task.json` na pasta `nest-local` (ou no mesmo diretório onde está rodando a CLI). Substitua **ACCOUNT**, **REGION**, **SQS_QUEUE_URL** e **S3_BUCKET** pelos seus valores (ou use o script abaixo que usa as variáveis já definidas).

**Gerar o arquivo com variáveis:**

```bash
cat > nest-api-task.json << TASKEOF
{
  "family": "nest-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-api:latest",
      "portMappings": [{ "containerPort": 8080, "protocol": "tcp" }],
      "essential": true,
      "environment": [
        { "name": "SQS_QUEUE_URL", "value": "${SQS_QUEUE_URL}" },
        { "name": "TABLE_NAME", "value": "nest_jobs" },
        { "name": "S3_BUCKET", "value": "${S3_BUCKET}" },
        { "name": "AWS_DEFAULT_REGION", "value": "${AWS_REGION}" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/nest-api",
          "awslogs-region": "${AWS_REGION}"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
TASKEOF
```

Criar o log group (necessário para o `logConfiguration`):

```bash
aws logs create-log-group --log-group-name /ecs/nest-api --region $AWS_REGION
```

Registrar a task definition:

```bash
aws ecs register-task-definition --cli-input-json file://nest-api-task.json --region $AWS_REGION
```

---

## Passo 10 – ECS – Task Definition do Worker

```bash
cat > nest-worker-task.json << TASKEOF
{
  "family": "nest-worker",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "worker",
      "image": "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/nest-worker:latest",
      "essential": true,
      "environment": [
        { "name": "SQS_QUEUE_URL", "value": "${SQS_QUEUE_URL}" },
        { "name": "TABLE_NAME", "value": "nest_jobs" },
        { "name": "S3_BUCKET", "value": "${S3_BUCKET}" },
        { "name": "AWS_DEFAULT_REGION", "value": "${AWS_REGION}" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/nest-worker",
          "awslogs-region": "${AWS_REGION}"
        }
      }
    }
  ]
}
TASKEOF

aws logs create-log-group --log-group-name /ecs/nest-worker --region $AWS_REGION
aws ecs register-task-definition --cli-input-json file://nest-worker-task.json --region $AWS_REGION
```

---

## Passo 11 – ECS – Serviço da API (sem ALB, para teste)

Para testar primeiro **sem** Load Balancer (acesso direto ao IP da task ou via port-forward), crie o serviço assim:

```bash
aws ecs create-service \
  --cluster nest-cluster \
  --service-name nest-api \
  --task-definition nest-api \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$DEFAULT_SG],assignPublicIp=ENABLED}" \
  --region $AWS_REGION
```

Para obter o IP público da task (depois que estiver RUNNING):

```bash
TASK_ARN=$(aws ecs list-tasks --cluster nest-cluster --service-name nest-api --query 'taskArns[0]' --output text --region $AWS_REGION)
ENI_ID=$(aws ecs describe-tasks --cluster nest-cluster --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text --region $AWS_REGION)
aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Association.PublicIp' --output text --region $AWS_REGION
```

A API estará em `http://<esse-ip>:8080`. O security group **default** costuma permitir entrada em todas as portas da própria VPC; para acesso da internet, é preciso liberar **entrada TCP 8080** de `0.0.0.0/0` no security group usado pelas tasks (no exemplo, `DEFAULT_SG`):

```bash
aws ec2 authorize-security-group-ingress \
  --group-id $DEFAULT_SG \
  --protocol tcp \
  --port 8080 \
  --cidr 0.0.0.0/0 \
  --region $AWS_REGION
```

---

## Passo 12 – ECS – Serviço do Worker

```bash
aws ecs create-service \
  --cluster nest-cluster \
  --service-name nest-worker \
  --task-definition nest-worker \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$DEFAULT_SG],assignPublicIp=ENABLED}" \
  --region $AWS_REGION
```

O worker não expõe porta; ele só consome mensagens da fila SQS.

---

## Passo 13 – Testar

1. **Health da API** (use o IP que você obteve no Passo 11):
   ```bash
   curl http://<IP-DA-TASK>:8080/health
   ```
   Resposta esperada: `{"status":"ok"}`.

2. **Criar um job:**
   ```bash
   curl -X POST http://<IP-DA-TASK>:8080/jobs \
     -H "Content-Type: application/json" \
     -d '{
       "units": "mm",
       "bin": { "width": 500, "height": 500 },
       "parts": [
         {
           "id": "P1",
           "qty": 2,
           "polygon": [[0,0], [100,0], [100,50], [0,50], [0,0]]
         }
       ],
       "options": { "spacing": 2, "rotations": [0, 90], "timeout_ms": 10000 }
     }'
   ```
   Anote o `job_id` da resposta.

3. **Consultar status (repita até status SUCCEEDED ou FAILED):**
   ```bash
   curl -s "http://<IP-DA-TASK>:8080/jobs/<JOB_ID>"
   ```

4. Se estiver **SUCCEEDED**, use o `result_url` para baixar o JSON ou abrir no navegador.

Se a API não responder, confira no ECS se a task está **RUNNING** e veja os logs em CloudWatch (`/ecs/nest-api`). Para o worker, logs em `/ecs/nest-worker`.

---

## Resumo da ordem

| # | O que fazer |
|---|-------------|
| 1 | Região e conta |
| 2 | Fila SQS `nest-jobs` |
| 3 | Tabela DynamoDB `nest_jobs` |
| 4 | Bucket S3 |
| 5 | Repositórios ECR `nest-api` e `nest-worker` |
| 6 | Build e push das imagens (a partir da pasta `nest-local`) |
| 7 | IAM: policy + task role + execution role |
| 8 | ECS cluster + variáveis de rede (subnets, SG) |
| 9 | Task definition da API + log group |
| 10 | Task definition do Worker + log group |
| 11 | Serviço ECS `nest-api` + liberar porta 8080 no SG |
| 12 | Serviço ECS `nest-worker` |
| 13 | Testar health, POST /jobs e GET /jobs/{id} |

---

## Próximo passo opcional: Application Load Balancer (ALB)

Para ter uma URL estável (em vez do IP da task) e HTTPS:

1. Crie um **Application Load Balancer** (esquema internet-facing) na mesma VPC e subnets.
2. Crie um **target group** (HTTP, porta 8080, target type **IP**), com health check em `/health`.
3. Adicione um **listener** (HTTP 80 e/ou HTTPS 443) encaminhando para esse target group.
4. Recrie o **serviço** `nest-api` com **load balancer** apontando para esse target group (o ECS registra as tasks automaticamente no target group).
5. Use o DNS do ALB como base URL da API (ex.: `http://nest-alb-xxxxx.us-east-1.elb.amazonaws.com`).

Se quiser, posso detalhar os comandos do ALB em um anexo ou outro arquivo.
