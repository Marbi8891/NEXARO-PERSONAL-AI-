#!/usr/bin/env bash
# Ejecuta el frontend (módulos ES reales, jsdom) contra una API real con BD temporal y modelo falso.
# Uso: tests/frontend/run.sh   (requiere Node >= 20 y el entorno Python del proyecto activo)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
export REPO="$(cd "$here/../.." && pwd)"
export PYTHONPATH="$REPO:$REPO/packages:$REPO/apps/api"
export NEXARO_E2E_PORT="${NEXARO_E2E_PORT:-8765}"
cd "$here"
[ -d node_modules ] || npm install --no-audit --no-fund --silent
python "$here/server.py" &
server=$!
trap 'kill "$server" 2>/dev/null || true' EXIT
up=0
for _ in $(seq 1 50); do
  curl -fs "http://127.0.0.1:$NEXARO_E2E_PORT/api/health/live" >/dev/null && { up=1; break; }
  sleep 0.2
done
# Sin servidor las pruebas no deben "pasar" contra nada: NEXARO_E2E_PORT=8899 si el puerto está reservado.
[ "$up" = 1 ] || { echo "el servidor de pruebas no arrancó en el puerto $NEXARO_E2E_PORT" >&2; exit 1; }
# Navegador real (descarga ~70 MB la primera vez): BROWSER=1 tests/frontend/run.sh
# Va primero: las capturas de docs/design deben salir del estado inicial, antes de que el E2E lo modifique.
if [ "${BROWSER:-0}" = "1" ]; then node browser.mjs; fi
node e2e.mjs
