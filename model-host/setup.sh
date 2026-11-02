#!/usr/bin/env bash
# Turn a fresh Ubuntu 24.04 Ampere VM into an Applaut AI model host.
#
#   LLAMA_API_KEY=<the app's APPLAUT_LLM_API_KEY> ./setup.sh <wg-address> <app-wg-public-key> <app-public-ip>
#   e.g.  LLAMA_API_KEY=... ./setup.sh 10.8.0.3 'AbC...=' 130.61.106.172
#
# Installs Docker and WireGuard, makes this VM a WireGuard peer of the app VM
# (UDP 51820 open to the app VM only), downloads and verifies the models,
# starts both servers. Prints the lines to add on the app VM. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

WG_ADDRESS=${1:?wg address, e.g. 10.8.0.3}
APP_PUBKEY=${2:?the app VM WireGuard public key}
APP_IP=${3:?the app VM public IP}
: "${LLAMA_API_KEY:?set LLAMA_API_KEY (same as APPLAUT_LLM_API_KEY on the app VM)}"

sudo apt-get update -q
sudo apt-get install -y -q docker.io docker-compose-v2 wireguard iptables-persistent curl python3
sudo usermod -aG docker "$USER"

# --- WireGuard: this host listens; the app VM (10.8.0.1) is the only peer
sudo install -d -m 700 /etc/wireguard
if ! sudo test -f /etc/wireguard/private.key; then
  wg genkey | sudo tee /etc/wireguard/private.key >/dev/null
  sudo chmod 600 /etc/wireguard/private.key
fi
PUBKEY=$(sudo cat /etc/wireguard/private.key | wg pubkey)
sudo tee /etc/wireguard/wg0.conf >/dev/null <<EOF
[Interface]
Address = $WG_ADDRESS/24
ListenPort = 51820
PrivateKey = $(sudo cat /etc/wireguard/private.key)

[Peer]
PublicKey = $APP_PUBKEY
AllowedIPs = 10.8.0.1/32
EOF
sudo chmod 600 /etc/wireguard/wg0.conf
sudo systemctl enable --now wg-quick@wg0
sudo systemctl restart wg-quick@wg0

# Ubuntu's own iptables rejects inbound traffic by default; allow WireGuard from the app VM only.
sudo iptables -C INPUT -p udp --dport 51820 -s "$APP_IP" -j ACCEPT 2>/dev/null \
  || sudo iptables -I INPUT 5 -p udp --dport 51820 -s "$APP_IP" -j ACCEPT
sudo netfilter-persistent save

# --- .env (key and address); update.sh adds the model lines
[[ -f .env ]] || cp .env.example .env
sed -i -E "s|^LLAMA_API_KEY=.*|LLAMA_API_KEY=$LLAMA_API_KEY|; s|^WG_ADDRESS=.*|WG_ADDRESS=$WG_ADDRESS|" .env
chmod 600 .env

sudo -u "$USER" sg docker -c "./update.sh --no-pull"

PUBLIC_IP=$(curl -fsS https://ifconfig.me || echo "<this VM's public IP>")
cat <<EOF

Done. On the app VM:
1. Add to /etc/wireguard/wg0.conf, then: sudo systemctl restart wg-quick@wg0

[Peer]
PublicKey = $PUBKEY
Endpoint = $PUBLIC_IP:51820
AllowedIPs = $WG_ADDRESS/32
PersistentKeepalive = 25

2. Append $WG_ADDRESS to APPLAUT_MODEL_HOSTS in .env.production, then:
   docker compose -f docker-compose.prod.yml up -d ai-worker
3. In OCI: security list ingress UDP 51820 from $APP_IP/32.
EOF
