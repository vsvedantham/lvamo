#!/bin/bash
# Copy the routine's documents from R2 to a local folder on this Mac.
# Started by the unlock listener (LaunchAgent com.jobsearch.sync) at login and on every unlock.
# Retries every 30 seconds until one sync succeeds (e.g. while offline), then exits.
# Only adds or updates files; never deletes anything locally.
#
# Credentials come from ~/.job-search-automation.env (never stored elsewhere).
# Usage: sync_to_mac.sh [destination]   (default ~/JobSearchDocuments)
set -u
export PATH="${SYNC_EXTRA_PATH:+$SYNC_EXTRA_PATH:}/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"  # SYNC_EXTRA_PATH: test hook

DEST="${1:-$HOME/JobSearchDocuments}"
ENV_FILE="$HOME/.job-search-automation.env"
LOCK="${TMPDIR:-/tmp}/job-search-sync.lock"
RETRY_SECONDS="${SYNC_RETRY_SECONDS:-30}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# One sync at a time: an unlock while a sync (or its retry loop) is running does nothing.
if ! mkdir "$LOCK" 2>/dev/null; then
  pid=$(cat "$LOCK/pid" 2>/dev/null)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then exit 0; fi
  rm -rf "$LOCK"; mkdir "$LOCK" 2>/dev/null || exit 0
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

[ -f "$ENV_FILE" ] || { log "missing $ENV_FILE"; exit 1; }
# Read line by line: the Neon URL contains '&', which breaks `source`.
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|'#'*) ;; *=*) export "$line" ;; esac
done < "$ENV_FILE"

for v in R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET; do
  [ -n "${!v:-}" ] || { log "missing $v in $ENV_FILE"; exit 1; }
done
ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# rclone remote "r2", configured only through environment variables.
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="$ENDPOINT"
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true

mkdir -p "$DEST"
count_jobs() { find "$DEST" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' '; }

# One sync attempt. Returns 0 on success. If the Mac sleeps during a pass, the pass ends
# after wake with a stale listing of R2; a normal pass takes seconds, so a pass longer
# than 90 s is repeated with a fresh listing (up to 3 passes).
copied=0
sync_once() {
  local pass t0 took out
  for pass in 1 2 3; do
    t0=$(date +%s)
    if ! out=$(rclone copy "r2:${R2_BUCKET}/${R2_PREFIX:-jobautomationdocs}" "$DEST" \
          --exclude "_selftest/**" --exclude "_e2e_test/**" \
          --transfers 8 --retries 3 --low-level-retries 5 --stats-one-line -v 2>&1); then
      log "rclone failed: $(printf '%s' "$out" | tail -2 | tr '\n' ' ')"
      return 1
    fi
    copied=$((copied + $(printf '%s\n' "$out" | grep -c ': Copied' || true)))
    took=$(( $(date +%s) - t0 ))
    [ "$took" -le 90 ] && return 0
    log "pass $pass took ${took}s (Mac probably slept); syncing again with a fresh listing"
  done
  return 0
}

before=$(count_jobs)
attempt=0
offline_logged=0
while :; do
  attempt=$((attempt + 1))
  if ! curl -s -o /dev/null -m 10 "$ENDPOINT"; then
    [ "$offline_logged" = 0 ] && log "no connection to R2; retrying every ${RETRY_SECONDS}s until a sync succeeds"
    offline_logged=1
    sleep "$RETRY_SECONDS"; continue
  fi
  sync_once && break
  log "sync attempt $attempt failed; retrying in ${RETRY_SECONDS}s"
  sleep "$RETRY_SECONDS"
done

after=$(count_jobs)
new=$((after - before))
log "sync ok (attempt $attempt): $copied files copied, $new new job folders, $after jobs total -> $DEST"

if [ "$new" -gt 0 ]; then
  s=$([ "$new" = 1 ] && echo "" || echo "s")
  osascript -e "display notification \"$new new job$s with CV and cover letter\" with title \"Job search\" subtitle \"Synced to JobSearchDocuments\"" >/dev/null 2>&1 || true
fi
