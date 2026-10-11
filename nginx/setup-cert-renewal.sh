#!/usr/bin/env bash
# One-time, idempotent fix for TLS cert auto-renewal on the prod VM.
# Run on the VM from the repo dir: sudo bash nginx/setup-cert-renewal.sh
#
# 1. api.applaut.lvamo.com was issued with the standalone authenticator,
#    which needs port 80 free — but the nginx container holds port 80
#    permanently, so renewal would fail. Re-issue it with webroot (same as
#    api.jobref.lvamo.com), served by nginx's /.well-known/acme-challenge/
#    location from /var/www/certbot.
# 2. Install a deploy hook so nginx reloads after any renewal.
set -euo pipefail

cd "$(dirname "$0")"

APPLAUT_DOMAIN=api.applaut.lvamo.com
WEBROOT=/var/www/certbot

echo "==> Installing nginx reload deploy hook"
install -m 755 certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

if grep -q '^authenticator = standalone' "/etc/letsencrypt/renewal/${APPLAUT_DOMAIN}.conf"; then
    echo "==> Dry run: webroot challenge for ${APPLAUT_DOMAIN}"
    certbot certonly --webroot -w "$WEBROOT" -d "$APPLAUT_DOMAIN" \
        --cert-name "$APPLAUT_DOMAIN" --dry-run --non-interactive

    echo "==> Re-issuing ${APPLAUT_DOMAIN} with webroot"
    certbot certonly --webroot -w "$WEBROOT" -d "$APPLAUT_DOMAIN" \
        --cert-name "$APPLAUT_DOMAIN" --force-renewal --non-interactive
else
    echo "==> ${APPLAUT_DOMAIN} already uses webroot, skipping re-issue"
fi

echo "==> Reloading nginx to serve the current certs"
/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

echo "==> Dry run: renewing all certs"
certbot renew --dry-run

echo "==> Done"
certbot certificates
