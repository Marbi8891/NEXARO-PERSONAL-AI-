# Aislamiento de conversaciones por usuario

- **Fecha:** 2026-11-22
- **Rama:** `security/conversation-isolation` (desde `feature/nexaro-design-system`, `175d1ab`)
- **Alcance:** backend FastAPI (`apps/api`, `packages`, `products`), esquema SQLite/PostgreSQL y frontend (`frontend/js`).

## 1. Auditoría inicial (antes de cambiar nada)

### 1.1 Modelo de identidad

| Pieza | Dónde | Cómo funciona |
|---|---|---|
| Sesión web | `deps.get_current_user` → `identity.get_session_user` | Cookie HttpOnly con un token opaco. Su hash se busca en `sessions`, junto con el usuario activo y aprobado. La identidad sale **solo** del servidor. |
| Clave de API | `deps.get_api_key_identity` → `api_keys.authenticate_api_key` | `Bearer nxr_…`. Su hash se valida contra la organización activa y el creador (activo, aprobado y miembro activo). `user_id` = `api_keys.created_by`. |
| Rol de plataforma | `users.role` (`admin`/`user`) | `get_admin_user`. **No** da acceso a organizaciones (`check_org_permission`) ni a conversaciones. |
| Organizaciones | `memberships` + `role_permissions` | `require_permission(...)`. No ser miembro → 404. |

Ningún endpoint lee `user_id` del cliente: no aparece en `schemas.py` ni en ningún `Query`/`Body`. Tampoco lo envía el frontend: `frontend/js` solo usa `user_id` para gestionar miembros de una organización.

### 1.2 Inventario de rutas que tocan conversaciones o mensajes

| Ruta | Operación | Filtro de propietario en SQL | Estado |
|---|---|---|---|
| `GET /api/conversations` | Listar | `WHERE c.user_id = ?` | OK |
| `GET /api/conversations/{id}` | Leer y mensajes | `WHERE id = ? AND user_id = ?`; después mensajes por `conversation_id` | OK |
| `DELETE /api/conversations/{id}` | Borrar | `SELECT … WHERE id = ? AND user_id = ?` dentro de `BEGIN IMMEDIATE` | OK |
| `POST /api/chat`, `POST /api/chat/stream` | Crear o añadir mensajes | `_claim_conversation` | **V-01** |
| `POST /api/v1/chat` | Crear o añadir (clave) | `_claim_conversation` con `organization_id` de la clave | **V-01** |
| `GET /api/v1/conversations[/{id}]` | Leer (clave) | `user_id = created_by AND organization_id = org de la clave` | OK |
| `GET /api/dashboard` | Totales y recientes | `WHERE c.user_id = ?` | OK |
| Modificar o renombrar, exportar, buscar en el historial, WebSocket | — | **No existen** en el código | Sin superficie |

### 1.3 Recursos relacionados

| Recurso | Ámbito | Acceso |
|---|---|---|
| `documents`, `document_chunks` | Organización, compartidos entre miembros por diseño | Todas las consultas llevan `organization_id`, y la ruta exige membresía con `documents:read/write`. Un documento de otra organización da 404. |
| Documentos en el chat (`document_organization_id`) | Organización | `_document_scope` → `check_org_permission`. Los fragmentos no se guardan en `messages`. |
| `embeddings`, `agents`, `agent_runs`, `tasks` | Organización | Solo existen las tablas. **Ningún código las lee ni las escribe** (`grep`) y no hay rutas. |
| `model_usage` | Usuario u organización | Solo contiene métricas, nunca texto. La lectura es para el administrador (agregados) o por organización con `usage:read`. |
| `audit_events` | Plataforma | `conversation.delete` guarda solo el id. No hay contenido de mensajes. |
| Gastos (`export.csv`) | Organización | `expenses:read`. No tiene relación con conversaciones. |

### 1.4 Administradores

- No hay ninguna ruta de administración que devuelva conversaciones ni mensajes. `/api/admin/*` solo cubre cuentas, registro, auditoría, seguridad, modelos y uso agregado.
- `GET /api/dashboard` como `admin` añade agregados de plataforma, pero `activity` sigue filtrando por el propio `user["id"]`.
- **No existe acceso administrativo al contenido.** No se añade ninguno.

### 1.5 Vulnerabilidades encontradas

| ID | Gravedad | Hallazgo | Dónde |
|---|---|---|---|
| **V-01** | Media | **Oráculo de existencia e IDs elegidos por el cliente.** Con un `conversation_id` desconocido, `_claim_conversation` **crea** una conversación con ese id (200). Si el id existe y es de otro usuario, devuelve 404. Así, un atacante con un id filtrado (logs, URL o captura) puede confirmar que existe, y cualquiera puede ocupar ids arbitrarios. Incumple «no revelar si la conversación existe». | `products/personal_ai/service.py::_claim_conversation` |
| **V-02** | Media | **`conversations.user_id` admite NULL.** Se añadió con `ALTER TABLE ADD COLUMN`. Hoy ninguna consulta expone filas huérfanas, porque `user_id = ?` nunca coincide con NULL. Pero la base no impide que un error futuro inserte conversaciones sin propietario. | Esquema (baseline `identity/schema.py`) |
| **V-03** | Baja | **La propiedad es mutable.** Nada impide un `UPDATE conversations SET user_id = …` que pase una conversación de un usuario a otro. | Esquema |
| **V-04** | Baja | **`messages` no tiene propietario propio.** El aislamiento depende de que cada consulta compruebe antes la conversación. Hoy todas lo hacen, pero la base permite añadir mensajes a una conversación huérfana. | Esquema |
| **V-05** | Baja | **La recuperación de huérfanas no deja rastro.** `bootstrap_admin --assign-orphaned-conversations` es explícita y hace copia de seguridad, pero no registra nada en `audit_events`. | `apps/api/nexaro_api/bootstrap_admin.py` |
| **V-06** | Baja (UX/privacidad local) | **El id recordado no va ligado al usuario.** `localStorage.nexaro_conversation_id` es global al navegador. Si otro usuario entra sin un *logout* previo (por ejemplo, una cookie caducada con el navegador cerrado), el frontend intenta abrir la conversación del anterior. El backend responde 404 y no hay fuga, pero se envía un id ajeno. | `frontend/js/state.js` |

No se ha encontrado ningún IDOR explotable que permita **leer, modificar o borrar** datos ajenos. Las rutas existentes ya filtraban por `user_id` en SQL. V-01 es la única que revela información (la existencia de un id).

## 2. Cambios realizados

| ID | Corrección | Archivos |
|---|---|---|
| V-01 | `get_conversation_for_user()` es la única puerta de acceso por id, con el propietario en el mismo `WHERE`. Solo se crea una conversación sin `conversation_id`, con id del servidor y `user_id` de la identidad autenticada. Un id desconocido, ajeno o de otro origen da el mismo 404. | `products/personal_ai/service.py` |
| V-02..V-04 | Migración **0008** (la 0007 es `message_agent`): triggers `conversations_owner_required`, `conversations_owner_immutable` (solo admite NULL → usuario) y `messages_conversation_owned`, más el índice `idx_conversations_user_org`. En PostgreSQL: `CHECK … NOT VALID` y triggers plpgsql. **No toca filas existentes.** | `migrations/sqlite/0008_conversation_ownership.sql`, `migrations/postgresql/0008_conversation_ownership.sql`, `database/migrations.py` |
| V-05 | `--assign-orphaned-conversations` registra `conversation.orphans_assigned` en `audit_events`, en la misma transacción. | `apps/api/nexaro_api/bootstrap_admin.py` |
| V-06 | El id recordado se guarda junto al id del usuario; si es de otra cuenta, se descarta. | `frontend/js/state.js` |

Tests adaptados al nuevo contrato (un id desconocido → 404): `tests/security/test_abuse_limits.py` y `tests/security/test_sql_injection.py`.
Test nuevo: `tests/security/test_conversation_isolation.py` (38 casos: los tests 1–12 pedidos, el administrador, las claves de API, el inventario de rutas, los triggers, la migración con huérfanas y la auditoría de la recuperación).

## 3. Resultados (2026-11-22, Windows, Python 3.12)

- Suite completa: **463 passed, 2 skipped, 3 failed**. Los 3 fallos son `tests/unit/test_prune_backups.py`, que necesita `bash` en el PATH de Windows. Fallan igual sin estos cambios.
- Con el `service.py` original, `test_09b` y `test_12c` **fallan**: los tests detectan V-01.
- `ruff check`, `ruff format --check` y `mypy`: limpios. `test_postgres_schema` (PostgreSQL real, `pgserver`) pasa con la 0008.
- Imagen Docker reconstruida con otra etiqueta: arranca, aplica las migraciones 1–7, `/api/health/live` responde 200 y `/api/conversations` sin sesión responde 401.
- Copia de la base real (backup en línea de solo lectura) migrada en un contenedor desechable: `integrity_check` ok y mismos recuentos de usuarios, conversaciones, mensajes, auditoría y documentos. 0 huérfanas.

### Integración sobre `main` (renumeración a 0008)

En `main`, la versión 7 ya es `message_agent` (ADR-0022), así que la propiedad pasa a ser la **versión 8** (`0008_conversation_ownership.sql` en SQLite y PostgreSQL). `run_migrations` identifica cada migración por número y checksum y exige 1..N sin huecos:

- Base de `main` (hasta la 7): al arrancar aplica solo la 8; no se tocan datos ni `messages.agent`.
- Base nueva o anterior a la 7: aplica 7 y 8 en ese orden, en la misma transacción.
- Base que aplicó la antigua 0007 de la rama de seguridad (propiedad como versión 7): la migración **falla sin aplicar nada** («La migración 7 aplicada fue modificada»), no se reinterpreta. Esa rama no llegó a `main`; si existiera una base así, se restaura una copia anterior a esa migración o se revisa a mano antes de arrancar.
- PostgreSQL no tiene registro de versiones propio: los scripts se aplican en orden de nombre (`0007_message_agent`, `0008_conversation_ownership`).

Las comprobaciones con Docker y con la copia de la base real de la sección 3 se hicieron antes de la renumeración (migraciones 1–7 de la rama de seguridad) y no se han repetido.

Tras la integración, la respuesta fija del filtro de temas restringidos (ADR-0019) pasa por la misma comprobación de propiedad: un id ajeno o desconocido da el mismo 404 también en ese camino y en streaming.

## 4. Huérfanas: procedimiento

Las conversaciones con `user_id` NULL no se borran ni se asignan solas, y nadie las ve, ni siquiera el administrador. Para recuperarlas: copia de seguridad (la hace el CLI), luego `python -m nexaro_api.bootstrap_admin --confirm-database <ruta> --email <propietario> --promote-existing --assign-orphaned-conversations`. Queda auditado.

## 5. Riesgos pendientes

- No existen rutas para renombrar, exportar, buscar en el historial, WebSocket ni agentes o tareas. `test_12e` falla si se añade una sin su test de aislamiento.
- `messages` no tiene `user_id`: el aislamiento depende de la conversación (lo imponen el trigger y la puerta única).
- Las claves de API pertenecen a su creador. Al revocar la membresía o desactivar la cuenta, la clave deja de funcionar (ya comprobado en `authenticate_api_key`).

## 6. Comandos

```powershell
$env:PYTHONUTF8=1; .venv-nexaro-tests\Scripts\python -m pytest -q
.venv-nexaro-tests\Scripts\python -m pytest -q tests/security/test_conversation_isolation.py
.venv-nexaro-tests\Scripts\ruff check .; .venv-nexaro-tests\Scripts\mypy packages apps products
docker compose up -d --build backend   # aplica la 0008 a la base del volumen; nunca `down -v`
```
