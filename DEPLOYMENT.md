# Despliegue

## Despliegue permanente en el ThinkPad (Windows + Docker Desktop) — v1.0

Estado el 2026-11-23, 15:43: NEXARO **en marcha en `http://127.0.0.1:8002`** (`NEXARO_PORT=8002`,
porque `127.0.0.1:8001` lo ocupa `nexaro-prompt-library`, de `C:\Users\pc\Documents\NEXARO-PERSONAL-AI-`).
Esquema v7, datos migrados desde v6 sin pérdidas, copia previa verificada en
`C:\Users\pc\NEXARO-Backups`. **Provisional:** se desplegó desde el worktree de la rama
`claude/nexaro-v1-consolidation-921fe0`; al integrarla en `main`, repite el paso 5 desde el clon
definitivo con este mismo `.env`:

```
NEXARO_PORT=8002
ALLOWED_ORIGINS=http://127.0.0.1:8002,http://localhost:8002
```

1. **Un solo clon, limpio, en `main`.** Hoy hay cuatro copias del proyecto y la de
   `C:\Users\pc\NEXARO-PERSONAL-AI-` tiene cambios sin confirmar. Despliega desde un clon sin
   cambios locales (`git status` vacío) para que lo que corre sea lo probado.
2. **Puerto.** O bien paras la Prompt Library standalone (la PR #11 la integra en NEXARO):

   ```powershell
   docker stop nexaro-prompt-library
   ```

   o bien, en `.env`, usas otro puerto local (siempre en 127.0.0.1):

   ```
   NEXARO_PORT=8002
   ALLOWED_ORIGINS=http://127.0.0.1:8002,http://localhost:8002
   ```

3. **Copia de seguridad** de los datos actuales (esquema v6) antes de actualizar:

   ```powershell
   pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\backup_nexaro.ps1 -Reason pre-update
   ```

4. **Prueba previa de la imagen** contra el Ollama real con datos temporales (no toca los reales):

   ```powershell
   docker build -t nexaro-personal-ai-backend:v1-candidate C:\Users\pc\NEXARO-PERSONAL-AI-
   ```

   ```powershell
   pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\smoke_isolated.ps1 -Image nexaro-personal-ai-backend:v1-candidate
   ```

5. **Arranque** (construye la imagen, aplica la migración 7 al arrancar y espera a que esté sano):

   ```powershell
   docker compose -f C:\Users\pc\NEXARO-PERSONAL-AI-\compose.yaml up -d --build --wait
   ```

6. **Comprobaciones:** `http://127.0.0.1:8001/api/health` → `{"status":"ok",...}`; inicia sesión;
   Administración → Operaciones (todo en verde salvo «Copia de seguridad» hasta el primer
   `backup_nexaro.ps1` con el backend en marcha).
7. **Copia diaria** (cambia el Programador de tareas; la decides tú): BACKUP_RESTORE.md.
8. **Arranque tras reiniciar Windows:** Docker Desktop → *Settings → General → Start Docker Desktop
   when you sign in*. Los contenedores tienen `restart: unless-stopped` y vuelven solos; el Ollama
   externo (`C:\Docker\ollama-local`) también. Docker Desktop no arranca hasta que inicias sesión.
9. **Acceso desde el móvil:** REMOTE_ACCESS.md (Tailscale Serve; preparado, sin activar).

Recomendado para el despliegue permanente: quitar el bind mount `./frontend:/app/frontend:ro` de
`compose.yaml` (la imagen ya incluye la interfaz) para que cambiar de rama en el clon no cambie la
interfaz en caliente.

Recursos: backend 1 GiB / 2 CPU / 200 procesos; logs 10 MiB × 5. El Ollama externo tiene 12 GiB;
`qwen2.5:3b` ocupa ~2 GiB cargado.

## Instalación desde cero (Docker, local)

Requisitos: Docker con **Compose >= 2.20** (Docker Desktop en macOS o Docker Engine en Linux, incluido
Linux en VirtualBox), `make` y `curl`. Unos 4 GB de RAM libres para Docker con `qwen2.5:3b`.

Hay dos modos de Ollama ([ADR-0021](docs/decisions/0021-compose-ollama-profile-and-smoke.md)). En los
dos, el backend lo encuentra como `http://ollama:11434` y Ollama **no publica puertos** desde este proyecto.

| | Externo (por defecto, MacBook) | Incluido (máquina nueva) |
|---|---|---|
| Ollama | contenedor `ollama` de `~/Docker/ollama-local` | servicio `ollama` de este `compose.yaml` (perfil) |
| Red | `ollama-local_default` (la crea `ollama-local`) | `nexaro_ollama` (la crea `make up`) |
| Modelos | volumen `ollama-local_ollama_data` | volumen `nexaro-personal-ai_ollama_models` |
| `.env` | nada | `COMPOSE_PROFILES=ollama` y `OLLAMA_NETWORK=nexaro_ollama` |

No uses los dos a la vez sobre la misma red: `make up` lo impide.

1. Clona el repositorio y entra en él.
2. Modo externo: `cd ~/Docker/ollama-local && docker compose up -d`. Modo incluido: añade las dos líneas
   de la tabla a `.env` (es el archivo que lee Compose; está en `.gitignore`).
3. `make up`. Comprueba Docker, Compose, la red y el modo, construye y espera a que los servicios estén
   sanos. La aplicación queda en `http://127.0.0.1:8001` (solo local).
4. `make model`. Descarga `qwen2.5:3b` (~2 GB) **solo si falta**; repetirlo no descarga nada.
   `make model-check` solo comprueba. Para otro modelo: `OLLAMA_MODEL=...` en `.env` y `make up`.
5. `make smoke`: servicios, salud, modelo, una respuesta real y persistencia tras recrear los
   contenedores. Debe terminar en `SMOKE OK`.
6. Crea el primer administrador (abajo). **No hay administradores ni registro público por defecto.**
7. Abre la aplicación e inicia sesión. Si quieres que otras personas pidan acceso, abre el registro en
   Administración: cada cuenta nueva queda pendiente hasta que la apruebes.
8. Para crear claves de API: Administración → crea una organización (la creas tú como propietario) →
   Developer.

`/api/health/live` solo dice que el proceso vive (lo usa el healthcheck). `/api/health` devuelve 503 con
«Servicio de IA no disponible» si Ollama no responde, o «Modelo de IA no disponible» si falta el modelo;
con todo bien, `{"status":"ok","ollama":"connected","model":"ready"}`.

Variables de la aplicación: [`.env.example`](.env.example). `compose.yaml` fija las del servicio; desde
`.env` se pueden cambiar `OLLAMA_MODEL`, `OLLAMA_NETWORK`, `OLLAMA_IMAGE` (fíjala a una versión tras la
primera descarga: `docker image inspect ollama/ollama:latest --format '{{index .RepoDigests 0}}'`) y
`OLLAMA_MEM_LIMIT` (6g).

### Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `no existe la red ollama-local_default` | Arranca `~/Docker/ollama-local` o pasa al modo incluido |
| `habría dos 'ollama'` | Modo incluido sobre la red del externo: pon `OLLAMA_NETWORK=nexaro_ollama` |
| `hace falta Docker Compose >= 2.20` | Actualiza Docker Desktop o el plugin `docker-compose-plugin` |
| `/api/health` → «Modelo de IA no disponible» | `make model` |
| `make model` se corta «sin progreso» | Red lenta o caída: repítelo, Ollama reanuda la descarga |
| La primera respuesta tarda mucho | Carga del modelo en CPU; `OLLAMA_KEEP_ALIVE=30m` lo mantiene cargado |

### Sin Docker (desarrollo)

`make install && make run` (API en `127.0.0.1:8001`, Ollama en `OLLAMA_BASE_URL`). Ver [DEVELOPMENT.md](DEVELOPMENT.md).

### Copias de seguridad y actualización

- La base es un único archivo SQLite en el volumen `nexaro-personal-ai_nexaro_data`. En Windows:
  `scripts/backup_nexaro.ps1` (copia verificada, ver [BACKUP_RESTORE.md](BACKUP_RESTORE.md)); en macOS,
  `scripts/rebuild_backend.sh` la hace antes de actualizar. La imagen no incluye el binario `sqlite3`.
  Guarda las copias fuera del repositorio: contienen datos de usuarios.
- Actualizar = reconstruir **solo** `backend` conservando el volumen. Las migraciones pendientes (hoy hasta la 10)
  se aplican al arrancar en una transacción; si fallan, el arranque aborta sin dejar estado parcial.
- Antes de aplicar migraciones pendientes sobre una base con datos, el arranque deja una copia
  verificada (`integrity_check`) junto a ella: `/data/nexaro.pre-migration-v<N>-<fecha UTC>.db`.
  Si la copia falla, no se migra. Estas copias no se borran solas: revísalas y muévelas fuera del
  volumen cuando ya no hagan falta.
- Revertir código: la imagen anterior queda etiquetada `rollback-<fecha>`. Las migraciones no tienen
  «bajada»: para volver atrás de verdad se restaura la copia previa.
- Nunca `docker compose down -v` ni borrar el volumen.

## Local (Docker)

```bash
make up && make model && make smoke
```

Volúmenes persistentes: `nexaro-personal-ai_nexaro_data` (SQLite en `/data/nexaro.db`) y, en el modo
incluido, `nexaro-personal-ai_ollama_models`. Puerto `127.0.0.1:8001`. `make down` para los contenedores
sin tocar los volúmenes; **nunca** `docker compose down -v`.

### Reconstruir conservando datos

`scripts/rebuild_backend.sh [--yes]` verifica la copia de seguridad, ejecuta los tests, hace
una copia fresca de la base viva, etiqueta la imagen anterior como `rollback-<fecha>`,
reconstruye solo `backend` y comprueba el resultado. Necesita un entorno Python con
`requirements/dev.txt` (variable `PYTHON`).

### Rendimiento de Ollama

Variables del backend (`compose.yaml` / `.env.example`): `OLLAMA_KEEP_ALIVE` (30m: el modelo sigue cargado
entre mensajes y no se paga la carga de nuevo), `OLLAMA_NUM_CTX` (4096, **constante**: si cambia entre
peticiones, Ollama recarga el modelo), `OLLAMA_NUM_THREAD` (vacío = decide Ollama),
`OUTPUT_TOKENS_SHORT/DEFAULT/CODE` y `CHAT_HISTORY_MAX_CHARS`. Mantener el modelo cargado ocupa RAM
(~2 GB para `qwen2.5:3b`); Docker Desktop reparte la suya entre todos los contenedores. Para medir antes y
después, sin instalar nada:

```bash
docker run --rm --network ollama-local_default -v "$PWD/scripts:/s:ro" python:3.12-slim \
    python /s/ollama_benchmark.py --base-url http://ollama:11434 --model qwen2.5:3b --profile actual --runs 3
```

Repite con `--profile optimizado` (y `--num-ctx 8192` para comparar). Con el equipo en reposo: otros
contenedores consumiendo CPU distorsionan los tiempos.

### Seguridad y retención

El detalle está en `docs/security/` (`SECURITY_BASELINE.md` tiene la lista de comprobación del despliegue).
Las copias de `backups/` se podan a mano: `scripts/prune_backups.sh --keep 10` simula y `--apply` borra;
nunca toca `nexaro-pre-auth-migration-*`. Los logs rotan en Docker (`10m × 5`).

### Primer administrador

```bash
docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin \
    --confirm-database /data/nexaro.db --email TU_CORREO [--promote-existing]
```

### Nube (opcional, desactivada)

`docker build --build-arg INSTALL_AWS=1 .` instala boto3. Variables en `.env.example`. Las
credenciales vienen del rol/entorno de AWS, no del repositorio. Mientras `AI_ALLOW_CLOUD` no sea
`true`, ningún dato sale a la nube.

## AWS (Terraform, sin aplicar)

Código en `infrastructure/aws/terraform` (módulos + `envs/{dev,staging,prod}`). **No se ha creado
ningún recurso.** Decisiones y límites: [ADR-0006](docs/decisions/0006-aws-infrastructure.md);
costes: [docs/deployment/aws-costs.md](docs/deployment/aws-costs.md).

Para aplicarlo (con tu autorización expresa, desde tu máquina):

1. Crea una vez el bucket de estado (cifrado, con versionado) y copia `backend.hcl.example` a
   `backend.hcl` en el entorno.
2. Copia `terraform.tfvars.example` a `terraform.tfvars` (ignorado por git).
3. `terraform init -backend-config=backend.hcl && terraform validate && terraform plan`.
   Revisa el plan antes de `apply`. **VERIFY**: el código no se ha validado contra el proveedor.
4. Sube la imagen a ECR con una etiqueta inmutable y fija `image_tag`.

La aplicación **no debe desplegarse** (`desired_count` > 0) hasta que ejecute sobre PostgreSQL
(ADR-0005): con SQLite el disco de Fargate se pierde en cada reinicio. Con `NEXARO_ENV=production`
la aplicación exige `COOKIE_SECURE=true` y orígenes https.
