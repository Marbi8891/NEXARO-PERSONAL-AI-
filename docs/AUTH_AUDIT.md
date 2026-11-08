# NEXARO Personal AI — Auditoría de autenticación (2026-11-08)

Estado: **código y pruebas validados; imagen Docker NO reconstruida todavía** (ver §6).

## 1. Hallazgos

| # | Sev. | Hallazgo | Estado |
|---|------|----------|--------|
| H1 | Crítica | `lifespan()` no llamaba a `init_auth_database()`. El `main.py` local consulta `users.is_active`/`approval_status`; sin migración, **el login falla para todos** al desplegar. (Con el código anterior, 28 de las 68 pruebas nuevas fallan.) | Corregido |
| H2 | Alta | `init_auth_schema` **no es atómica**: sqlite3 no abre transacción antes de un `ALTER`/`CREATE`; un fallo a mitad dejaba columnas nuevas ya confirmadas (reproducido). | Corregido (`BEGIN IMMEDIATE`) |
| H3 | Alta | No había forma de crear el primer admin: tu único usuario es justo `ADMIN_EMAIL` y `bootstrap_admin` se negaba si la cuenta existía. Tras migrar, ese usuario queda como `user` sin admin posible. | Corregido (`--promote-existing`) |
| H4 | Alta | Fuerza bruta evitable: un login correcto ponía a cero el contador de la IP, permitiendo intercalar accesos válidos para seguir adivinando; no había límite por cuenta; el diccionario crecía sin límite. | Corregido |
| H5 | Media | Enumeración de cuentas por tiempo: usuario inexistente/pendiente/inactivo no ejecutaba scrypt. | Corregido (hash señuelo) |
| H6 | Media | Un admin podía rechazarse a sí mismo; sin protección del último admin (bloqueo que solo se arregla con shell). | Corregido |
| H7 | Media | `login`/`register` eran `async def` con scrypt (~50-100 ms) bloqueando el event loop. | Corregido (`def` → threadpool) |
| H8 | Baja | `COPY app ./app` metía en la imagen ~30 copias `.pre-*`/`.bak`/`.backup-*`. | Corregido (`backend/.dockerignore`) |
| H9 | Baja | `ADMIN_EMAIL` con tu correo personal por defecto en el código. | Corregido (`--email` o env, obligatorio) |
| H10 | Baja | `conversation_id` sin límite de longitud. | Corregido (`max_length=64`) |
| H11 | Baja | `sessions.revoked_at` se asumía presente; no se añadía si faltaba. | Corregido (aditivo) |
| H12 | Info | **El frontend no tiene UI de administración ni de registro**: las rutas `/api/admin/*` y `/api/auth/register` solo son accesibles por API. | Pendiente (decisión tuya) |
| H13 | Info | Ninguna de las 31 pruebas originales ejercitaba rutas de `main.py`. | Añadidas 38 |

## 2. Decisiones técnicas (ADR resumidos)

**ADR-1 Migración en `lifespan`, fail-fast.** `init_database()` → `init_auth_database()` dentro de `BEGIN IMMEDIATE`. Si falla: `logger.exception` + re-raise → uvicorn aborta ("Application startup failed"), el contenedor reinicia y el fallo es visible en `docker logs`. Razón: arrancar con esquema a medias es peor que no arrancar. Trade-off: un fallo persistente deja el servicio caído (preferible a servir con datos inconsistentes; la migración es aditiva y el rollback de imagen es seguro).
**ADR-2 No se toca `get_connection()`.** Un test existente la extrae por AST y la ejecuta aislada; la transacción explícita va en los llamadores (`begin_write`).
**ADR-3 Sin admin automático, sin registro automático.** El usuario migrado recibe los defaults aditivos (`user`, activo, `approved`); el registro público queda en `0`; las sesiones existentes no se tocan (la sesión viva sigue válida: verificado). Admin solo con `bootstrap_admin --promote-existing`, manual e interactivo.
**ADR-4 Límite de intentos.** Claves `ip:` y `email:`; el éxito solo limpia la clave de email. En memoria, acotada a 10 000 claves. Aceptado: se reinicia al reiniciar el proceso y no es válido con varios workers (hoy hay uno). Detrás de Docker todas las peticiones llegan con la IP de la pasarela; como el puerto es `127.0.0.1`, es aceptable.
**ADR-5 Rehash de scrypt aplazado.** `verify_password` exige parámetros idénticos a los constantes, por lo que subir `N` hoy invalidaría todas las contraseñas. Requiere verificación versionada + rehash al login. No se hace ahora (ver §3-1).

## 3. Auditoría de seguridad

| Área | Resultado |
|---|---|
| Hashing | scrypt N=2¹⁴, r=8, p=1, sal 16 B, `compare_digest`, parámetros fijados (rechaza hashes con parámetros ajenos), mínimo 12 caracteres. **Parámetro por debajo de la recomendación actual de OWASP** (N=2¹⁷). Riesgo bajo en uso local; mejora futura = ADR-5. |
| Tokens de sesión | 256 bits (`token_urlsafe(32)`), solo se guarda SHA-256. Sin SECRET_KEY que gestionar. OK |
| Cookies | `HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age` 7 d. `Secure` controlado por `COOKIE_SECURE` (por defecto `false`: correcto para `http://127.0.0.1`; **ponerlo a `true` si algún día va tras HTTPS**). |
| Caducidad | 7 días fijos, comprobada en cada petición, sin renovación. No se purgan sesiones caducadas (crecimiento mínimo). |
| Revocación | Logout, rechazo y desactivación revocan; además la consulta de sesión exige usuario activo y aprobado. Probado. |
| Fuerza bruta | Corregido (H4/H5). |
| Rutas admin | Todas con `Depends(get_admin_user)`; el rol se lee de BD en cada petición; mutaciones validan `Origin`; no existe endpoint para conceder admin. Probado (401/403/200). |
| Inactivos / pendientes | Filtrados en login y en validación de sesión. Probado. |
| Inyección SQL | Todo parametrizado; el único f-string SQL usa constantes internas. |
| Validación | Límites pydantic en email/contraseña/mensaje/`conversation_id`. Validación de email básica (suficiente: el alta pública está cerrada y la crea un admin). |
| CORS / CSRF | Sin `CORSMiddleware` (mismo origen), allowlist de `Origin` en POST/PATCH, `SameSite=Strict`. OK |
| Errores | Mensajes genéricos para Ollama/health; sin trazas al cliente. Nota baja: el 422 de pydantic devuelve el valor enviado en `input` (solo al propio cliente). |
| Datos personales | Nunca se devuelve `password_hash`; sin secretos ni correos en código; los logs no contienen credenciales (único log: fallo de migración). Con el registro abierto, el 409 revela si un correo existe (hoy cerrado). |
| XSS | El frontend pinta contenido dinámico con `textContent`; `innerHTML` solo con literales. OK |
| Contenedor | No root (uid 10001), puerto ligado a `127.0.0.1`. OK |

## 4. Pruebas ejecutadas (Linux, Python 3.10, FastAPI 0.120.4)

- `python -m unittest discover -s backend/tests` → **69 OK** (31 originales sin modificar + 38 nuevas), 24 s.
- Migración sobre **copia** de `backups/nexaro-pre-auth-migration-20261108.db`: columnas `role/is_active/approval_status` añadidas; usuario → `user`/1/`approved`; sesiones 4, conversaciones 11, mensajes 52 conservados; `foreign_key_check` vacío; `integrity_check` ok; registro público `0`; 0 admins; 3 ejecuciones consecutivas con esquema idéntico (idempotente).
- Sesión viva del backup (`fc07ef8d…`, caduca 2026-11-15) sigue siendo válida tras migrar.
- Rollback ante fallo simulado: la base queda exactamente como estaba.
- Arranque real de `uvicorn app.main:app` sobre una copia: migra al arrancar; `/me`, `/admin/users`, `/conversations` → 401; `register` → 403; login con origen ajeno → 403; credencial mala → 401; `/health` sin Ollama → 503 genérico.
- Las pruebas nuevas **fallan contra el código anterior** (28/68), es decir, detectan los defectos.
- El backup original mantiene el SHA-256 `53ab1134…ce01` antes y después de todo.

## 5. No verificado (límites del entorno de trabajo)

- **Docker**: el entorno donde trabajé no tiene `docker` ni llega a tu Mac. No se ha ejecutado `docker compose config`, build, recreación ni comprobación de volumen/red.
- **Ollama real** (`qwen2.5:3b`): probado solo con respuestas simuladas; `/api/health` real queda para el script.
- Pruebas hechas con Python 3.10; la imagen usa 3.12 (sin diferencias esperables).
- La base viva del volumen puede haber cambiado desde el backup de las 22:02; el script toma una copia fresca antes de recrear.

## 6. Despliegue (en tu Mac)

```bash
cd /Users/macbookpro/Docker/nexaro-personal-ai
scripts/rebuild_backend.sh          # pide confirmación; usa --yes para omitirla
docker exec -it nexaro-backend python -m app.bootstrap_admin \
  --confirm-database /data/nexaro.db --email <tu_correo> --promote-existing
```

El script: verifica hash e integridad del backup → ejecuta los tests → valida compose/volumen/red → copia fresca de la base viva (API de backup) → etiqueta la imagen actual como `rollback-<fecha>` → pide confirmación → `build backend` + `up -d --no-deps backend` (sin `down`, sin `-v`, sin tocar otros servicios) → espera arranque → compara conteos antes/después, registro público, admins y Ollama.

Rollback: la migración es aditiva, así que la imagen anterior funciona con la base migrada. `docker tag nexaro-personal-ai-backend:rollback-<fecha> nexaro-personal-ai-backend:latest && docker compose up -d --no-deps backend`.

## 7. Ficheros modificados / añadidos

Modificados: `backend/app/main.py`, `backend/app/auth.py`, `backend/app/bootstrap_admin.py` (copias `*.pre-audit-20261108` al lado).
Añadidos: `backend/.dockerignore`, `backend/tests/{legacy_db,test_migration,test_main_routes,test_bootstrap_admin}.py`, `scripts/rebuild_backend.sh`, `docs/AUTH_AUDIT.md`.
Sin cambios: pruebas existentes, `compose.yaml`, `Dockerfile`, frontend, `backups/`. Sin commits.
