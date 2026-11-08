# Arquitectura

Monolito modular (ADR-0001): un proceso, un despliegue, módulos con dependencias dirigidas.

```
apps/api  ──►  products/*  ──►  packages/{nexaro_core, ai_gateway}
```

- `packages/*` no importan `products/*` ni `apps/*`.
- Los `products/*` no se importan entre sí ni importan `apps/*`.
- `nexaro_core` y `products` no importan FastAPI/Starlette.
- Las tres reglas las comprueba `tests/unit/test_architecture.py`.

## Módulos

| Módulo | Responsabilidad |
|---|---|
| `nexaro_core.config` | `Settings` desde entorno; en producción exige cookie `Secure` y orígenes https |
| `nexaro_core.security` | scrypt, tokens de sesión (solo se guarda el SHA-256), `RateLimiter` |
| `nexaro_core.database` | `Database.connect()` (commit/rollback, claves foráneas), `begin_write` |
| `nexaro_core.identity` | usuarios, sesiones, aprobación, rol, último admin protegido |
| `nexaro_core.audit` | eventos append-only (triggers), redacción de claves sensibles |
| `ai_gateway` | `ChatProvider` (Protocol) y `OllamaProvider` |
| `products.personal_ai` | conversaciones y mensajes, historial acotado, prompt de sistema |
| `apps/api` | HTTP: rutas, validación de origen, cookies, cabeceras de seguridad |

## Arranque y migración

`create_app()` ejecuta en el lifespan una migración aditiva e idempotente dentro de
`BEGIN IMMEDIATE`. Si falla, el arranque aborta (fail-fast) y no queda estado parcial.

## Límites conocidos

- Persistencia solo SQLite; el esquema no está versionado todavía (migración aditiva por código).
- Sin multitenencia efectiva: el aislamiento actual es por usuario (`conversations.user_id`).
- Un solo proveedor de IA (Ollama).
