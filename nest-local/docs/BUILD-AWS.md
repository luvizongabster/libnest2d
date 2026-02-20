# Builds na AWS (sem Docker local)

Este guia descreve como configurar **builds totalmente na AWS** usando **AWS CodeBuild** (e opcionalmente **CodePipeline**). As imagens Docker da API e do Worker são construídas nos servidores da AWS e enviadas ao ECR; você não precisa fazer build na sua máquina.

---

## Visão geral

- **CodeBuild** usa o arquivo `buildspec.yml` (em `nest-local/buildspec.yml`) para:
  1. Fazer login no ECR
  2. Buildar a imagem do **engine** (C++) – usada apenas como base do Worker
  3. Buildar a imagem da **API** e da **Worker**
  4. Fazer tag e **push** das imagens `nest-api` e `nest-worker` para o ECR

- O código-fonte pode vir de **GitHub**, **AWS CodeCommit** ou **S3** (zip).

- Depois do push, o ECS pode usar as novas imagens (atualizando o serviço ou usando “latest”).

---

## Pré-requisitos

- Conta AWS com permissão para criar CodeBuild, IAM, ECR e (se usar) CodePipeline.
- Repositório com o código (ex.: GitHub). O `buildspec.yml` deve estar no repositório (em `nest-local/buildspec.yml` se o repo for o Libnest2D inteiro).
- Repositórios ECR já criados: `nest-api` e `nest-worker` (como no [PASSO-A-PASSO-AWS.md](PASSO-A-PASSO-AWS.md)).

---

## Parte 1 – Role IAM para o CodeBuild

O projeto CodeBuild precisa de uma **role** que permita: fazer login no ECR, push das imagens, escrever logs no CloudWatch e (se usar GitHub via CodeStar Connection) usar a conexão.

### 1.1 Policy de permissões do CodeBuild

Crie uma policy com o conteúdo abaixo. Salve como `codebuild-nest-policy.json` (ajuste a região e a conta nos ARNs).

Substitua `REGION` e `ACCOUNT` pela sua região (ex.: `us-east-1`) e ID da conta. Ou use o bloco “Gerar policy com variáveis” mais abaixo.

**Conteúdo da policy (codebuild-nest-policy.json):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "ECRPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": [
        "arn:aws:ecr:REGION:ACCOUNT:repository/nest-api",
        "arn:aws:ecr:REGION:ACCOUNT:repository/nest-worker"
      ]
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:REGION:ACCOUNT:log-group:/aws/codebuild/*"
    },
    {
      "Sid": "S3ArtifactsOptional",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::codebuild-*"
    }
  ]
}
```

**Gerar o arquivo com variáveis (no terminal, na pasta onde quer o JSON):**

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > codebuild-nest-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "ECRPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": [
        "arn:aws:ecr:${AWS_REGION}:${AWS_ACCOUNT_ID}:repository/nest-api",
        "arn:aws:ecr:${AWS_REGION}:${AWS_ACCOUNT_ID}:repository/nest-worker"
      ]
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/aws/codebuild/*"
    }
  ]
}
EOF
```

Crie a policy na AWS:

```bash
aws iam create-policy \
  --policy-name codebuild-nest-ecr-policy \
  --policy-document file://codebuild-nest-policy.json
```

Anote o **Arn** retornado (ex.: `arn:aws:iam::123456789012:policy/codebuild-nest-ecr-policy`).

### 1.2 Role “codebuild-nest-service-role”

Crie a role que o CodeBuild vai assumir:

```bash
aws iam create-role \
  --role-name codebuild-nest-service-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": { "Service": "codebuild.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }]
  }'
```

Anexe a policy à role (use o Arn da policy que você anotou):

```bash
export CODEBUILD_POLICY_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:policy/codebuild-nest-ecr-policy
aws iam attach-role-policy \
  --role-name codebuild-nest-service-role \
  --policy-arn $CODEBUILD_POLICY_ARN
```

---

## Parte 2 – Projeto CodeBuild (fonte: repositório)

Você pode criar o projeto pelo **Console** ou pela **CLI**. Abaixo: Console (mais claro para fonte GitHub) e depois CLI.

### 2.1 Pelo Console AWS

1. Acesse **AWS CodeBuild** na região desejada (ex.: `us-east-1`).
2. **Create build project**.

**Project configuration**

- **Project name:** `nest-build` (ou outro).
- **Description:** opcional (ex.: “Build nest-api e nest-worker para ECR”).

**Source**

- **Source provider:** **GitHub** (ou **CodeCommit** / **Amazon S3**, se preferir).
- Se for **GitHub**:
  - **Connect using OAuth** (recomendado para repositório público): clique em **Connect to GitHub**, autorize e escolha:
    - **Repository in my GitHub account**
    - **Repo:** seu repositório (ex.: `Libnest2D` ou o que contém a pasta `nest-local`).
    - **Reference type:** Branch.
    - **Branch:** ex.: `main` ou `master`.
  - Ou **Connect using GitHub App** / **Connect using CodeStar Connection** (para repo privado ou pipelines com trigger em push).

**Environment**

- **Environment image:** **Managed image**.
- **Operating system:** **Amazon Linux**.
- **Runtime(s):** **Standard**.
- **Image:** **Amazon Linux 2 x86_64 Standard 7.0** (ou mais recente).
- **Privileged:** marque **Enable** (necessário para build de imagens Docker dentro do ambiente).
- **Service role:** **Existing service role** → **codebuild-nest-service-role** (a que você criou).
- **Role name:** deve aparecer como `codebuild-nest-service-role`.

**Buildspec**

- **Build specifications:** **Use a buildspec file**.
- **Buildspec name:** `nest-local/buildspec.yml`  
  - Use isso se a raiz do repositório for o projeto inteiro (ex.: Libnest2D) e o app estiver em `nest-local`.  
  - Se o repositório contiver **só** o conteúdo da pasta `nest-local` (raiz = app), use `buildspec.yml`.

**Additional configuration (opcional mas recomendado)**

- **Environment variables:** adicione as variáveis abaixo (Type = Plaintext):

  | Name           | Value        | Observação                          |
  |----------------|-------------|-------------------------------------|
  | `AWS_REGION`   | `us-east-1` | Região do ECR e do projeto.         |
  | `ECR_REPO_API` | `nest-api`  | Nome do repositório ECR da API.     |
  | `ECR_REPO_WORKER` | `nest-worker` | Nome do repositório ECR do Worker. |
  | `APP_PATH`     | `nest-local` | Subpasta do repo onde está o app. Deixe **vazio** se a raiz do repo já for o app. |

- **Logs:**
  - **CloudWatch logs:** Enable.
  - **Group name:** ex.: `/aws/codebuild/nest-build`.
  - **Stream name:** opcional (pode deixar padrão).

3. Clique em **Create build project**.

### 2.2 Pelo AWS CLI

Use depois de ter a fonte configurada. Para **GitHub com OAuth**, primeiro é necessário conectar pelo Console uma vez (Connect to GitHub). Para **CodeCommit** ou **S3** não precisa.

Exemplo com **CodeCommit** (crie o repositório e faça push do código antes):

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ROLE_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:role/codebuild-nest-service-role
```

Se o código estiver em **CodeCommit** (substitua `codecommit-repo-name` e `branch`):

```bash
aws codebuild create-project \
  --name nest-build \
  --source "type=CODECOMMIT,location=https://git-codecommit.${AWS_REGION}.amazonaws.com/v1/repos/codecommit-repo-name,buildspec=nest-local/buildspec.yml,gitCloneDepth=1" \
  --source-version "refs/heads/main" \
  --artifacts "type=NO_ARTIFACTS" \
  --environment "type=LINUX_CONTAINER,image=aws/codebuild/amazonlinux2-x86_64-standard:7.0,computeType=BUILD_GENERAL1_MEDIUM,privilegedMode=true" \
  --service-role $ROLE_ARN \
  --logs-config "cloudWatchLogs={status=ENABLED,groupName=/aws/codebuild/nest-build}" \
  --region $AWS_REGION
```

Adicionar variáveis de ambiente ao projeto (já criado):

```bash
aws codebuild update-project \
  --name nest-build \
  --environment "type=LINUX_CONTAINER,image=aws/codebuild/amazonlinux2-x86_64-standard:7.0,computeType=BUILD_GENERAL1_MEDIUM,privilegedMode=true,environmentVariables=[{name=AWS_REGION,value=us-east-1,type=PLAINTEXT},{name=ECR_REPO_API,value=nest-api,type=PLAINTEXT},{name=ECR_REPO_WORKER,value=nest-worker,type=PLAINTEXT},{name=APP_PATH,value=nest-local,type=PLAINTEXT}]" \
  --region $AWS_REGION
```

Para **GitHub**, o projeto costuma ser criado pelo Console (conexão OAuth). Depois você pode usar `update-project` para ajustar variáveis ou buildspec.

---

## Parte 3 – Rodar o build

### 3.1 Pelo Console

1. Em **CodeBuild** → **Build projects** → **nest-build**.
2. **Start build** (opcionalmente informe **Source version**, ex.: branch ou commit).
3. Acompanhe em **Build history** e nos **CloudWatch logs** do projeto.

### 3.2 Pelo CLI

```bash
aws codebuild start-build --project-name nest-build --region $AWS_REGION
```

Para buildar um commit/branch específico (ex.: branch `main`):

```bash
aws codebuild start-build \
  --project-name nest-build \
  --source-version "refs/heads/main" \
  --region $AWS_REGION
```

O retorno traz o `id` do build. Para ver o status:

```bash
aws codebuild batch-get-builds --ids <build-id> --query 'builds[0].buildStatus' --output text --region $AWS_REGION
```

Quando o status for **SUCCEEDED**, as imagens `nest-api:latest` e `nest-worker:latest` estarão no ECR.

---

## Parte 4 – CodePipeline (build automático a cada push) [opcional]

Para disparar o build **sempre que houver push** no repositório:

1. Crie um **CodePipeline** com estágios:
   - **Source:** GitHub (ou CodeCommit) – repositório e branch (ex.: `main`).
   - **Build:** **AWS CodeBuild** – projeto **nest-build**.
   - (Opcional) **Deploy:** atualizar serviço ECS para usar a nova imagem (não detalhado aqui).

2. Se a fonte for **GitHub** e o repositório for **privado**, use **CodeStar Connection**:
   - Em **Developer tools** → **Connections** → **Create connection**.
   - **Provider:** GitHub.
   - Siga o fluxo para autorizar e instalar o connector no GitHub.
   - No estágio Source do Pipeline, escolha **Connect using CodeStar Connection** e selecione essa conexão.

3. No estágio **Build**, selecione o projeto CodeBuild **nest-build**. O Pipeline passa o código baixado pelo estágio Source para o CodeBuild; o buildspec continua o mesmo.

Depois do primeiro build bem-sucedido, a cada push no branch configurado um novo build será iniciado e as novas imagens serão enviadas ao ECR.

---

## Parte 5 – Usar as novas imagens no ECS

Depois que o CodeBuild fizer push de `nest-api:latest` e `nest-worker:latest` para o ECR:

- **Atualização manual:** no ECS, atualize o serviço (force new deployment) para que as tasks passem a usar a imagem `latest` novamente (pull da nova digest).
- **Atualização automática:** se você adicionar um estágio **Deploy** no CodePipeline (ação “Amazon ECS” para atualizar o serviço), o deploy pode ser disparado após o build.

Comando para forçar nova implantação dos serviços (após o build):

```bash
aws ecs update-service --cluster nest-cluster --service nest-api   --force-new-deployment --region $AWS_REGION
aws ecs update-service --cluster nest-cluster --service nest-worker --force-new-deployment --region $AWS_REGION
```

---

## Resumo rápido

| O que                         | Onde / Como |
|------------------------------|-------------|
| Definir passos do build      | `nest-local/buildspec.yml` |
| Onde o build roda            | Projeto CodeBuild (ambiente Docker privilegiado) |
| Origem do código             | GitHub, CodeCommit ou S3 (configurado no projeto) |
| Destino das imagens          | ECR `nest-api` e `nest-worker` |
| Variáveis do projeto         | `AWS_REGION`, `ECR_REPO_API`, `ECR_REPO_WORKER`, `APP_PATH` (se necessário) |
| Build automático em push     | CodePipeline com estágio Source + Build (CodeBuild) |

---

## Troubleshooting

- **“Cannot connect to the Docker daemon”**  
  Ative **Privileged** no ambiente do projeto CodeBuild (Environment → Privileged → Enable).

- **“no such file buildspec.yml”**  
  Confira o caminho em **Buildspec name**. Se o app está em `nest-local`, use `nest-local/buildspec.yml` e defina `APP_PATH=nest-local`.

- **“denied: Your authorization token has expired”**  
  O buildspec já faz `aws ecr get-login-password`; a role do CodeBuild precisa da policy com `ecr:GetAuthorizationToken` e permissões de push nos repositórios (como na policy acima).

- **Build do engine muito lento**  
  O build do engine compila C++ e pode levar vários minutos. Para acelerar, use **cache** do CodeBuild (S3) para as camadas do Docker; no `buildspec.yml` há um bloco `cache` vazio que você pode preencher com `docker` se quiser cache de layers.

- **Repositório privado no GitHub**  
  Use **CodeStar Connection** no CodePipeline (e, se necessário, fonte do projeto CodeBuild via Pipeline) ou **GitHub App**; conexão OAuth simples costuma ser só para repositórios públicos.

Com isso, você passa a ter **builds novas sempre na AWS**, sem depender de builds locais.
