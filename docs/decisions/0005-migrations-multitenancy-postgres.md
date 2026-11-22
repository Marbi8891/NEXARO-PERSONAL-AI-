# ADR-0005: Migraciones versionadas, multitenencia y PostgreSQL

- **Estado:** Aceptada (SQLite en ejecución; PostgreSQL validado a nivel de esquema, no de aplicación)
- **Fecha:** 2026-11-08

## Contexto
Hay que pasar de un esquema aditivo por código a migraciones versionadas, añadir organizaciones
con aislamiento efectivo y preparar PostgreSQL para producción. Todo el acceso a datos es hoy
`sqlite3` con SQL directo, y la base viva tiene datos reales.

## Opciones de migraciones
- **A. Alembic + SQLAlchemy.** Estándar, pero obliga a reescribir todo el acceso a datos (riesgo
  sobre una base viva) y a aprender un ORM que hoy no aporta nada.
- **B. Migrador propio mínimo** con archivos SQL numerados por dialecto, tabla
  `schema_migrations` con checksum, y una transacción para todo el lote.
- **C. Mantener `CREATE IF NOT EXISTS`.** Sin historial ni detección de cambios.

## Decisión
**B.** Unos 100 líneas, sin dependencias, aplica a SQLite hoy. La migración 1 es la línea base:
ejecuta el esquema existente (idempotente), de modo que la base viva queda marcada sin cambios.
Se detiene si un checksum aplicado cambió o si la base es más nueva que el código.
Se reconsidera Alembic si se adopta un ORM o hacen falta migraciones de datos complejas.

## Multitenencia
- Toda tabla de negocio de una organización lleva `organization_id NOT NULL` y
  `UNIQUE (id, organization_id)`. Las relaciones hijas usan **clave foránea compuesta**
  `(padre_id, organization_id)`: la base de datos rechaza que un fragmento, embedding, ejecución o
  tarea apunte a un padre de otra organización, aunque el código falle.
- Un test inspecciona el esquema y falla si una tabla nueva con `organization_id` no cumple esto.
- Capa de aplicación: el acceso a una organización pasa por membresía activa y permiso
  (`require_permission`). Quien no es miembro recibe 404, no 403.
- PostgreSQL añade **Row Level Security** (`nexaro.organization_id`) como segunda barrera; sin
  contexto no se ve ninguna fila. RLS no aplica a superusuarios: la app debe conectar con un rol
  sin privilegios. `organizations` y `memberships` quedan fuera de RLS (se consultan antes de
  elegir organización).
- Roles fijos del sistema (owner, admin, member, viewer). Roles personalizados por organización
  quedan fuera hasta que haya un caso de uso.

## PostgreSQL: qué está hecho y qué no
- Hecho: DDL propio (`uuid`, `timestamptz`, `jsonb`, `bytea`), validado contra un PostgreSQL 16
  real en los tests, con prueba de paridad de tablas y columnas con SQLite y pruebas de RLS.
- **No hecho:** la capa de acceso sigue siendo `sqlite3`; la aplicación aún no arranca sobre
  PostgreSQL. Falta una abstracción de conexión (marcadores `?`/`%s`, filas) o un ORM. Es el
  siguiente paso antes de producción y requiere su propia decisión.
- Embeddings: `bytea`. `pgvector` sería lo natural; UNKNOWN si estará disponible en el destino
  (Aurora lo soporta: VERIFY al llegar a Terraform).

## Consecuencias
Dos juegos de SQL que mantener; el test de paridad evita que diverjan. Las migraciones aplicadas
no se editan: se añade una nueva.
