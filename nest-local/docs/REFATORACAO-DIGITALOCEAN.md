# Refatoração para compatibilidade Digital Ocean

Resumo das alterações feitas para **compatibilidade total** com Digital Ocean (Droplet + MinIO ou Spaces).

---

## 1. Código: configuração via variáveis de ambiente

### API (`services/api/app.py`)

- **TABLE_NAME**: lido de `TABLE_NAME` (default `nest_jobs`).
- **QUEUE_NAME**: lido de `QUEUE_NAME` (default `nest-jobs`).
- **PRESIGNED_EXPIRY**: lido de `PRESIGNED_EXPIRY` (default `600`).

Assim, tabela, fila e expiração da URL de resultado são configuráveis sem mudar código.

### Worker (`services/worker/worker.py`)

- **TABLE_NAME**: lido de `TABLE_NAME` (default `nest_jobs`).
- **ENGINE_TIMEOUT**: lido de `ENGINE_TIMEOUT` (default `20`).
- **ERROR_MAX_LEN**: lido de `ERROR_MAX_LEN` (default `2000`).

### Init (`services/init/init_infra.py`)

- **SKIP_S3_INIT**: quando `1`, `true` ou `yes`, o init **não** cria bucket no S3/MinIO. Usado quando o bucket já existe (ex.: Digital Ocean Spaces criado no painel).

---

## 2. Arquivos específicos para Digital Ocean

| Arquivo | Função |
|---------|--------|
| **docker-compose.do.yml** | Override que adiciona **volumes** para DynamoDB Local e MinIO (dados persistentes no Droplet). Uso: `docker compose -f docker-compose.yml -f docker-compose.do.yml up -d`. |
| **docker-compose.do.spaces.yml** | Stack completo **sem MinIO**: usa Digital Ocean Spaces (S3-compatível). Exige `.env` com `S3_ENDPOINT`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e `SKIP_S3_INIT=1`. |
| **.env.do.example** | Exemplo de variáveis para DO (MinIO no Droplet ou Spaces). Copiar para `.env` e preencher; não commitar `.env`. |

---

## 3. Cenários suportados no Digital Ocean

1. **Droplet + MinIO no próprio servidor**  
   - Compose: `docker-compose.yml` + `docker-compose.do.yml`.  
   - Persistência: DynamoDB e MinIO em volumes.  
   - Nenhuma dependência externa além do Droplet.

2. **Droplet + Spaces (armazenamento S3 na DO)**  
   - Compose: `docker-compose.do.spaces.yml`.  
   - Space e chave API criados no painel DO; bucket = nome do Space.  
   - Init com `SKIP_S3_INIT=1`; fila e banco continuam no Droplet (ElasticMQ + DynamoDB Local).

3. **Local (desenvolvimento)**  
   - Compose: `docker-compose.yml` (sem override).  
   - Comportamento anterior mantido.

---

## 4. Documentação atualizada

- **README.md**: tabela de variáveis de ambiente; referência a `docker-compose.do.yml`, `docker-compose.do.spaces.yml` e `.env.do.example`.
- **docs/PASSO-A-PASSO-DIGITALOCEAN.md**: tabela dos arquivos DO; Parte 4 com Opções A (MinIO), B (Spaces) e C (local); Parte 6 e resumo de comandos usando o override DO.

---

## 5. Compatibilidade com AWS

As mudanças são compatíveis com o uso em **AWS** (SQS, DynamoDB, S3): a API e o Worker já usam `SQS_QUEUE_URL`, endpoints e credenciais via ambiente. A leitura de `TABLE_NAME`, `QUEUE_NAME` e demais variáveis apenas torna a configuração explícita e reutilizável em qualquer ambiente.
