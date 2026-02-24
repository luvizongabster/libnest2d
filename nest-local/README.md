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
    "options": { "spacing": 2, "rotations": [0, 90, 180, 270], "timeout_ms": 10000 }
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

Para **refletir o resultado na representação das chapas no canvas**, use `?embed=result` para receber o resultado inline (evita segunda requisição e CORS):

```bash
curl -s "http://localhost:8080/jobs/<job_id>?embed=result"
```

Resposta quando `SUCCEEDED`: `result_url`, `expires_in_sec` e `result` com o JSON da otimização (veja abaixo). O frontend deve usar `result.bins_used` e `result.placements` para desenhar cada chapa e posicionar as peças.

## 4. Formato do resultado (para o canvas)

O objeto `result` (ou o JSON em `result_url`) tem:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `bins_used` | number | Número de chapas utilizadas (índices `0` a `bins_used - 1`) |
| `placements` | array | Posicionamento de cada peça na chapa |
| `metrics` | object | `runtime_ms`, `utilization` |

Cada elemento de `placements`:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `instance_id` | string | Identificador da instância da peça (ex.: `"P1#1"`) — correlaciona com o `id` e a ordem do input |
| `bin` | number | Índice da chapa (0-based) onde a peça foi colocada |
| `x` | number | Posição X na chapa (mesma unidade do input, ex.: mm) |
| `y` | number | Posição Y na chapa |
| `rotation` | number | Rotação em graus (0, 90, etc.) |

**Como refletir no canvas:** para cada chapa (0 até `bins_used - 1`), desenhe um retângulo de tamanho `bin.width` x `bin.height`. Para cada item em `placements` com `bin === índice_da_chapa`, desenhe a peça correspondente a `instance_id` na posição `(x, y)` com rotação `rotation` (o polígono da peça vem do payload original de `parts`, identificado por `instance_id` que é `id#número`, ex.: `P1#1`).

## 5. Baixar o resultado (alternativa)

Com o `result_url` retornado quando o status é `SUCCEEDED` (sem `embed=result`):

```bash
curl -s "<result_url>" -o result.json
```

O JSON tem a mesma estrutura descrita acima: `bins_used`, `placements`, `metrics`.

## 6. Estrutura do JSON de entrada

| Campo     | Tipo   | Descrição |
|----------|--------|-----------|
| `units`  | string | Unidade (ex.: `"mm"`) |
| `bin`    | objeto | `width`, `height` (número) |
| `parts`  | array  | Lista de peças |
| `options`| objeto | Opcional: `spacing`, `rotations` (graus), `timeout_ms`, `selection` (`"djd"` ou `"first_fit"`), `try_triplets`, `initial_fill_proportion`, `waste_increment`. Por padrão usa **DJD** e rotações `[0, 90, 180, 270]`. |

**Modo máxima utilização (melhor aproveitamento de chapas):** Para priorizar utilização em vez de tempo, use `selection: "djd"`, `try_triplets: true`, `rotations: [0, 90, 180, 270]`, e um `timeout_ms` alto (ex.: 120000). Opcionalmente `waste_increment: 0.05` e `initial_fill_proportion: 0.33`. Aumente a variável de ambiente `ENGINE_TIMEOUT` do worker (em segundos) para pelo menos o valor de timeout_ms/1000. Benchmark em [benchmark/README.md](benchmark/README.md).

Cada elemento de `parts`:

- `id`: string
- `qty`: número de cópias
- `polygon`: array de `[x, y]` (contorno fechado; pode repetir o primeiro ponto no final)

## 7. Trocar ElasticMQ por SQS real

- Remova o serviço `elasticmq` do `docker-compose.yml` e use uma fila SQS na AWS.
- Defina nas variáveis de ambiente da API e do worker:
  - `SQS_ENDPOINT`: deixe em branco ou não defina (usa SQS padrão).
  - `SQS_QUEUE_URL`: URL completa da fila (ex.: `https://sqs.us-east-1.amazonaws.com/123456789012/nest-jobs`).
- Use credenciais AWS (IAM role, env ou profile) em vez de `minioadmin`.

## 8. Subir no ECS

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

## Configuração (variáveis de ambiente)

A API e o Worker leem todas as configurações de ambiente; o comportamento é compatível com **Digital Ocean** (MinIO no Droplet ou **Spaces**) e com **AWS** (SQS, DynamoDB, S3).

| Variável | Default | Descrição |
|----------|---------|-----------|
| `TABLE_NAME` | `nest_jobs` | Tabela DynamoDB |
| `QUEUE_NAME` | `nest-jobs` | Nome da fila SQS/ElasticMQ |
| `S3_BUCKET` | `nest-results` | Bucket S3 / MinIO / Spaces |
| `S3_ENDPOINT` | `http://minio:9000` | Endpoint S3-compatível (Spaces: `https://nyc3.digitaloceanspaces.com`) |
| `PRESIGNED_EXPIRY` | `600` | Expiração (segundos) da URL de resultado |
| `ENGINE_TIMEOUT` | `20` | Timeout do engine (segundos) |
| `SKIP_S3_INIT` | — | `1` para não criar bucket no init (ex.: usar Spaces já criado no painel) |

Para **Digital Ocean** use os arquivos `docker-compose.do.yml` (MinIO + persistência) ou `docker-compose.do.spaces.yml` (Spaces); exemplo de env em `.env.do.example`.

## Deploy em nuvem

- **Digital Ocean:** [docs/PASSO-A-PASSO-DIGITALOCEAN.md](docs/PASSO-A-PASSO-DIGITALOCEAN.md) – stack compatível com DO (Droplet + MinIO ou Spaces).
- **AWS:** [docs/PASSO-A-PASSO-AWS.md](docs/PASSO-A-PASSO-AWS.md) e [docs/PLANO-AWS.md](docs/PLANO-AWS.md).

## Estrutura do projeto

```
nest-local/
  docker-compose.yml
  docker-compose.do.yml          # Override DO (MinIO + volumes)
  docker-compose.do.spaces.yml   # Stack DO com Spaces (sem MinIO)
  .env.do.example
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
