# Base de seguridad (qué se espera de un despliegue correcto)

Lista de comprobación. Lo marcado **VERIFY** no se puede asegurar desde el repositorio.

## Antes de usarlo

| # | Comprobación | Comando | Esperado |
|---|---|---|---|
| 1 | Backend solo en localhost | `docker ps --format 'table {{.Names}}\t{{.Ports}}'` | `127.0.0.1:8001->8000` |
| 2 | **VERIFY** Ollama no publicado fuera | `lsof -nP -iTCP -sTCP:LISTEN \| grep -E '11434\|8080'` | solo `127.0.0.1` o `localhost`, o nada |
| 3 | Contenedor endurecido | `docker inspect nexaro-backend --format '{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.CapDrop}} {{.HostConfig.SecurityOpt}}'` | `true [ALL] [no-new-privileges:true]` |
| 4 | Usuario sin privilegios | `docker exec nexaro-backend id -u` | `10001` |
| 5 | Swagger cerrado | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/openapi.json` | `404` |
| 6 | Registro público cerrado | Administración → ajustes | desactivado |
| 7 | Un solo administrador creado a mano | `bootstrap_admin` | sin admins automáticos |
| 8 | Migraciones al día | `docker exec nexaro-backend python -c "import sqlite3;print(sqlite3.connect('file:/data/nexaro.db?mode=ro',uri=True).execute('select max(version) from schema_migrations').fetchone())"` | `(6,)` |

## Datos

| Tema | Estado |
|---|---|
| Cifrado en tránsito | **No hay TLS** en local (HTTP sobre `127.0.0.1`). En producción: `NEXARO_ENV=production`, `COOKIE_SECURE=true` y orígenes `https://` (la aplicación se niega a arrancar si no) detrás de un proxy TLS |
| Cifrado en reposo | **SQLite y las copias NO están cifrados.** Dependen del cifrado del disco del Mac (FileVault: **VERIFY**). Si se necesita cifrado propio: cifrar las copias con `age` o migrar a PostgreSQL con cifrado de volumen |
| Contraseñas | scrypt con sal; mínimo 12 caracteres |
| Sesiones y claves de API | solo hash en base de datos; claves de API visibles una vez |
| Retención de copias | `scripts/prune_backups.sh --keep 10 --apply` (manual; no hay programación automática) |
| Borrado seguro | No garantizado: SQLite y APFS no sobrescriben al borrar. Un borrado lógico (documentos, gastos) no elimina los bytes hasta `VACUUM` y aun así depende del sistema de archivos |
| Permisos | `backups/` y `data/` deben ser `700`/`600` en el host; el código se copia con `a+rX` a la imagen |

## Operación

- Límites por defecto: 30 peticiones/min por usuario al modelo, 2 generaciones simultáneas, 2 MiB por petición, login 5 intentos/15 min por cuenta.
- Logs: JSON por stdout, rotados por Docker (`10m × 5`), sin contenido de mensajes, consultas ni secretos.
- Actualización de imágenes: mensual o ante aviso; copiar el nuevo digest de `python:3.12-slim` al `Dockerfile`, pasar los tests y reconstruir con `scripts/rebuild_backend.sh` (guarda la imagen anterior para volver atrás).
- Lo que este documento no afirma: cumplimiento de certificaciones, seguridad absoluta ni ausencia de vulnerabilidades.
