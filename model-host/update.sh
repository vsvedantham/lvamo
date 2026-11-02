#!/usr/bin/env bash
# Bring this model host to the models in backend/app/applaut/ai/models.lock:
# download what's missing, verify every checksum, write the SCORER_* /
# WRITER_* lines of .env, restart, wait until both servers answer.
#   ./update.sh            pull the repo first
#   ./update.sh --no-pull  use the checkout as it is
set -euo pipefail
cd "$(dirname "$0")"
LOCK=../backend/app/applaut/ai/models.lock

[[ "${1:-}" == "--no-pull" ]] || git -C .. pull --ff-only
[[ -f .env ]] || { echo "No .env here: run setup.sh first (or copy .env.example)"; exit 1; }
mkdir -p models

declare -A FILE ALIAS
while read -r task alias sha file url; do
  [[ -z "$task" || "$task" == \#* ]] && continue
  if [[ ! -f "models/$file" ]] || ! echo "$sha  models/$file" | sha256sum -c --status; then
    echo "Downloading $file ..."
    curl -fL --retry 3 -o "models/$file.part" "$url"
    echo "$sha  models/$file.part" | sha256sum -c --quiet
    mv "models/$file.part" "models/$file"
  fi
  FILE[$task]=$file
  # What the server reports as its model id; the app checks it per port.
  ALIAS[$task]="$task:$alias@${sha:0:8}"
done < "$LOCK"

for task in scorer writer; do
  [[ -n "${FILE[$task]:-}" ]] || { echo "models.lock has no '$task' line"; exit 1; }
done

# Rewrite only the model lines of .env; keep the key, address and cores.
grep -vE '^(SCORER|WRITER)_(FILE|ALIAS)=' .env > .env.new || true
{
  echo "SCORER_FILE=${FILE[scorer]}"; echo "SCORER_ALIAS=${ALIAS[scorer]}"
  echo "WRITER_FILE=${FILE[writer]}"; echo "WRITER_ALIAS=${ALIAS[writer]}"
} >> .env.new
mv .env.new .env
chmod 600 .env

docker compose up -d --remove-orphans
set -a; . ./.env; set +a
for port in 8080 8081; do
  for _ in $(seq 1 90); do
    curl -fsS "http://$WG_ADDRESS:$port/health" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS -H "Authorization: Bearer $LLAMA_API_KEY" "http://$WG_ADDRESS:$port/v1/models" \
    | python3 -c "import json,sys; print('port $port serves', [m['id'] for m in json.load(sys.stdin)['data']])"
done
# Unused model files (an older lock) can be removed by hand from models/.
