#!/usr/bin/env bash
# Avvio rapido Snap+ (backend + frontend) su Linux/Mac.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Backend: creo venv e installo dipendenze"
cd "$ROOT/backend"
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> Avvio backend su http://localhost:8000"
python3 -m uvicorn server:app --reload --port 8000 &
BACK_PID=$!

echo "==> Frontend: installo dipendenze (puo' richiedere qualche minuto)"
cd "$ROOT/frontend"
npm install --legacy-peer-deps

echo "==> Avvio frontend su http://localhost:3000"
npm start

kill $BACK_PID 2>/dev/null || true
