#!/usr/bin/env bash
# LVAMO — production deploy script (shared backend for every vertical)
# Run on Oracle Cloud VM: bash deploy.sh
set -euo pipefail

COMPOSE="sudo docker compose --env-file .env.production -f docker-compose.prod.yml"

echo "==> Pulling latest code"
git pull origin main

echo "==> Building production images"
# ai-worker has its own image from the same code: build both, or it keeps the old code
$COMPOSE build --no-cache backend ai-worker

echo "==> Running database migrations"
$COMPOSE run --rm backend alembic upgrade head

echo "==> Restarting services"
$COMPOSE up -d

echo "==> Cleaning up unused images"
sudo docker image prune -f

echo "==> Done. Services:"
$COMPOSE ps
