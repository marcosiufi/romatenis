#!/bin/bash
# Configuração inicial do VPS Hetzner (Ubuntu 22.04 / 24.04)
# Execute como root: bash setup_server.sh
set -euo pipefail

echo "=== Setup do servidor Ranking de Tênis ==="

# ── 1. Sistema ─────────────────────────────────────────────────────────────────
apt-get update && apt-get upgrade -y
apt-get install -y git curl ufw

# ── 2. Docker ──────────────────────────────────────────────────────────────────
curl -fsSL https://get.docker.com | sh

# Adiciona o usuário atual ao grupo docker (requer logout/login para efetuar)
SUDO_USER="${SUDO_USER:-ubuntu}"
usermod -aG docker "$SUDO_USER"

# ── 3. Firewall ────────────────────────────────────────────────────────────────
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp   # HTTP/3 (QUIC)
ufw --force enable

echo ""
echo "=== Setup concluído ==="
echo ""
echo "Próximos passos:"
echo "  1. Deslogar e logar novamente (ou: newgrp docker)"
echo "  2. Clonar o repositório:"
echo "     git clone <repo-url> /opt/ranking-tenis"
echo "     cd /opt/ranking-tenis"
echo "  3. Copiar e preencher o .env:"
echo "     cp .env.example .env"
echo "     nano .env"
echo "  4. Executar o deploy:"
echo "     bash deploy.sh"
