# Nest Local – Ambiente Docker para microserviço de nesting (libnest2d)

Stack local com API FastAPI, worker assíncrono, engine C++ (libnest2d), ElasticMQ, DynamoDB local e MinIO.

## 1. Subir o stack

```bash
cd nest-local
docker compose up --build
```

O serviço `init` cria a tabela DynamoDB `nest_jobs` e o bucket MinIO `nest-results` na primeira subida. Em seguida sobem API (porta 8080), worker, ElasticMQ (9324), DynamoDB (8000) e MinIO (9000 + console 9001).

### Acesso externo (ex.: teste com frontend Lovable)

A API escuta em **todas as interfaces** (`0.0.0.0:8080`) e tem **CORS liberado** para qualquer origem, para o frontend conseguir chamar a API.

- **Na mesma rede (LAN)**: use o IP da máquina onde o Docker está rodando, por exemplo `http://192.168.1.100:8080`. Descubra o IP com `hostname -I` (Linux) ou `ipconfig` (Windows).
- **Da internet (Lovable em produção)**: use um túnel para expor a porta 8080, por exemplo:
  - **ngrok**: `ngrok http 8080` → use a URL `https://...ngrok.io` como base da API no frontend.
  - **cloudflared**: `cloudflared tunnel --url http://localhost:8080` → use a URL gerada.

No frontend Lovable, configure a base URL da API para uma dessas URLs (com `/jobs`, `/health` etc. relativos a essa base).

## 2. Criar um job

Envie o payload de nesting para a API:

```bash
curl -X POST http://localhost:8080/jobs \
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

Resposta: `{"job_id":"<uuid>"}`.

## 3. Consultar status e resultado

Poll até o job terminar:

```bash
JOB_ID="<job_id do passo anterior>"
curl -s "http://localhost:8080/jobs/$JOB_ID"
```

- `QUEUED` / `RUNNING`: aguardar e chamar de novo.
- `SUCCEEDED`: a resposta traz `result_url` e `expires_in_sec` (ex.: 600).
- `FAILED`: a resposta traz `error`.

## 4. Baixar o resultado

Com o `result_url` retornado quando o status é `SUCCEEDED`:

```bash
curl -s "<result_url>" -o result.json
```

O JSON contém `bins_used`, `placements` (instance_id, bin, x, y, rotation) e `metrics` (runtime_ms, utilization).

## 5. Estrutura do JSON de entrada

| Campo     | Tipo   | Descrição |
|----------|--------|-----------|
| `units`  | string | Unidade (ex.: `"mm"`) |
| `bin`    | objeto | `width`, `height` (número) |
| `parts`  | array  | Lista de peças |
| `options`| objeto | Opcional: `spacing`, `rotations` (graus), `timeout_ms` |

Cada elemento de `parts`:

- `id`: string
- `qty`: número de cópias
- `polygon`: array de `[x, y]` (contorno fechado; pode repetir o primeiro ponto no final)

## 6. Trocar ElasticMQ por SQS real

- Remova o serviço `elasticmq` do `docker-compose.yml` e use uma fila SQS na AWS.
- Defina nas variáveis de ambiente da API e do worker:
  - `SQS_ENDPOINT`: deixe em branco ou não defina (usa SQS padrão).
  - `SQS_QUEUE_URL`: URL completa da fila (ex.: `https://sqs.us-east-1.amazonaws.com/123456789012/nest-jobs`).
- Use credenciais AWS (IAM role, env ou profile) em vez de `minioadmin`.

## 7. Subir no ECS

- **Imagens**: faça build e push das imagens `nest-local-api` e `nest-local-worker` para um ECR (ou registry compatível).
- **Engine**: o worker já inclui o binário `nest_engine`; não é necessário um serviço ECS para o engine.
- **Infra**:
  - Fila SQS real para `nest-jobs`.
  - Tabela DynamoDB real com PK `job_id` (String).
  - Bucket S3 real para resultados (ex.: `nest-results`).
- **Tasks**:
  - Serviço API: Fargate (ou EC2), porta 8080, variáveis de ambiente apontando para SQS, DynamoDB e S3.
  - Serviço Worker: Fargate (ou EC2), uma ou mais tasks consumindo da fila SQS, com as mesmas variáveis de ambiente.
- **Load balancer**: na frente da API, se for público; segurança com VPC e security groups conforme sua política.

## Estrutura do projeto

```
nest-local/
  docker-compose.yml
  elasticmq.conf
  services/
    api/       (FastAPI)
    worker/    (consumidor SQS + nest_engine)
    engine/    (binário C++ libnest2d)
    init/      (cria tabela DDB e bucket S3)
  scripts/
    init_minio.sh
    seed_ddb.sh
  README.md
```

## Portas

- **8080**: API
- **9000**: MinIO S3 API
- **9001**: MinIO Console
- **9324**: ElasticMQ (SQS)
- **8000**: DynamoDB local
