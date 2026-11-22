#!/bin/sh
# Container start. Seeds the demo account when DEMO_PASSWORD is set (the free host's disk is wiped on every
# restart, so accounts made on the site do not survive), then runs the API on $PORT.
mkdir -p artifacts
if [ -n "$DEMO_PASSWORD" ]; then
  python scripts/seed_demo_account.py || echo "demo account seed failed; continuing"
fi
exec python -m uvicorn api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
