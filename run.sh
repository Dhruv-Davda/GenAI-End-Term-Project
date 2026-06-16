#!/usr/bin/env bash
# One-command setup + launch.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

echo "Installing dependencies..."
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

if [ ! -f sample_data/superstore_sales.csv ]; then
  echo "Generating sample dataset..."
  ./.venv/bin/python generate_sample.py
fi

if [ ! -f .env ] && [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "⚠️  No .env found and ANTHROPIC_API_KEY is unset."
  echo "    Copy .env.example to .env and add your key (uploads/profiling still work without it)."
fi

# Pick the first free port (8000 is often taken by another dev server).
PORT="${PORT:-8000}"
while lsof -i:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; do
  echo "Port $PORT is in use, trying $((PORT + 1))..."
  PORT=$((PORT + 1))
done

echo "Starting on http://127.0.0.1:$PORT"
exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
