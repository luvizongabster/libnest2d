# Status do Droplet (159.223.149.208)

## Verificação feita

- **SSH:** funcionando (`ssh root@159.223.149.208`).
- **Projeto:** em `/root/libnest2d/nest-local` (caminho em minúsculo).
- **Containers:** DynamoDB, ElasticMQ, MinIO, API e Worker foram criados e estão no compose com `docker-compose.do.yml`.
- **Firewall:** portas 22, 8080 e 9001 liberadas (ufw).
- **Problema:** o serviço **init** ficou preso (sem saída) e não criou a tabela `nest_jobs` nem o bucket no MinIO. A **API** não conclui o startup porque `wait_for_dependencies()` exige essa tabela e a fila SQS.

## Como corrigir (rodar no Droplet)

Conecte no Droplet e execute na ordem:

```bash
ssh root@159.223.149.208
cd /root/libnest2d/nest-local
```

**1. Criar a tabela DynamoDB e garantir o bucket MinIO (one-off):**

```bash
docker run --rm --network nest-local_default \
  -e DYNAMODB_ENDPOINT=http://dynamodb:8000 \
  -e S3_ENDPOINT=http://minio:9000 \
  -e S3_BUCKET=nest-results \
  -e TABLE_NAME=nest_jobs \
  -e AWS_ACCESS_KEY_ID=minioadmin \
  -e AWS_SECRET_ACCESS_KEY=minioadmin \
  nest-local-init
```

Se aparecer "Table already exists" e "Bucket already exists" (ou "Created"), siga.

**2. Reiniciar a API e o Worker:**

```bash
docker restart nest-local-api-1 nest-local-worker-1
```

**3. Aguardar ~30 segundos e testar:**

```bash
curl -s http://localhost:8080/health
```

Deve retornar: `{"status":"ok"}`.

**4. Testar pela internet:**

No seu computador:

```bash
curl http://159.223.149.208:8080/health
```

Se não responder, confira o firewall no painel da Digital Ocean (Droplet → Networking → Firewall). O ufw no servidor já permite 8080; pode haver um firewall de rede na DO na frente do Droplet.

## Comandos úteis

```bash
# Status dos containers
docker ps -a

# Logs da API
docker logs nest-local-api-1

# Reiniciar todo o stack (sem rebuild)
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d
```
