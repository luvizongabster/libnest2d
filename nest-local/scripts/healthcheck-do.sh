#!/usr/bin/env bash
# Validação de saúde do sistema no Digital Ocean via doctl + SSH.
# Uso: ./scripts/healthcheck-do.sh [DROPLET_IP]
# Se DROPLET_IP não for passado, usa doctl para obter o IP do droplet nest-app.

set -e

DROPLET_IP="${1:-}"

if ! command -v doctl >/dev/null 2>&1; then
  echo "doctl não encontrado. Instale: https://docs.digitalocean.com/reference/doctl/how-to/install/"
  exit 1
fi

if [[ -z "$DROPLET_IP" ]]; then
  echo "Obtendo droplet nest-app via doctl..."
  DROPLET_IP=$(doctl compute droplet list --format Name,PublicIPv4 --no-header 2>/dev/null | awk '/nest-app/ {print $2}')
  if [[ -z "$DROPLET_IP" ]]; then
    echo "Nenhum droplet 'nest-app' encontrado. Passe o IP: $0 159.223.149.208"
    exit 1
  fi
fi

echo "=============================================="
echo "Validação de saúde – nest-app @ $DROPLET_IP"
echo "=============================================="

echo ""
echo "[doctl] Droplet na DO:"
doctl compute droplet list --format ID,Name,PublicIPv4,Status,Memory,VCPUs 2>/dev/null | head -5

echo ""
echo "[SSH] Recursos, disco e containers:"
ssh -o ConnectTimeout=10 -o BatchMode=yes "root@$DROPLET_IP" 'echo "Memória:"; free -h | grep Mem; echo "Disco /:"; df -h / | tail -1; echo ""; echo "Containers:"; cd /root/libnest2d/nest-local && docker compose -f docker-compose.yml -f docker-compose.do.yml ps -a 2>/dev/null' || {
  echo "Falha ao conectar por SSH em root@$DROPLET_IP. Verifique chave SSH e rede."
  exit 1
}

echo ""
echo "[API] Health local (porta 8080):"
ssh -o ConnectTimeout=5 "root@$DROPLET_IP" "curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8080/health && curl -s http://localhost:8080/health" || echo "API inacessível"

echo ""
echo "[Nginx] HTTPS (443):"
ssh -o ConnectTimeout=5 "root@$DROPLET_IP" "curl -s -k -o /dev/null -w 'HTTP %{http_code}\n' https://localhost:443/health" 2>/dev/null || true

echo ""
echo "=============================================="
echo "Validação concluída."
echo "=============================================="
