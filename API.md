# API

Base `/api`. Autenticación por cookie de sesión HttpOnly (`SameSite=Strict`). Las rutas que
modifican estado exigen cabecera `Origin` incluida en `ALLOWED_ORIGINS`. En producción
`/docs` está desactivado.

| Método | Ruta | Acceso | Notas |
|---|---|---|---|
| GET | `/health` | público | 503 genérico si Ollama no responde |
| GET | `/health/live` | público | liveness del proceso |
| POST | `/auth/register` | público | 403 mientras el registro público esté cerrado (por defecto); la cuenta queda pendiente |
| POST | `/auth/login` | público | limitado por IP+correo; error idéntico para usuario inexistente y clave errónea |
| GET | `/auth/me` | sesión | |
| POST | `/auth/logout` | sesión | revoca la sesión en servidor |
| POST | `/chat` | sesión | `{message, conversation_id?}` |
| GET | `/conversations` | sesión | solo las del usuario |
| GET | `/conversations/{id}` | sesión | 404 si no es del usuario |
| GET | `/admin/users` | admin | |
| POST | `/admin/users` | admin | crea siempre rol `user`; clave mínima obligatoria |
| POST | `/admin/users/{id}/approve` · `/reject` | admin | |
| PATCH | `/admin/users/{id}/active` | admin | no sobre uno mismo; protege al último admin |
| PATCH | `/admin/settings/registration` | admin | abre/cierra el registro público |
| GET | `/admin/audit` | admin | |
| GET | `/organizations` | sesión | organizaciones del usuario y su rol |
| POST | `/organizations` | admin plataforma | crea la organización; el creador es propietario (ASSUMPTION: solo admins de plataforma) |
| GET | `/organizations/{id}/members` | `members:read` | 404 si no eres miembro (también para admins de plataforma) |
| POST | `/organizations/{id}/members` | `members:manage` | `{email, role}`; el usuario debe existir |
| PATCH/DELETE | `/organizations/{id}/members/{user_id}` | `members:manage` | solo propietarios tocan propietarios; el último no se puede quitar |
| GET | `/admin/usage` | admin | uso de modelos por proveedor/modelo (`days`, máx. 365) y coste del mes |

Códigos: 400 operación no permitida (p. ej. sobre uno mismo o el último admin), 401 sin sesión,
403 origen/rol/registro cerrado, 404 recurso ajeno, 409 correo duplicado, 422 validación,
422 también cuando la política del gateway rechaza la entrada (p. ej. demasiado larga),
429 limitación de intentos, 502 fallo del proveedor de IA (sin detalles).
