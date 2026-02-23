# Droplet criado – concluir o deploy

Foi criado um Droplet na sua conta Digital Ocean:

| Campo    | Valor            |
|----------|------------------|
| **Nome** | nest-app         |
| **IP**   | 159.223.149.208  |
| **Região** | New York 1 (nyc1) |
| **Imagem** | Docker on Ubuntu 22.04 |
| **Tamanho** | 2 GB RAM / 1 vCPU |

O script de deploy não conseguiu conectar porque não há chave SSH cadastrada no Droplet (ou a senha foi enviada por e-mail e não dá para usá-la aqui).

---

## Opção 1 – Adicionar sua chave SSH e rodar o deploy

1. No painel da Digital Ocean: **Droplets** → **nest-app** → **Access** → **Reset Root Password** (se quiser) ou **Add SSH Key**.
2. Em **Security** → **SSH Keys**, adicione a chave pública da sua máquina (a que você usa no GitHub ou no terminal).
3. Se o Droplet já estava criado, associe a chave: **Droplets** → **nest-app** → **Access** → **Add SSH Key** e escolha a chave.
4. Na sua máquina (onde está o repositório), rode:

```bash
cd /Users/luvizon/Documents/GitHub/Libnest2D/nest-local
./deploy-do.sh 159.223.149.208
```

Se pedir confirmação do host (first connection), aceite. O script vai enviar os arquivos e subir o stack.

---

## Opção 2 – Usar a senha enviada por e-mail

A Digital Ocean envia por e-mail a **senha de root** do Droplet. Use-a assim:

1. Conecte por SSH (vai pedir a senha):

```bash
ssh root@159.223.149.208
```

2. No Droplet, instale git (se não tiver), clone o repositório e suba o stack:

```bash
apt-get update && apt-get install -y git
git clone https://github.com/SEU_USUARIO/Libnest2D.git
cd Libnest2D/nest-local
ufw allow 22 && ufw allow 8080 && ufw allow 9001 && ufw --force enable
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d --build
```

Troque `SEU_USUARIO/Libnest2D` pelo seu repositório. Se o código ainda não estiver no GitHub, use **Opção 3**.

---

## Opção 3 – Enviar o projeto da sua máquina com rsync (com senha)

Na **sua máquina** (não no Droplet), com a senha de root que você recebeu por e-mail:

```bash
cd /Users/luvizon/Documents/GitHub/Libnest2D
rsync -avz --exclude '.git' -e ssh ./ root@159.223.149.208:/root/Libnest2D/
```

Quando pedir a senha, use a do e-mail. Depois conecte no Droplet e suba o stack:

```bash
ssh root@159.223.149.208
cd /root/Libnest2D/nest-local
ufw allow 22 && ufw allow 8080 && ufw allow 9001 && ufw --force enable
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d --build
```

---

## Depois do deploy

- **API:** http://159.223.149.208:8080  
- **Health:** http://159.223.149.208:8080/health  
- **MinIO Console:** http://159.223.149.208:9001 (minioadmin / minioadmin)

O primeiro build pode levar alguns minutos (engine C++).
