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

Códigos: 400 operación no permitida (p. ej. sobre uno mismo o el último admin), 401 sin sesión,
403 origen/rol/registro cerrado, 404 recurso ajeno, 409 correo duplicado, 422 validación,
429 limitación de intentos.
