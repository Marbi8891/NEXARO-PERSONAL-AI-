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

## Migraciones y multitenencia (ADR-0005)

`schema_migrations` registra versión y checksum; el lote pendiente se aplica en una transacción.
La 1 es la línea base (esquema anterior); la 2 crea organizaciones, roles/permisos, membresías,
suscripciones, proveedores de modelos, documentos, fragmentos, embeddings, agentes, ejecuciones y
tareas. Hay un juego de SQL por dialecto (`migrations/sqlite`, `migrations/postgresql`) y un test
de paridad contra un PostgreSQL real.

## Límites conocidos

- La aplicación solo ejecuta sobre SQLite: el DDL de PostgreSQL está validado, pero falta la capa de acceso (ADR-0005).
- Organizaciones y miembros tienen API; documentos, agentes y tareas solo esquema.
- Las conversaciones siguen siendo personales (`organization_id` es opcional y aún no se usa).
- Un solo proveedor de IA (Ollama).
