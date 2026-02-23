#!/usr/bin/env bash
# Deploy nest-local no Digital Ocean (Droplet).
# Uso: DROPLET_IP=1.2.3.4 ./deploy-do.sh   ou   ./deploy-do.sh 1.2.3.4
set -e

DROPLET_IP="${DROPLET_IP:-$1}"
DROPLET_USER="${DROPLET_USER:-root}"
SSH_OPTS="${SSH_OPTS:--o StrictHostKeyChecking=accept-new}"
NEST_DIR="${NEST_DIR:-/root/Libnest2D}"

if [ -z "$DROPLET_IP" ]; then
  echo "Defina o IP do Droplet:"
  echo "  export DROPLET_IP=SEU_IP"
  echo "  ./deploy-do.sh"
  echo "ou: ./deploy-do.sh SEU_IP"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE_NEST_LOCAL="$NEST_DIR/nest-local"

echo "=== Deploy para $DROPLET_USER@$DROPLET_IP ==="
echo "Enviando arquivos..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '.env' \
  "$REPO_ROOT/" "$DROPLET_USER@$DROPLET_IP:$NEST_DIR/"

echo "=== Configurando firewall e subindo stack ==="
ssh $SSH_OPTS "$DROPLET_USER@$DROPLET_IP" bash -s << REMOTE
set -e
cd $REMOTE_NEST_LOCAL
ufw allow 22/tcp 2>/dev/null || true
ufw allow 8080/tcp 2>/dev/null || true
ufw allow 9001/tcp 2>/dev/null || true
ufw --force enable 2>/dev/null || true
docker compose -f docker-compose.yml -f docker-compose.do.yml up -d --build
echo "Aguardando API..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://localhost:8080/health >/dev/null 2>&1; then break; fi
  sleep 3
done
curl -sf http://localhost:8080/health && echo "" || echo "Health check falhou (API pode ainda estar subindo)"
echo ""
echo "API: http://$DROPLET_IP:8080"
REMOTE

echo ""
echo "Deploy concluído. API: http://$DROPLET_IP:8080"
