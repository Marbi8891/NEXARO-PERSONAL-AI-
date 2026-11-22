# Respuesta a incidentes y recuperación

Entorno: Docker en un Mac, un solo propietario. Los pasos asumen la carpeta `~/Docker/nexaro-personal-ai`.

## Qué mirar primero

```
docker logs --tail 200 nexaro-backend
docker logs nexaro-backend 2>&1 | grep '"level": "ERROR"'
```

Cada línea es JSON con `request_id`. El `request_id` también está en la cabecera `X-Request-ID` de la
respuesta y en el cuerpo de un error 500: con él se encuentra toda la traza de esa petición. Los
eventos de seguridad (`logger: nexaro.security`) llevan `event`, `outcome`, `actor_user_id` e `ip`. En
Administración → Auditoría están los mismos eventos, guardados en la base y que no se pueden modificar.

## Escenarios

| Síntoma | Actuación |
|---|---|
| Ráfaga de `auth.login failure` o `auth.lockout` | Revisar `ip` y cuentas afectadas en Auditoría. Con una sola IP (la pasarela de Docker) no se distingue al atacante: mirar desde fuera quién tiene acceso a `127.0.0.1:8001`. Cerrar el registro si estaba abierto |
| Sospecha de cuenta comprometida | Administración → desactivar usuario (revoca sesiones). Cambiar contraseña. Revisar Auditoría por actor |
| Clave de API filtrada | Revocarla en Developer. La clave se ve una sola vez y solo se guarda su hash |
| Modelo inservible / respuestas 503 | `docker stats`, `docker exec ollama ollama ps`. Subir `CHAT_MAX_CONCURRENT` no ayuda en CPU. Reiniciar solo Ollama si hace falta |
| Muchos 429 de un usuario legítimo | Subir `CHAT_REQUESTS_PER_MINUTE` en `compose.yaml` y recrear solo `backend` |
| El contenedor no arranca tras endurecerlo (`read_only`) | Ver abajo |
| Se sospecha que Ollama está expuesto | `lsof -nP -iTCP -sTCP:LISTEN \| grep 11434`; cambiar su publicación a `127.0.0.1:11434` en su propio compose |

## Si el backend no arranca

1. `docker logs --tail 50 nexaro-backend` (un `PermissionError` o `Read-only file system` apunta a `read_only`).
2. Volver a la imagen anterior: `scripts/rebuild_backend.sh` etiqueta cada vez `rollback-<fecha>` antes de reconstruir.
   `docker tag nexaro-personal-ai-backend:rollback-<fecha> nexaro-personal-ai-backend:latest` y `docker compose up -d backend`.
3. Si la causa es `read_only`, quitar esa línea de `compose.yaml` temporalmente, anotar qué ruta necesitaba escribir y añadirla como `tmpfs`.

## Recuperar la base

Las copias están en `backups/` y las crea `rebuild_backend.sh` con la API de backup de SQLite. La copia
`nexaro-pre-auth-migration-20261108.db` es el original previo a la migración: **no se toca ni se poda**.

```
docker compose stop backend
docker run --rm -v nexaro-personal-ai_nexaro_data:/data -v "$PWD/backups":/backup python:3.12-slim cp /backup/NOMBRE.db /data/nexaro.db
docker compose start backend
```

Antes de restaurar, guardar la base actual con otro nombre. Tras restaurar, el script de reconstrucción
ya comprueba integridad y conteos. Una copia solo cuenta como recuperable si se ha restaurado y probado:
**las copias existentes no se han probado en una restauración completa** (UNKNOWN).

## Retención

`scripts/prune_backups.sh --keep 10` (simulación) y `--apply` para borrar. Los logs rotan en Docker
(`10m × 5`). La tabla de auditoría no se poda (triggers append-only); una retención futura sería una
migración explícita.

## Después de un incidente

Anotar fecha, `request_id`, causa y cambio realizado en este documento o en un ADR. Si hubo filtración de
datos personales de terceros, valorar la obligación de notificar (RGPD) con asesoramiento; este documento no lo sustituye.
