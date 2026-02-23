# Passo a passo: subir o Nest no Digital Ocean

Este guia leva o ambiente **nest-local** (API, Worker, ElasticMQ, DynamoDB Local, MinIO ou Spaces) para um **Droplet** no Digital Ocean. O projeto está refatorado para **compatibilidade total** com DO: todas as configurações vêm de variáveis de ambiente e há compose específicos para DO.

---

## Arquivos para Digital Ocean (nest-local/)

| Arquivo | Uso |
|---------|-----|
| **docker-compose.do.yml** | Override para DO com **MinIO no Droplet**: persiste dados do DynamoDB e do MinIO em volumes. Use: `docker compose -f docker-compose.yml -f docker-compose.do.yml up -d` |
| **docker-compose.do.spaces.yml** | Stack completo para DO com **Spaces** (S3-compatível): sem container MinIO; exige `.env` com `S3_ENDPOINT`, `S3_BUCKET` e chaves. Use: `docker compose -f docker-compose.do.spaces.yml up -d` |
| **.env.do.example** | Exemplo de variáveis; copie para `.env` e preencha (não commite `.env`). |

Variáveis configuráveis em todos os ambientes: `TABLE_NAME`, `QUEUE_NAME`, `S3_BUCKET`, `S3_ENDPOINT`, `PRESIGNED_EXPIRY`, `ENGINE_TIMEOUT`, `ERROR_MAX_LEN`. Com **Spaces**, defina `SKIP_S3_INIT=1` (o bucket é criado no painel DO).

---

## Visão geral

| Componente | Onde roda no DO |
|------------|------------------|
| API (FastAPI) | Container no Droplet, porta 8080 |
| Worker | Container no Droplet |
| ElasticMQ (fila) | Container no Droplet |
| DynamoDB Local | Container no Droplet (em memória ou com volume) |
| MinIO (S3) | Container no Droplet (ou opcionalmente **DO Spaces**) |

**Requisitos:** conta no [Digital Ocean](https://www.digitalocean.com/), cartão ou método de pagamento.

---

## Parte 1 – Criar o Droplet

### 1.1 Pelo Console Digital Ocean

1. Acesse [cloud.digitalocean.com](https://cloud.digitalocean.com/) e faça login.
2. **Droplets** → **Create Droplet**.

**Escolha da imagem:**

- **One-click apps** → **Docker** (recomendado: já vem com Docker instalado).  
  Ou **Ubuntu 24.04 LTS** e instale Docker manualmente (ver 1.2).

**Plano:**

- **Basic** ou **Premium**; para começar: **Regular** com **2 GB RAM / 1 vCPU** (mínimo recomendado para build do engine C++ e vários containers).  
- Se for só para testar com poucos jobs: **1 GB** pode funcionar (build pode ser mais lento).

**Região:**

- Escolha a mais próxima dos usuários (ex.: **New York** ou **São Paulo** se disponível).

**Autenticação:**

- **SSH key** (recomendado) ou **Password**.  
- Se usar chave: adicione sua chave pública em **Security** → **SSH Keys** e selecione no Droplet.

**Hostname:**

- Ex.: `nest-app` ou `nest-production`.

3. **Create Droplet**. Anote o **IP público** do Droplet.

### 1.2 Se escolheu Ubuntu (sem one-click Docker)

Conecte por SSH e instale Docker e Docker Compose:

```bash
ssh root@<IP_DO_DROPLET>

# Docker
apt-get update && apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verificar
docker --version
docker compose version
```

Se usou a one-click **Docker**, pule para a Parte 2.

---

## Parte 2 – Acessar o Droplet e preparar o projeto

### 2.1 Conectar por SSH

```bash
ssh root@<IP_DO_DROPLET>
```

(Substitua pelo IP do seu Droplet.)

### 2.2 Clonar o repositório (recomendado)

Se o código está no GitHub:

```bash
apt-get update && apt-get install -y git
git clone https://github.com/SEU_USUARIO/Libnest2D.git
cd Libnest2D/nest-local
```

Troque `SEU_USUARIO/Libnest2D` pelo seu usuário e nome do repositório. Se for repositório privado, use um token ou configure SSH no Droplet.

### 2.3 Alternativa: enviar os arquivos com scp/rsync

Na **sua máquina** (não no Droplet), na pasta do projeto:

```bash
rsync -avz --exclude '.git' /Users/luvizon/Documents/GitHub/Libnest2D/ root@<IP_DO_DROPLET>:/root/Libnest2D/
ssh root@<IP_DROPLET> "cd /root/Libnest2D/nest-local && pwd"
```

No Droplet, entre na pasta:

```bash
cd /root/Libnest2D/nest-local
```

---

## Parte 3 – Firewall (portas)

Libere a porta da API (e opcionalmente a do console do MinIO) no firewall do Droplet:

```bash
ufw allow 22/tcp
ufw allow 8080/tcp
ufw allow 9001/tcp
ufw --force enable
ufw status
```

- **8080:** API (obrigatório para acesso externo).
- **9001:** Console do MinIO (opcional; só se quiser acessar a interface do MinIO pela web).

---

## Parte 4 – Subir o stack com Docker Compose

Na pasta `nest-local` no Droplet. Escolha uma das opções:

**Opção A – MinIO no Droplet (com persistência em disco)**

```bash
cd /root/Libnest2D/nest-local
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d --build
```

**Opção B – Digital Ocean Spaces (sem container MinIO)**

1. Crie um Space no painel DO e gere uma Spaces API key.
2. Copie o exemplo de env e preencha: `cp .env.do.example .env` e edite `.env` com `S3_ENDPOINT`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`; defina `SKIP_S3_INIT=1`.
3. Suba o stack:

```bash
docker compose -f docker-compose.do.spaces.yml up -d --build
```

**Opção C – Stack local padrão (sem volumes persistentes)**

```bash
docker compose up -d --build
```

O primeiro build pode levar vários minutos (especialmente o **engine** C++). Acompanhe os logs, se quiser:

```bash
docker compose logs -f
```

Quando o `init` terminar e a API estiver saudável, você pode sair com `Ctrl+C` (os containers continuam rodando em segundo plano).

**Verificar:**

```bash
docker compose ps
curl -s http://localhost:8080/health
```

Resposta esperada: `{"status":"ok"}`.

---

## Parte 5 – Acessar a API pela internet

- **URL da API:** `http://<IP_DO_DROPLET>:8080`
- **Exemplo:** `http://164.92.123.45:8080/health`
- **Criar job:** `POST http://<IP_DO_DROPLET>:8080/jobs` (mesmo payload do README).

**MinIO Console (opcional):** `http://<IP_DO_DROPLET>:9001` (usuário/senha: `minioadmin` / `minioadmin`).

---

## Parte 6 – Persistência

Ao usar **MinIO no Droplet**, use o override oficial para DO, que já define volumes para DynamoDB e MinIO:

```bash
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d
```

Assim, dados do MinIO e do DynamoDB Local persistem entre reinícios (evite `docker compose down -v` se quiser manter os volumes). Com **Spaces** (`docker-compose.do.spaces.yml`), o DynamoDB Local também usa volume; o armazenamento de resultados fica no Spaces.

---

## Parte 7 – Domínio e HTTPS (opcional)

Para usar um domínio (ex.: `api.seudominio.com`) e HTTPS com certificado gratuito:

1. No Digital Ocean, aponte o **DNS** do domínio para o IP do Droplet (registro A).
2. No Droplet, instale um proxy reverso com SSL (ex.: **Caddy**):

```bash
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy

# Exemplo: proxy para a API na porta 8080
echo 'api.seudominio.com { reverse_proxy localhost:8080 }' > /etc/caddy/Caddyfile
systemctl reload caddy
```

O Caddy obtém e renova o certificado HTTPS automaticamente. Acesse `https://api.seudominio.com`.

---

## Parte 8 – Usar Digital Ocean Spaces (opcional, em vez de MinIO)

Se quiser usar **Spaces** (S3-compatível) como armazenamento dos resultados em vez do MinIO no Droplet:

1. No Digital Ocean: **Spaces** → **Create Space** (ex.: região `nyc3`, nome `nest-results`).
2. Gere uma **Spaces API key**: **API** → **Spaces Keys** → **Generate New Key**; anote **Access Key** e **Secret**.
3. No servidor, crie um arquivo de ambiente (ex.: `.env.spaces`) na pasta `nest-local`:

```bash
# .env.spaces (exemplo; não commitar com chaves reais)
S3_ENDPOINT=https://nyc3.digitaloceanspaces.com
S3_BUCKET=nest-results
AWS_ACCESS_KEY_ID=<SPACES_ACCESS_KEY>
AWS_SECRET_ACCESS_KEY=<SPACES_SECRET_KEY>
AWS_DEFAULT_REGION=us-east-1
```

4. Crie um bucket com o mesmo nome no Space (ou use o nome do Space como bucket).
5. Use um compose override que **substitui apenas o MinIO** pelos Spaces: desligue o serviço `minio`, passe as variáveis acima para `api`, `worker` e `init`, e ajuste o endpoint no init (o init hoje cria bucket no MinIO; com Spaces o bucket já existe). Exemplo mínimo de override (só env para api e worker):

**Exemplo `docker-compose.spaces.yml` (rodar com `docker compose -f docker-compose.yml -f docker-compose.spaces.yml up -d`):**

```yaml
# docker-compose.spaces.yml - usar com: docker compose -f docker-compose.yml -f docker-compose.spaces.yml up -d
# Requer: criar o Space e o bucket no DO; definir variáveis no .env ou aqui (não commitar .env com chaves).
services:
  init:
    environment:
      S3_ENDPOINT: ${S3_ENDPOINT}
      S3_BUCKET: ${S3_BUCKET}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
  api:
    environment:
      S3_ENDPOINT: ${S3_ENDPOINT}
      S3_BUCKET: ${S3_BUCKET}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
  worker:
    environment:
      S3_ENDPOINT: ${S3_ENDPOINT}
      S3_BUCKET: ${S3_BUCKET}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
  minio:
    profiles:
      - donotstart
```

E descomente ou adicione no `docker-compose.yml` um `profiles: ["default"]` no MinIO e use `profiles: ["donotstart"]` no override para não subir o MinIO quando usar Spaces. Como o init precisa do S3 para criar o bucket, com Spaces você cria o bucket manualmente no painel e pode rodar o init com as mesmas variáveis (o init vai dar “bucket already exists” e seguir). Para simplificar, pode manter MinIO no Droplet e migrar para Spaces depois.

*(Resumo: com Spaces você configura endpoint + bucket + chaves nas variáveis de ambiente da API/Worker/init e pode desabilitar o container MinIO.)*

---

## Resumo dos comandos (referência rápida)

```bash
# No Droplet, após clonar ou enviar o projeto
cd /root/Libnest2D/nest-local
ufw allow 22 && ufw allow 8080 && ufw allow 9001 && ufw --force enable

# Com MinIO no Droplet (recomendado; persiste dados)
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d --build

# Ou com Spaces (configure .env antes)
docker compose -f docker-compose.do.spaces.yml up -d --build

curl http://localhost:8080/health
# API pública: http://<IP>:8080
```

**Reiniciar o stack (MinIO no Droplet):**

```bash
cd /root/Libnest2D/nest-local
docker compose -f docker-compose.yml -f docker-compose.do.yml down
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d
```

**Atualizar após mudanças no repositório:**

```bash
cd /root/Libnest2D && git pull
cd nest-local
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d --build
```

---

## Troubleshooting

- **Build do engine falha por falta de memória:** use um Droplet com pelo menos 2 GB RAM ou aumente o swap temporariamente (`fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`).
- **API não responde na porta 8080:** confira `docker compose ps` e `docker compose logs api`; verifique se o firewall liberou 8080 (`ufw status`).
- **“address already in use”:** outra aplicação está usando a porta; pare o serviço ou mude a porta no `docker-compose.yml` (ex.: `"8081:8080"`).

Com isso, o ambiente sobe no Digital Ocean e a API fica acessível em `http://<IP_DO_DROPLET>:8080`.
