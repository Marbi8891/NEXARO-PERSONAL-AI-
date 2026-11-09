# Despliegue

## Instalación desde cero (Docker, local)

Requisitos: Docker con Compose v2 y un contenedor de Ollama accesible en la red externa
`ollama-local_default` (nombre del servicio `ollama`) con el modelo descargado (`ollama pull qwen2.5:3b`).

1. Clona el repositorio y entra en él.
2. Comprueba que existe la red: `docker network ls | grep ollama-local_default`. Si no, levanta antes tu
   Ollama o ajusta el nombre de la red en `compose.yaml`.
3. `docker compose up -d --build backend`. La aplicación queda en `http://127.0.0.1:8001` (solo local).
4. `curl -s http://127.0.0.1:8001/api/health/live` debe devolver `{"status":"ok"}`. `/api/health` devuelve
   503 si Ollama no responde: el chat no funcionará hasta que lo haga.
5. Crea el primer administrador (abajo). **No hay administradores ni registro público por defecto.**
6. Abre la aplicación, inicia sesión y, si quieres que otras personas pidan acceso, abre el registro en
   Administración. Cada cuenta nueva queda pendiente hasta que la apruebes.
7. Para crear claves de API: Administración → crea una organización (la creas tú como propietario) →
   Developer.

Variables de configuración: [`.env.example`](.env.example). `compose.yaml` fija las del servicio; para
cambiarlas, edítalas ahí. El modelo, los orígenes permitidos y la ruta de la base de datos son configurables,
sin valores fijos en el código.

**VERIFY:** estos pasos no se han ejecutado con Docker en el entorno de desarrollo de esta rama (sin Docker);
sí está probada la aplicación, la migración y la interfaz. La primera vez, reconstruye con
`scripts/rebuild_backend.sh` (verifica copia, tests y resultado) y comprueba el inicio de sesión.

### Sin Docker (desarrollo)

`make install && make run` (API en `127.0.0.1:8001`, Ollama en `OLLAMA_BASE_URL`). Ver [DEVELOPMENT.md](DEVELOPMENT.md).

### Copias de seguridad y actualización

- La base es un único archivo SQLite en el volumen `nexaro-personal-ai_nexaro_data`. Copia con
  `sqlite3 nexaro.db ".backup copia.db"` (o `scripts/rebuild_backend.sh`, que la hace antes de actualizar).
  Guarda las copias fuera del repositorio: contienen datos de usuarios.
- Actualizar = reconstruir **solo** `backend` conservando el volumen. Las migraciones pendientes (hoy hasta la 6)
  se aplican al arrancar en una transacción; si fallan, el arranque aborta sin dejar estado parcial.
- Revertir código: la imagen anterior queda etiquetada `rollback-<fecha>`. Las migraciones no tienen
  «bajada»: para volver atrás de verdad se restaura la copia previa.
- Nunca `docker compose down -v` ni borrar el volumen.

## Local (Docker)

```bash
docker compose up -d --build backend
```

Volumen persistente `nexaro-personal-ai_nexaro_data` (SQLite en `/data/nexaro.db`), puerto
`127.0.0.1:8001`, red externa `ollama-local_default`.

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
