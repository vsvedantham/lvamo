#!/usr/bin/env bash
# Idempotent environment setup; safe to run at the start of every routine run.
set -u
if ! python3 -c "import weasyprint" >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    if sudo -n true 2>/dev/null; then SUDO=sudo; else SUDO=""; fi
    $SUDO apt-get update -qq >/dev/null 2>&1 || true
    $SUDO apt-get install -y -qq libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core >/dev/null 2>&1 || true
  fi
fi
python3 -m pip install -q -r "$(dirname "$0")/../requirements.txt" 2>/dev/null \
  || python3 -m pip install -q --break-system-packages -r "$(dirname "$0")/../requirements.txt"
python3 -c "import weasyprint, sqlalchemy, boto3, yaml, jinja2; print('setup ok')"
