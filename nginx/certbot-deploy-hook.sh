#!/bin/sh
# certbot deploy hook — installed to /etc/letsencrypt/renewal-hooks/deploy/
# by setup-cert-renewal.sh. certbot runs it (as root) once after any cert
# renews successfully. Without it, nginx keeps serving the old cert from
# memory until the container restarts, so a "successful" renewal still
# ends in an expired cert being served.
set -e

container=$(docker ps -q --filter label=com.docker.compose.service=nginx)
if [ -n "$container" ]; then
    docker exec "$container" nginx -s reload
fi
