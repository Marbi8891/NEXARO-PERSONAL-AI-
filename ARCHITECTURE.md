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
| `nexaro_core.database` | `Database.connect()` (commit/rollback, claves foráneas, WAL, espera de bloqueos), `begin_write` |
| `nexaro_core.identity` | usuarios, sesiones, aprobación, rol, último admin protegido |
| `nexaro_core.audit` | eventos append-only (triggers), redacción de claves sensibles, conteo de eventos por ventana |
| `nexaro_core.organizations` | organizaciones, membresías, roles y permisos |
| `nexaro_core.api_keys` | claves de API: creación, hash, revocación, autenticación (ADR-0009) |
| `nexaro_core.timeseries` | series diarias sin huecos (los días sin datos valen 0) |
| `ai_gateway` | `Gateway` (políticas, respaldo, cortacircuitos por proveedor, estado `describe()`, registro de uso), `UsageStore`, proveedores Ollama, Bedrock y SageMaker |
| `products.personal_ai` | conversaciones y mensajes, historial acotado, prompt de sistema, resumen de actividad |
| `apps/api` | HTTP: rutas, validación de origen, cookies, cabeceras de seguridad, avisos derivados |

## Frontend

HTML, CSS y ES Modules sin paso de compilación (ADR-0007), servidos por la propia API. Sin React ni Next.js.

```
frontend/index.html          única página; CSP estricta (sin scripts ni estilos en línea)
frontend/css/                tokens.css (única fuente de color/espacio/tipografía), base, layout, components
frontend/js/main.js, app.js  arranque y tabla de rutas (router por hash con guardas de sesión y rol)
frontend/js/api.js           único punto que llama a la API (errores, sesión caducada)
frontend/js/shell.js         marco: barra lateral, cabecera, campana de avisos, menú de usuario
frontend/js/components/      componentes reutilizables (tabla, formulario, estados, diálogo, gráfico...)
frontend/js/views/           una vista por pantalla; sin lógica de red propia más allá de api.js
```

Reglas: el DOM se construye con `h()` (nunca `innerHTML`); los colores solo existen en `tokens.css`;
una pantalla entra en la navegación solo si tiene API real. Sistema de diseño: [docs/design-system.md](docs/design-system.md).

## Arranque y migración

`create_app()` ejecuta en el lifespan una migración aditiva e idempotente dentro de
`BEGIN IMMEDIATE`. Si falla, el arranque aborta (fail-fast) y no queda estado parcial.

## Migraciones y multitenencia (ADR-0005)

`schema_migrations` registra versión y checksum; el lote pendiente se aplica en una transacción.
La 1 es la línea base (esquema anterior); la 3 añade las claves de API y `model_usage.api_key_id` (ADR-0009); la 4 los permisos por clave (ADR-0011); la 5 los gastos (ADR-0013); la 6 las métricas de inferencia (ADR-0014); la 2 crea organizaciones, roles/permisos, membresías,
suscripciones, proveedores de modelos, documentos, fragmentos, embeddings, agentes, ejecuciones y
tareas. Hay un juego de SQL por dialecto (`migrations/sqlite`, `migrations/postgresql`) y un test
de paridad contra un PostgreSQL real.

## Límites conocidos

- La aplicación solo ejecuta sobre SQLite: el DDL de PostgreSQL está validado, pero falta la capa de acceso (ADR-0005).
- Organizaciones, miembros, claves de API, documentos (búsqueda BM25, ADR-0012; consultables desde el chat, ADR-0017) y gastos tienen API; agentes, tareas y embeddings son solo esquema.
- Las conversaciones siguen siendo personales (`organization_id` solo se rellena en el uso por clave de API).
- Con funcionalidad: Personal AI, Developer (claves de API con scopes `chat:write` y `conversations:read`), documentos, gastos (Finance) y el resumen de Security. Business es solo identidad de marca.
- El modelo se fija por variable de entorno (`OLLAMA_MODEL`): no hay selección de modelo ni de agente en tiempo de ejecución.
- SQLite en modo WAL (ADR-0015): un solo escritor a la vez; suficiente para una instancia.
- El limitador de intentos es en memoria del proceso: no se comparte entre instancias.
