#!/usr/bin/env bash
# Comprobaciones del stack Docker de NEXARO (ADR-0021). Compatible con bash 3.2 (macOS).
#
#   scripts/stack.sh preflight   antes de `docker compose up`: Docker, Compose, modo de Ollama y red
#   scripts/stack.sh smoke       con el stack arrancado: servicios, salud, modelo, respuesta real y
#                                persistencia tras reiniciar
#
# Nunca ejecuta `down`, `-v` ni borra volúmenes. No modifica la base de datos: la lee en solo
# lectura y, para probar la persistencia, escribe y luego borra un archivo propio (/data/.nexaro-smoke).
#
# Variables: OLLAMA_CONTAINER (externo, por defecto `ollama`), SMOKE_RESTART_OLLAMA=1 (reinicia
# también el Ollama externo; el incluido se reinicia siempre), SMOKE_TIMEOUT (s, por defecto 180).
set -Eeuo pipefail

cd "$(dirname "$0")/.."

BACKEND="nexaro-backend"
BUNDLED_OLLAMA="nexaro-ollama"
EXTERNAL_NET="ollama-local_default"
URL="http://127.0.0.1:8001"
MARKER="/data/.nexaro-smoke"
TIMEOUT="${SMOKE_TIMEOUT:-180}"
FAILURES=0

step() { printf '\n==> %s\n' "$*"; }
ok() { printf '  OK   %s\n' "$*"; }
bad() { printf '  FALLO %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- Detección ---------------------------------------------------------------------------------

compose_version_ok() {
  # Compose >= 2.20 por `depends_on.required`. Acepta "v2.29.1", "2.29.1-desktop.1", "v5.7.1".
  local version major minor
  version="$(docker compose version --short 2>/dev/null)" || return 1
  version="${version#v}"
  major="${version%%.*}"
  minor="${version#*.}"
  minor="${minor%%.*}"
  case "$major$minor" in *[!0-9]*|"") return 1 ;; esac
  [ "$major" -gt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -ge 20 ]; }
}

# Sin tuberías hacia `grep -q`/`exit`: con pipefail, el SIGPIPE de compose daría un falso negativo.
bundled_mode() {
  local services
  services="$(docker compose config --services 2>/dev/null)" || return 1
  case "
$services
" in *"
ollama
"*) return 0 ;; esac
  return 1
}

# Nombre real de la red tras la interpolación de compose (.env incluido).
network_name() {
  local config
  config="$(docker compose config 2>/dev/null)" || return 1
  printf '%s\n' "$config" \
    | awk '/^networks:/{f=1; next} f && /^[^ ]/{f=0} f && $1=="name:" && !n {gsub(/"/, "", $2); print $2; n=1}'
}

ollama_container() {
  if bundled_mode; then echo "$BUNDLED_OLLAMA"; else echo "${OLLAMA_CONTAINER:-ollama}"; fi
}

running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = "true" ]; }
health_of() { docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}sin-healthcheck{{end}}' "$1" 2>/dev/null || echo "inexistente"; }

wait_healthy() {
  local name="$1" waited=0 status
  while [ "$waited" -lt "$TIMEOUT" ]; do
    status="$(health_of "$name")"
    case "$status" in
      healthy|sin-healthcheck) running "$name" && return 0 ;;
      unhealthy) return 1 ;;
    esac
    sleep 3
    waited=$((waited + 3))
  done
  return 1
}

# Lanza scripts/ollama_model.py dentro del backend: misma red y misma OLLAMA_BASE_URL que la app.
model_cmd() { docker exec -i "$BACKEND" python - "$@" < scripts/ollama_model.py; }
configured_model() { docker exec "$BACKEND" printenv OLLAMA_MODEL; }

# /api/health con reintentos (HEALTH_CACHE_SECONDS y el cortacircuitos tardan unos segundos).
api_health() {
  local waited=0 body
  while [ "$waited" -lt "$TIMEOUT" ]; do
    if body="$(curl -fsS --max-time 15 "$URL/api/health" 2>/dev/null)"; then
      printf '%s' "$body"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
  done
  curl -sS --max-time 15 "$URL/api/health" 2>&1 || true
  return 1
}

# Recuento de filas en solo lectura: ni el arranque ni el smoke añaden filas a estas tablas.
db_fingerprint() {
  docker exec "$BACKEND" python -c '
import sqlite3
db = sqlite3.connect("file:/data/nexaro.db?mode=ro", uri=True)
tables = ("users", "conversations", "messages", "documents")
print(" ".join(t + "=" + str(db.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]) for t in tables))'
}

# --- preflight ---------------------------------------------------------------------------------

preflight() {
  step "Docker y Compose"
  docker info >/dev/null 2>&1 || fail "Docker no responde (¿Docker Desktop arrancado?)"
  compose_version_ok || fail "hace falta Docker Compose >= 2.20 (tienes: $(docker compose version --short 2>/dev/null || echo ninguno))"
  docker compose config --quiet || fail "compose.yaml o .env no son válidos"
  ok "Docker $(docker version --format '{{.Server.Version}}'), Compose $(docker compose version --short)"

  local net
  net="$(network_name)"
  [ -n "$net" ] || fail "no se pudo leer el nombre de la red de compose.yaml"

  if bundled_mode; then
    step "Modo Ollama incluido (perfil ollama), red $net"
    if [ "$net" = "$EXTERNAL_NET" ] && running ollama; then
      fail "el Ollama de ~/Docker/ollama-local está en la red $net: habría dos 'ollama'. Usa OLLAMA_NETWORK=nexaro_ollama o el modo externo"
    fi
    if docker network inspect "$net" >/dev/null 2>&1; then
      ok "la red $net ya existe"
    else
      docker network create "$net" >/dev/null
      ok "red $net creada"
    fi
  else
    step "Modo Ollama externo, red $net"
    docker network inspect "$net" >/dev/null 2>&1 \
      || fail "no existe la red $net: arranca antes ~/Docker/ollama-local (docker compose up -d) o usa el modo incluido (DEPLOYMENT.md)"
    running "$(ollama_container)" \
      && ok "contenedor $(ollama_container) en marcha" \
      || printf '  AVISO el contenedor %s no está en marcha: el backend arrancará, pero /api/health dará 503\n' "$(ollama_container)"
  fi
}

# --- smoke -------------------------------------------------------------------------------------

smoke() {
  local ollama model before after token got
  command -v curl >/dev/null || fail "falta curl"
  ollama="$(ollama_container)"
  bundled_mode && echo "Modo: Ollama incluido ($ollama)" || echo "Modo: Ollama externo ($ollama)"

  step "1/6 Servicios activos"
  running "$BACKEND" && ok "$BACKEND en marcha" || fail "$BACKEND no está en marcha: make up"
  running "$ollama" && ok "$ollama en marcha" || bad "$ollama no está en marcha"

  step "2/6 Healthchecks"
  wait_healthy "$BACKEND" && ok "$BACKEND: $(health_of "$BACKEND")" || bad "$BACKEND: $(health_of "$BACKEND")"
  wait_healthy "$ollama" && ok "$ollama: $(health_of "$ollama")" || bad "$ollama: $(health_of "$ollama")"
  curl -fsS --max-time 5 "$URL/api/health/live" >/dev/null && ok "GET /api/health/live" || bad "GET /api/health/live"

  step "3/6 Ollama accesible desde el backend y modelo instalado"
  model="$(configured_model)"
  if model_cmd check "$model"; then
    ok "modelo $model disponible"
  else
    bad "Ollama o el modelo $model no están disponibles (make model)"
  fi
  local body
  if body="$(api_health)" && case "$body" in *'"model":"ready"'*) true ;; *) false ;; esac; then
    ok "GET /api/health: $body"
  else
    bad "GET /api/health: $body"
  fi

  step "4/6 Generación real de una respuesta"
  model_cmd generate "$model" && ok "el modelo responde" || bad "el modelo no generó respuesta"

  step "5/6 Reinicio: contenedores nuevos sobre los mismos volúmenes"
  token="$(docker exec "$BACKEND" python -c "import pathlib, secrets; t = secrets.token_hex(8); pathlib.Path('$MARKER').write_text(t); print(t)")"
  before="$(db_fingerprint)"
  echo "  antes:   $before"
  # --force-recreate sin -v: contenedores nuevos, volúmenes intactos (prueba más fuerte que restart).
  if bundled_mode; then
    docker compose up -d --force-recreate --no-deps --no-build ollama >/dev/null 2>&1
  elif [ "${SMOKE_RESTART_OLLAMA:-0}" = "1" ]; then
    docker restart "$ollama" >/dev/null
  else
    echo "  (Ollama externo no se reinicia; SMOKE_RESTART_OLLAMA=1 para incluirlo)"
  fi
  docker compose up -d --force-recreate --no-deps --no-build backend >/dev/null 2>&1
  wait_healthy "$ollama" && ok "$ollama sano tras reiniciar" || bad "$ollama no vuelve a estar sano"
  wait_healthy "$BACKEND" && ok "$BACKEND sano tras reiniciar" || bad "$BACKEND no vuelve a estar sano"

  step "6/6 Persistencia tras el reinicio"
  got="$(docker exec "$BACKEND" python -c "import pathlib; print(pathlib.Path('$MARKER').read_text())" 2>/dev/null || true)"
  [ "$got" = "$token" ] && ok "el volumen de datos conserva el archivo de prueba" || bad "el archivo de prueba no sobrevivió al reinicio"
  docker exec "$BACKEND" python -c "import pathlib; pathlib.Path('$MARKER').unlink(missing_ok=True)" || true
  after="$(db_fingerprint)"
  echo "  después: $after"
  [ "$before" = "$after" ] && ok "la base de datos conserva sus filas" || bad "la base de datos cambió tras el reinicio"
  model_cmd check "$model" >/dev/null && ok "el modelo sigue instalado" || bad "el modelo ya no está instalado"
  api_health >/dev/null && ok "GET /api/health tras el reinicio" || bad "GET /api/health tras el reinicio"

  echo
  if [ "$FAILURES" -eq 0 ]; then
    echo "SMOKE OK"
  else
    echo "SMOKE FALLIDO: $FAILURES comprobaciones"
    exit 1
  fi
}

case "${1:-}" in
  preflight) preflight ;;
  smoke) smoke ;;
  *) echo "uso: $0 preflight|smoke" >&2; exit 2 ;;
esac
