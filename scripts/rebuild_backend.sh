#!/usr/bin/env bash
# Reconstruye SOLO el servicio backend de NEXARO conservando el volumen SQLite,
# la red externa de Ollama, las variables de entorno y el puerto 127.0.0.1:8001.
# Nunca ejecuta `down`, `-v` ni borra volúmenes.
#
# Uso:  scripts/rebuild_backend.sh [--yes]
set -Eeuo pipefail

cd "$(dirname "$0")/.."

BACKUP="backups/nexaro-pre-auth-migration-20261108.db"
BACKUP_SHA="53ab1134fa8bc64ecdd18d9cea199e7ac8d92ece90d4fd55c6b7b468d0c9ce01"
CONTAINER="nexaro-backend"
SERVICE="backend"
VOLUME="nexaro-personal-ai_nexaro_data"
NETWORK="ollama-local_default"
URL="http://127.0.0.1:8001"
PY="${PYTHON:-.venv-nexaro-tests/bin/python}"  # debe tener requirements/dev.txt instalado
STAMP="$(date +%Y%m%d-%H%M%S)"
ASSUME_YES=0
[[ "${1:-}" == "--yes" ]] && ASSUME_YES=1

step() { printf '\n==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Cuenta tablas y comprueba integridad de un .db local (solo lectura).
db_report() {
  python3 - "$1" <<'PY'
import sqlite3, sys, json
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print(json.dumps({
  "integrity": c.execute("PRAGMA integrity_check").fetchone()[0],
  **{t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
     for t in ("users", "sessions", "conversations", "messages")},
}, sort_keys=True))
PY
}

step "1/8 Copia de seguridad previa (existencia, hash e integridad)"
[[ -f "$BACKUP" ]] || fail "no existe $BACKUP"
[[ "$(shasum -a 256 "$BACKUP" | cut -d' ' -f1)" == "$BACKUP_SHA" ]] \
  || fail "el hash de $BACKUP no coincide: la copia ha cambiado"
db_report "$BACKUP" | grep -q '"integrity": "ok"' || fail "integridad de la copia"
db_report "$BACKUP"

step "2/8 Pruebas unitarias y de integración"
"$PY" -c "import pytest, fastapi, httpx, pydantic_settings" 2>/dev/null \
  || fail "faltan dependencias en $PY: $PY -m pip install -r requirements/dev.txt"
"$PY" -B -m pytest -q -p no:cacheprovider tests

step "3/8 Configuración, volumen y red"
docker compose config --quiet
docker volume inspect "$VOLUME" >/dev/null || fail "no existe el volumen $VOLUME"
docker network inspect "$NETWORK" >/dev/null || fail "no existe la red $NETWORK"
docker container inspect "$CONTAINER" >/dev/null || fail "no existe $CONTAINER"

step "4/8 Copia fresca de la base VIVA (API de backup de SQLite)"
LIVE_NAME="nexaro.pre-rebuild-$STAMP.db"
docker exec "$CONTAINER" python -c "
import sqlite3
s = sqlite3.connect('/data/nexaro.db')
d = sqlite3.connect('/data/$LIVE_NAME')
s.backup(d); d.close(); s.close()"
docker cp "$CONTAINER:/data/$LIVE_NAME" "backups/$LIVE_NAME"
db_report "backups/$LIVE_NAME" | tee "/tmp/nexaro-before-$STAMP.json"
grep -q '"integrity": "ok"' "/tmp/nexaro-before-$STAMP.json" || fail "copia viva corrupta"

step "5/8 Conservar la imagen actual para poder volver atrás"
OLD_IMAGE="$(docker inspect --format '{{.Image}}' "$CONTAINER")"
docker tag "$OLD_IMAGE" "nexaro-personal-ai-backend:rollback-$STAMP"
echo "imagen anterior: $OLD_IMAGE  (tag rollback-$STAMP)"

if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "Reconstruir y recrear SOLO '$SERVICE'? [escribe si] " answer
  [[ "$answer" == "si" ]] || fail "cancelado; no se ha cambiado nada"
fi

step "6/8 Build y recreación de $SERVICE (sin tocar otros servicios ni volúmenes)"
docker compose build "$SERVICE"
docker compose up -d --no-deps "$SERVICE"

step "7/8 Espera de arranque"
code=000
for _ in $(seq 1 40); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/auth/me" || true)"
  [[ "$code" == "401" ]] && break
  sleep 1
done
docker logs --tail 25 "$CONTAINER"
if [[ "$code" != "401" ]]; then
  echo "Rollback: docker tag nexaro-personal-ai-backend:rollback-$STAMP nexaro-personal-ai-backend:latest && docker compose up -d --no-deps $SERVICE" >&2
  fail "el backend no responde como se esperaba (HTTP $code)"
fi

step "8/8 Verificación posterior en la base viva"
docker exec "$CONTAINER" python -c "
import sqlite3, json
c = sqlite3.connect('file:/data/nexaro.db?mode=ro', uri=True)
print(json.dumps({
  'columnas_users': [r[1] for r in c.execute('PRAGMA table_info(users)')][4:],
  'integrity': c.execute('PRAGMA integrity_check').fetchone()[0],
  'fk_errores': len(c.execute('PRAGMA foreign_key_check').fetchall()),
  'registro_publico': c.execute(\"SELECT value FROM app_settings WHERE key='public_registration_enabled'\").fetchone()[0],
  'admins': c.execute(\"SELECT COUNT(*) FROM users WHERE role='admin'\").fetchone()[0],
  **{t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
     for t in ('users','sessions','conversations','messages')},
}, sort_keys=True))"
echo "antes: $(cat /tmp/nexaro-before-$STAMP.json)"
echo "register sin permiso -> HTTP $(curl -s -o /dev/null -w '%{http_code}' -H 'Origin: http://127.0.0.1:8001' -H 'Content-Type: application/json' -d '{"email":"x@example.com","password":"correct-horse-battery"}' "$URL/api/auth/register") (esperado 403)"
echo "admin sin sesión     -> HTTP $(curl -s -o /dev/null -w '%{http_code}' "$URL/api/admin/users") (esperado 401)"
echo "Ollama (/api/health) -> HTTP $(curl -s -o /dev/null -w '%{http_code}' "$URL/api/health") (200 = conectado, 503 = sin Ollama)"

cat <<MSG

Hecho. Siguiente paso (manual, interactivo; pide la contraseña solo si la cuenta no existe):
  docker exec -it $CONTAINER python -m nexaro_api.bootstrap_admin \\
      --confirm-database /data/nexaro.db --email TU_CORREO --promote-existing
MSG
