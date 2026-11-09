# API

Base `/api`. Dos formas de autenticarse:

- **Sesión (navegador):** cookie HttpOnly `SameSite=Strict`. Las rutas que modifican estado exigen
  cabecera `Origin` incluida en `ALLOWED_ORIGINS`.
- **Clave de API (programática):** `Authorization: Bearer nxr_…` solo en `/api/v1/*`; no usa cookies ni
  `Origin`. Ver [ADR-0009](docs/decisions/0009-api-keys-developer-module.md).

En producción `/docs` está desactivado. En desarrollo, la referencia generada (OpenAPI) está en `/docs`.

## Plataforma y sesión

| Método | Ruta | Acceso | Notas |
|---|---|---|---|
| GET | `/health` | público | 503 genérico si Ollama no responde |
| GET | `/health/live` | público | liveness del proceso |
| POST | `/auth/register` | público | 403 mientras el registro público esté cerrado (por defecto); la cuenta queda pendiente |
| POST | `/auth/login` | público | limitado por IP+correo; error idéntico para usuario inexistente y clave errónea |
| GET | `/auth/me` | sesión | |
| POST | `/auth/logout` | sesión | revoca la sesión en servidor |

## NEXARO Personal AI

| Método | Ruta | Acceso | Notas |
|---|---|---|---|
| POST | `/chat` | sesión | `{message, conversation_id?}` → `{conversation_id, answer}` |
| GET | `/conversations` | sesión | solo las del usuario |
| GET | `/conversations/{id}` | sesión | 404 si no es del usuario |

## Panel y avisos

| Método | Ruta | Acceso | Notas |
|---|---|---|---|
| GET | `/dashboard?days=14` | sesión | `days` 1–90. `activity`: conversaciones, mensajes, última actividad, mensajes por día (sin huecos: los días sin datos valen 0) y 5 conversaciones recientes. `admin` (solo administradores de plataforma, `null` si no): cuentas (total, pendientes, inactivas), peticiones al modelo por día, coste del mes y contadores de seguridad de 24 h |
| GET | `/notifications` | sesión | Avisos derivados del estado real en cada consulta (no se guardan). Todos: modelo de IA no disponible. Administradores: solicitudes pendientes, ≥5 accesos fallidos en 1 h, registro público abierto. Sin correos ni IPs |

## Organizaciones

| Método | Ruta | Acceso | Notas |
|---|---|---|---|
| GET | `/organizations` | sesión | organizaciones del usuario y su rol |
| POST | `/organizations` | admin plataforma | el creador es propietario (ASSUMPTION: solo admins de plataforma crean organizaciones) |
| GET | `/organizations/{id}/members` | `members:read` | 404 si no eres miembro (también para admins de plataforma) |
| POST | `/organizations/{id}/members` | `members:manage` | `{email, role}`; el usuario debe existir |
| PATCH/DELETE | `/organizations/{id}/members/{user_id}` | `members:manage` | solo propietarios tocan propietarios; el último no se puede quitar |

## Developer (claves de API y uso)

| Método | Ruta | Acceso | Notas |
|---|---|---|---|
| GET | `/organizations/{id}/api-keys` | `api_keys:manage` | sin secreto ni hash; incluye `status` (`active`, `expired`, `revoked`) |
| POST | `/organizations/{id}/api-keys` | `api_keys:manage` | `{name, expires_in_days?, scopes?}` (1–365; `scopes` entre `chat:write` y `conversations:read`, por defecto `chat:write`). La respuesta incluye `secret`: **única vez que se muestra**. 409 con 25 claves activas |
| DELETE | `/organizations/{id}/api-keys/{key_id}` | `api_keys:manage` | 204; revocación lógica e idempotente; 404 si la clave no es de esa organización |
| GET | `/organizations/{id}/usage?days=30` | `usage:read` | `days` 1–90. Por clave: peticiones, errores, tokens y coste. Solo cuenta lo que pasó por una clave |
| POST | `/v1/chat` | clave con `chat:write` | mismo cuerpo y respuesta que `/chat`; las conversaciones quedan marcadas con la organización de la clave |
| GET | `/v1/conversations?limit=50` | clave con `conversations:read` | solo conversaciones creadas con claves de la organización (1–100) |
| GET | `/v1/conversations/{id}` | clave con `conversations:read` | 404 si no es de esa organización (incluye el chat web) |

Sin el permiso: 403. Cada clave admite 60 peticiones por minuto (`API_KEY_REQUESTS_PER_MINUTE`); al superarlo, 429 con `Retry-After`. Ver [ADR-0011](docs/decisions/0011-api-key-scopes-and-read-api.md).

Permisos: `api_keys:manage` y `usage:read` los tienen propietario y administrador de la organización.

```bash
curl -X POST http://127.0.0.1:8001/api/v1/chat \
  -H "Authorization: Bearer TU_CLAVE" -H "Content-Type: application/json" \
  -d '{"message": "Hola"}'
```

## Administración de plataforma

| Método | Ruta | Acceso | Notas |
|---|---|---|---|
| GET | `/admin/users` | admin | |
| POST | `/admin/users` | admin | crea siempre rol `user`; clave mínima obligatoria |
| POST | `/admin/users/{id}/approve` · `/reject` | admin | |
| PATCH | `/admin/users/{id}/active` | admin | no sobre uno mismo; protege al último admin |
| PATCH | `/admin/settings/registration` | admin | abre/cierra el registro público |
| GET | `/admin/audit` | admin | filtro `action`, `limit` |
| GET | `/admin/security?days=14` | admin | `days` 1–90. Resumen derivado de la auditoría: totales (accesos fallidos y correctos, denegaciones, bloqueos), serie diaria sin huecos, 5 IP con más fallos, incidencias por tipo y las 10 últimas. Sin correos, seudónimos ni `details` |
| GET | `/admin/usage` | admin | uso de modelos por proveedor/modelo (`days`, máx. 365) y coste del mes |

## Códigos

400 operación no permitida (p. ej. sobre uno mismo o el último admin), 401 sin sesión o clave no válida
(mismo mensaje para clave inexistente, revocada o caducada), 403 origen/rol/permiso/registro cerrado,
404 recurso ajeno, 409 conflicto (correo o identificador duplicado, límite de claves), 422 validación
(también cuando la política del gateway rechaza la entrada), 429 limitación de intentos, 502 fallo del
proveedor de IA (sin detalles).
