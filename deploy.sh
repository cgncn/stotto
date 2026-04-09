#!/bin/bash
set -e

SERVER="root@178.104.32.74"
SSH_KEY="/tmp/stotto_deploy_key"
REPO="https://github.com/cgncn/stotto.git"
APP_DIR="/root/stotto"

echo "==> Connecting to server..."
ssh -i $SSH_KEY $SERVER bash << 'ENDSSH'
set -e

APP_DIR="/root/stotto"

# ── Install dependencies if needed ─────────────────────────────────────────
if ! command -v nginx &> /dev/null; then
  echo "==> Installing Nginx & Certbot..."
  apt-get update -q
  apt-get install -y nginx certbot python3-certbot-nginx
fi

# ── Clone or pull repo ─────────────────────────────────────────────────────
if [ ! -d "$APP_DIR" ]; then
  echo "==> Cloning repo..."
  git clone https://github.com/cgncn/stotto.git $APP_DIR
else
  echo "==> Pulling latest code..."
  cd $APP_DIR && git pull
fi

cd $APP_DIR

# ── Check .env exists ──────────────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "ERROR: .env file missing. Upload it first with:"
  echo "  scp -i /tmp/stotto_deploy_key .env root@178.104.32.74:/root/stotto/.env"
  exit 1
fi

# ── Build & start containers ───────────────────────────────────────────────
echo "==> Building and starting containers..."
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --build

# ── Run migrations ─────────────────────────────────────────────────────────
echo "==> Running database migrations..."
sleep 5
docker compose exec -T backend alembic upgrade head

echo "==> Containers running:"
docker compose ps

ENDSSH

echo ""
echo "==> Copying Nginx config..."
scp -i $SSH_KEY nginx/stotto.conf $SERVER:/etc/nginx/sites-available/stotto.conf
ssh -i $SSH_KEY $SERVER "ln -sf /etc/nginx/sites-available/stotto.conf /etc/nginx/sites-enabled/stotto.conf"

echo "==> Testing Nginx config..."
ssh -i $SSH_KEY $SERVER "nginx -t"

echo ""
echo "=========================================="
echo " NEXT STEPS (run manually on the server):"
echo "=========================================="
echo ""
echo "1. Get SSL certificates:"
echo "   certbot --nginx -d stotto.com.tr -d www.stotto.com.tr"
echo "   certbot --nginx -d api.stotto.com.tr"
echo ""
echo "2. Reload Nginx:"
echo "   systemctl reload nginx"
echo ""
echo "Done! STOTTO should be live at https://stotto.com.tr"
