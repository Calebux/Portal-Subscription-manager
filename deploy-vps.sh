#!/bin/bash
# Deploy SubBot to VPS (run this ON the VPS)
# Usage: bash deploy-vps.sh
# Requires: A domain pointing to this server (for HTTPS)

set -e

APP_DIR="$HOME/subbot"
DOMAIN="${SUBBOT_DOMAIN:-subbot.example.com}"  # set SUBBOT_DOMAIN env var before running
REPO_URL="https://github.com/$(git remote get-url origin 2>/dev/null | sed 's|.*github.com[:/]||;s|\.git$||')" 2>/dev/null || true

echo "=== SubBot VPS Deploy ==="

# 1. Clone or pull
if [ -d "$APP_DIR" ]; then
  echo "[1/6] Pulling latest code..."
  cd "$APP_DIR"
  git pull
else
  echo "[1/6] Cloning repo..."
  if [ -n "$REPO_URL" ] && [ "$REPO_URL" != "https://github.com/" ]; then
    git clone "$REPO_URL" "$APP_DIR"
  else
    echo "No git remote found. Copy the project to $APP_DIR manually, then re-run."
    exit 1
  fi
  cd "$APP_DIR"
fi

# 2. Install Node deps
echo "[2/6] Installing dependencies..."
npm install --production

# 3. Create .env if missing
if [ ! -f "$APP_DIR/.env" ]; then
  echo "[3/6] Creating .env template..."
  cat > "$APP_DIR/.env" <<'EOF'
# SubBot environment — fill in your values
PORT=3747
DATA_DIR=/root/.hermes

# LLM (Nous Research / OpenAI-compatible)
OPENAI_API_KEY=
OPENAI_BASE_URL=https://inference-api.nousresearch.com/v1

# Celo contracts
AGENT_PRIVATE_KEY=
LOG_CONTRACT_ADDRESS=0x5bc06976e5b46fd624195EFdD0bFC45a73569003
CREDITS_CONTRACT_ADDRESS=
EOF
  echo "   → Edit $APP_DIR/.env with your keys"
else
  echo "[3/6] .env already exists, skipping"
fi

# 4. Set up systemd service
echo "[4/6] Setting up systemd service..."
sudo tee /etc/systemd/system/subbot.service > /dev/null <<EOF
[Unit]
Description=SubBot API Bridge
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$APP_DIR
ExecStart=$(which node) api-bridge.js
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable subbot
sudo systemctl restart subbot

# 5. Install nginx + certbot for HTTPS
echo "[5/6] Setting up HTTPS (nginx + Let's Encrypt)..."
if ! command -v nginx &>/dev/null; then
  sudo apt-get update -qq && sudo apt-get install -y -qq nginx certbot python3-certbot-nginx
fi

sudo tee /etc/nginx/sites-available/subbot > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:3747;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;

        # Security: don't leak server info
        proxy_hide_header X-Powered-By;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/subbot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 6. Obtain TLS certificate (skip if already exists)
echo "[6/6] Obtaining TLS certificate..."
if [ "$DOMAIN" != "subbot.example.com" ]; then
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" --redirect 2>/dev/null || \
    echo "   ⚠ Certbot failed — run manually: sudo certbot --nginx -d $DOMAIN"
else
  echo "   ⚠ Set SUBBOT_DOMAIN before running to enable HTTPS"
  echo "   Example: SUBBOT_DOMAIN=subbot.yourdomain.com bash deploy-vps.sh"
fi

echo ""
echo "=== Done! ==="
if [ "$DOMAIN" != "subbot.example.com" ]; then
  echo "SubBot running at https://$DOMAIN"
else
  echo "SubBot running at http://$(hostname -I | awk '{print $1}'):3747"
  echo "⚠ Set SUBBOT_DOMAIN and re-run to enable HTTPS"
fi
echo ""
echo "Commands:"
echo "  sudo systemctl status subbot    # check status"
echo "  sudo journalctl -u subbot -f    # view logs"
echo "  sudo systemctl restart subbot   # restart"
