# Análise Completa e Melhorias - Nest Local

## Sumário Executivo

A aplicação **Nest Local** é um microserviço de otimização 2D (nesting) que usa a biblioteca libnest2d para arranjar peças em chapas, minimizando desperdício. A arquitetura é bem estruturada com separação clara de responsabilidades, mas há diversas oportunidades de melhoria em segurança, performance, observabilidade e qualidade de código.

---

## 1. Arquitetura Atual

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    CLIENTE                                       │
│                              (Browser/Frontend)                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               NGINX (80/443)                                     │
│                          HTTPS + CORS + S3 Proxy                                │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
┌─────────────────────────────┐               ┌─────────────────────────────┐
│         API (8080)          │               │       MinIO S3 (9000)       │
│          FastAPI            │               │      (via /s3/ proxy)       │
└─────────────────────────────┘               └─────────────────────────────┘
           │           │
           │           ▼
           │   ┌─────────────────┐
           │   │  DynamoDB (8000) │
           │   └─────────────────┘
           │           ▲
           ▼           │
┌─────────────────┐    │
│ ElasticMQ (9324)│    │
│      SQS        │    │
└─────────────────┘    │
           │           │
           ▼           │
┌─────────────────────────────┐
│         WORKER              │
│   (Python + nest_engine)    │──────────────────┐
└─────────────────────────────┘                  │
                                                 ▼
                                      ┌─────────────────────────────┐
                                      │       MinIO S3 (9000)       │
                                      │    (upload de resultados)   │
                                      └─────────────────────────────┘
```

### Componentes

| Serviço | Tecnologia | Função |
|---------|------------|--------|
| API | FastAPI (Python 3.12) | Recebe jobs, retorna status e URLs de resultado |
| Worker | Python 3.12 + boto3 | Consome fila SQS, executa engine, salva resultados |
| Engine | C++14 + libnest2d | Executa algoritmo de nesting |
| Init | Python | Cria tabela DynamoDB e bucket S3 |
| Nginx | nginx:alpine | Reverse proxy, HTTPS, CORS |
| ElasticMQ | SQS-compatible | Fila de mensagens |
| DynamoDB | amazon/dynamodb-local | Banco de dados de jobs |
| MinIO | minio/minio | Armazenamento S3-compatible |

---

## 2. Problemas Identificados

### 2.1 Segurança

| # | Problema | Severidade | Arquivo |
|---|----------|------------|---------|
| S1 | **CORS permite todas as origens** (`allow_origins=["*"]`) | Alta | `api/app.py:105` |
| S2 | **Sem autenticação/autorização** na API | Alta | `api/app.py` |
| S3 | **Credenciais hardcoded** nos docker-compose | Média | `docker-compose.yml` |
| S4 | **Sem rate limiting** - vulnerável a DoS | Média | `api/app.py` |
| S5 | **Sem validação de entrada** no payload | Média | `api/app.py:118` |

### 2.2 Performance e Escalabilidade

| # | Problema | Severidade | Arquivo |
|---|----------|------------|---------|
| P1 | **Worker single-threaded** - processa 1 job por vez | Alta | `worker/worker.py:114-126` |
| P2 | **Boto3 blocking calls no event loop** | Baixa | `api/app.py:74-92` |
| P3 | **Sem cache de conexões boto3** otimizado | Baixa | Geral |
| P4 | **DynamoDB sem índices secundários** para queries | Média | `init/init_infra.py` |

### 2.3 Resiliência e Confiabilidade

| # | Problema | Severidade | Arquivo |
|---|----------|------------|---------|
| R1 | **Sem graceful shutdown** no worker | Alta | `worker/worker.py` |
| R2 | **Sem Dead Letter Queue (DLQ)** para mensagens falhas | Média | Configuração SQS |
| R3 | **Sem retry com backoff exponencial** | Média | `worker/worker.py` |
| R4 | **Jobs órfãos** - podem ficar em RUNNING para sempre | Média | Worker |
| R5 | **Sem TTL/limpeza** de jobs antigos no DynamoDB | Baixa | Schema |

### 2.4 Observabilidade

| # | Problema | Severidade | Arquivo |
|---|----------|------------|---------|
| O1 | **Sem logging estruturado** | Alta | Todos |
| O2 | **Sem métricas/health check** no worker | Alta | `worker/worker.py` |
| O3 | **Sem tracing distribuído** (job_id nos logs) | Média | Todos |
| O4 | **Código de debug deixado em produção** (`_append_debug_log`) | Baixa | `api/app.py:39-47` |

### 2.5 Qualidade de Código

| # | Problema | Severidade | Arquivo |
|---|----------|------------|---------|
| Q1 | **Duplicação de configuração** entre API e Worker | Média | `app.py`, `worker.py` |
| Q2 | **Sem Pydantic models** para validação de payload | Média | `api/app.py` |
| Q3 | **Sem type hints** em várias funções | Baixa | Vários |
| Q4 | **Sem testes automatizados** | Alta | N/A |
| Q5 | **Sem .dockerignore** - builds lentos | Baixa | N/A |

### 2.6 Infraestrutura

| # | Problema | Severidade | Arquivo |
|---|----------|------------|---------|
| I1 | **DynamoDB perde dados** no docker-compose.yml principal | Média | `docker-compose.yml:115` |
| I2 | **Nginx hardcoded** para domínio específico | Baixa | `nginx/nginx.conf:4,20` |
| I3 | **Sem resource limits** nos containers | Média | `docker-compose.yml` |

---

## 3. Melhorias Sugeridas

### Prioridade 1 - Crítica (Segurança e Estabilidade)

#### 3.1.1 Adicionar Validação de Entrada com Pydantic

```python
# api/app.py - Adicionar modelos Pydantic
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class Point(BaseModel):
    x: float = Field(..., alias="0")
    y: float = Field(..., alias="1")

class Part(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    qty: int = Field(default=1, ge=1, le=1000)
    polygon: List[List[float]] = Field(..., min_length=3)
    
    @validator('polygon')
    def validate_polygon(cls, v):
        if len(v) < 3:
            raise ValueError('Polygon must have at least 3 points')
        for point in v:
            if len(point) != 2:
                raise ValueError('Each point must have exactly 2 coordinates')
        return v

class Bin(BaseModel):
    width: float = Field(..., gt=0, le=100000)
    height: float = Field(..., gt=0, le=100000)

class Options(BaseModel):
    spacing: float = Field(default=0.0, ge=0)
    rotations: List[float] = Field(default=[0.0, 90.0])
    timeout_ms: int = Field(default=0, ge=0, le=300000)

class NestingJobRequest(BaseModel):
    units: str = Field(default="mm", pattern="^(mm|m|cm|in)$")
    bin: Bin
    parts: List[Part] = Field(..., min_length=1, max_length=10000)
    options: Optional[Options] = None

@app.post("/jobs")
def create_job(payload: NestingJobRequest):
    # ... código existente usando payload.dict()
```

#### 3.1.2 Adicionar Rate Limiting

```python
# api/app.py - Adicionar rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/jobs")
@limiter.limit("10/minute")
def create_job(request: Request, payload: NestingJobRequest):
    # ...
```

#### 3.1.3 Graceful Shutdown no Worker

```python
# worker/worker.py - Adicionar signal handling
import signal
import threading

shutdown_event = threading.Event()

def signal_handler(signum, frame):
    print(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def main():
    while not shutdown_event.is_set():
        try:
            r = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=5,  # Reduzido para verificar shutdown mais frequentemente
            )
            for msg in r.get("Messages", []):
                if shutdown_event.is_set():
                    print("Shutdown requested, not processing new messages")
                    break
                process_message(msg)
        except Exception as e:
            if not shutdown_event.is_set():
                print(e)
                time.sleep(5)
    print("Worker shutdown complete")
```

### Prioridade 2 - Alta (Observabilidade)

#### 3.2.1 Logging Estruturado

```python
# shared/logging_config.py
import logging
import json
import sys
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, 'job_id'):
            log_data['job_id'] = record.job_id
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def setup_logging(service_name: str):
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    return logger

# Uso:
logger = setup_logging("worker")
logger.info("Processing job", extra={"job_id": job_id})
```

#### 3.2.2 Health Check no Worker

```python
# worker/worker.py - Adicionar health endpoint
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import json

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            status = {
                "status": "healthy",
                "jobs_processed": jobs_processed_count,
                "last_job_time": last_job_timestamp,
                "uptime_seconds": time.time() - start_time
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress access logs

def start_health_server():
    server = HTTPServer(("0.0.0.0", 8081), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
```

### Prioridade 3 - Média (Performance)

#### 3.3.1 Worker com Concorrência

```python
# worker/worker.py - Usar ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor
import os

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "2"))

def main():
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while not shutdown_event.is_set():
            try:
                r = sqs.receive_message(
                    QueueUrl=SQS_QUEUE_URL,
                    MaxNumberOfMessages=MAX_WORKERS,
                    WaitTimeSeconds=5,
                )
                futures = []
                for msg in r.get("Messages", []):
                    if shutdown_event.is_set():
                        break
                    futures.append(executor.submit(process_message, msg))
                
                # Aguardar conclusão
                for future in futures:
                    try:
                        future.result(timeout=ENGINE_TIMEOUT + 30)
                    except Exception as e:
                        logger.error(f"Worker thread error: {e}")
            except Exception as e:
                if not shutdown_event.is_set():
                    logger.error(f"Main loop error: {e}")
                    time.sleep(5)
```

#### 3.3.2 Configuração Centralizada

```python
# shared/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # AWS/Local
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_default_region: str = "us-east-1"
    
    # Endpoints
    sqs_endpoint: str = "http://elasticmq:9324"
    sqs_queue_url: str = ""
    dynamodb_endpoint: str = "http://dynamodb:8000"
    s3_endpoint: str = "http://minio:9000"
    s3_public_endpoint: str = ""
    
    # Nomes
    table_name: str = "nest_jobs"
    queue_name: str = "nest-jobs"
    s3_bucket: str = "nest-results"
    
    # Timeouts
    engine_timeout: int = 20
    presigned_expiry: int = 600
    
    @property
    def use_real_aws(self) -> bool:
        return bool(self.sqs_queue_url and self.sqs_queue_url.startswith("https://sqs."))
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### Prioridade 4 - Baixa (Qualidade de Código)

#### 3.4.1 Adicionar .dockerignore

```dockerfile
# .dockerignore
.git
.gitignore
__pycache__
*.pyc
*.pyo
*.egg-info
.pytest_cache
.mypy_cache
.coverage
htmlcov
*.log
.env*
!.env.example
*.md
docs/
plans/
tests/
.cursor/
```

#### 3.4.2 Remover Código de Debug

Remover todas as regiões `# #region agent log` dos arquivos:
- `api/app.py`
- `init/init_infra.py`

#### 3.4.3 Adicionar Resource Limits ao Docker Compose

```yaml
# docker-compose.yml
services:
  api:
    # ...
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M

  worker:
    # ...
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M
```

---

## 4. Testes Recomendados

### 4.1 Estrutura de Testes

```
tests/
├── conftest.py
├── unit/
│   ├── test_api.py
│   ├── test_worker.py
│   └── test_engine.py
├── integration/
│   ├── test_api_integration.py
│   └── test_worker_integration.py
└── e2e/
    └── test_full_flow.py
```

### 4.2 Exemplo de Teste Unitário

```python
# tests/unit/test_api.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    from api.app import app
    return TestClient(app)

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_create_job_valid_payload(client):
    payload = {
        "units": "mm",
        "bin": {"width": 500, "height": 500},
        "parts": [
            {"id": "P1", "qty": 1, "polygon": [[0,0], [100,0], [100,50], [0,50]]}
        ]
    }
    with patch('api.app.sqs') as mock_sqs, \
         patch('api.app.dynamodb') as mock_ddb:
        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table
        
        response = client.post("/jobs", json=payload)
        
        assert response.status_code == 200
        assert "job_id" in response.json()

def test_create_job_invalid_payload(client):
    payload = {"invalid": "payload"}
    response = client.post("/jobs", json=payload)
    assert response.status_code == 422  # Validation error
```

---

## 5. Roadmap de Implementação

### Fase 1 - Estabilização (1-2 dias)
- [ ] Adicionar validação Pydantic nos endpoints
- [ ] Implementar graceful shutdown no worker
- [ ] Remover código de debug
- [ ] Adicionar .dockerignore
- [ ] Corrigir persistência do DynamoDB

### Fase 2 - Observabilidade (1-2 dias)
- [ ] Implementar logging estruturado (JSON)
- [ ] Adicionar health check no worker
- [ ] Adicionar métricas básicas
- [ ] Configurar log levels por ambiente

### Fase 3 - Segurança (1-2 dias)
- [ ] Implementar rate limiting
- [ ] Configurar CORS restrito por ambiente
- [ ] Externalizar credenciais para secrets
- [ ] Adicionar autenticação básica (API key)

### Fase 4 - Performance (2-3 dias)
- [ ] Worker com ThreadPoolExecutor
- [ ] Configuração centralizada com Pydantic Settings
- [ ] Resource limits no Docker Compose
- [ ] Dead Letter Queue (DLQ)

### Fase 5 - Qualidade (2-3 dias)
- [ ] Adicionar testes unitários
- [ ] Adicionar testes de integração
- [ ] CI/CD pipeline com testes
- [ ] Documentação de API (OpenAPI/Swagger)

---

## 6. Conclusão

A aplicação tem uma arquitetura sólida e bem organizada, mas precisa de melhorias em:

1. **Segurança**: Validação de entrada, rate limiting, autenticação
2. **Resiliência**: Graceful shutdown, DLQ, retries
3. **Observabilidade**: Logging estruturado, métricas, health checks
4. **Qualidade**: Testes, configuração centralizada, código limpo

As melhorias sugeridas são incrementais e podem ser implementadas sem grandes refatorações na arquitetura existente.
