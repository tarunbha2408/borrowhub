#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# BorrowHub - local development server
#   bash run_local.sh              -> http://127.0.0.1:8010
#   PORT=8020 bash run_local.sh    -> http://127.0.0.1:8020
# The first run creates .venv and installs the dependencies automatically.
# ---------------------------------------------------------------------------
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8010}"

if [ ! -x ".venv/bin/python" ]; then
  echo "==> Creating .venv (first run, 1-2 minutes)"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  echo "==> Installing dependencies"
  ./.venv/bin/pip install -r backend/requirements.txt
fi

if [ ! -f "backend/.env" ]; then
  cp backend/.env.example backend/.env
  echo "==> Created backend/.env from backend/.env.example"
fi

source .venv/bin/activate
echo "==> Server: http://127.0.0.1:$PORT   (Ctrl+C to stop)"
exec python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" --reload
