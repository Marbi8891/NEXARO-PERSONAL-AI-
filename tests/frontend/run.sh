#!/usr/bin/env bash
# Ejecuta el frontend (módulos ES reales, jsdom) contra una API real con BD temporal y modelo falso.
# Uso: tests/frontend/run.sh   (requiere Node >= 20 y el entorno Python del proyecto activo)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
export REPO="$(cd "$here/../.." && pwd)"
export PYTHONPATH="$REPO:$REPO/packages:$REPO/apps/api"
cd "$here"
[ -d node_modules ] || npm install --no-audit --no-fund --silent
python "$here/server.py" &
server=$!
trap 'kill "$server" 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  curl -fs http://127.0.0.1:8765/api/health/live >/dev/null && break
  sleep 0.2
done
# Navegador real (descarga ~70 MB la primera vez): BROWSER=1 tests/frontend/run.sh
# Va primero: las capturas de docs/design deben salir del estado inicial, antes de que el E2E lo modifique.
if [ "${BROWSER:-0}" = "1" ]; then node browser.mjs; fi
node e2e.mjs
