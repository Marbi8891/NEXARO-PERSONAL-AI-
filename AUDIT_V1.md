# Auditoría NEXARO v1.0

Fecha: 2026-11-23. Trabajo en la rama `claude/nexaro-v1-consolidation-921fe0` (worktree de
`C:\Users\pc\NEXARO-PERSONAL-AI`, desde `main` 4022b0e = PR #21). Sin commits, push ni merges.

Leyenda: **[C]** problema confirmado (con evidencia) · **[R]** riesgo potencial · **[H]** hipótesis ·
**[Rec]** recomendación. Prioridad: CRÍTICO / ALTO / MEDIO / BAJO.

## 1. Estado real encontrado

### Git y clones

| Ubicación | Rama | Estado |
|---|---|---|
| `C:\Users\pc\NEXARO-PERSONAL-AI` | `integration/security-conversation-isolation` (af7a09e) | limpio; origen de este worktree |
| `C:\Users\pc\NEXARO-PERSONAL-AI-` (la ruta indicada en el encargo) | `security/conversation-isolation` | **muchos cambios en el índice sin commit** (README, compose, Dockerfile, routers, obsidian…). No se ha tocado. |
| `C:\Users\pc\NEXARO-PERSONAL-AI-winfix` | `fix/windows-bash-tests` | worktree; ya integrado en `main` (PR #21) |
| `C:\Users\pc\Documents\NEXARO-PERSONAL-AI-` | ? | de aquí sale el contenedor `nexaro-prompt-library` |

**[C] ALTO** — Hay cuatro copias del proyecto en el equipo y el despliegue se hace desde la que
tiene trabajo sin confirmar. Riesgo de desplegar algo distinto de lo probado. [Rec] Desplegar desde
un único clon limpio en `main` (DEPLOYMENT.md).

### Docker (estado real, `docker ps -a`)

| Contenedor | Proyecto (carpeta de compose) | Estado |
|---|---|---|
| `nexaro-backend` | `nexaro-personal-ai` (`C:\Users\pc\NEXARO-PERSONAL-AI-`) | **Created, nunca arrancó** |
| `nexaro-prompt-library` | `C:\Users\pc\Documents\NEXARO-PERSONAL-AI-` | Up, **publica 127.0.0.1:8001** |
| `ollama` | `C:\Docker\ollama-local` | Up (healthy), sin puertos, 12 GiB, root |
| `nexaro-backend-1`, `nexaro-caddy-1`, `nexaro-agent-runner-1`, `nexaro-ollama-1` | `C:\Users\pc\nexaro-ai` (otro producto: agent hub) | Up (healthy) |
| `nexaro-ai` | `C:\Users\pc\Downloads\NEXARO-AI-Frontend\...` | Up, 127.0.0.1:8080 |

**[C] CRÍTICO** — NEXARO Personal AI **no está en marcha**. `docker inspect nexaro-backend`:
`Bind for 127.0.0.1:8001 failed: port is already allocated` (desde el 22/11, 23:39). El puerto lo
ocupa `nexaro-prompt-library`. Corrección aplicada: el puerto del host es configurable
(`NEXARO_PORT`, siempre en 127.0.0.1). **Decisión tuya (BLOCKED):** parar la Prompt Library
standalone (la PR #11 la integra en NEXARO) o usar `NEXARO_PORT=8002`.

**[C] MEDIO** — La imagen `nexaro-personal-ai-backend` existente es anterior a `main`: la base del
volumen `nexaro-personal-ai_nexaro_data` está en el esquema **v6** (`schema_migrations` 1–6, leído
en solo lectura con `immutable=1`); `main` está en v7. Contiene 1 usuario, 1 conversación,
2 mensajes, 0 documentos y una copia antigua `nexaro.pre-admin-20261122-113927.db`. La
actualización v6→v7 está probada (`tests/integration/test_upgrade_paths.py`).

### Línea base de calidad (antes de cambiar nada)

`pytest` en Windows: **585 passed, 5 failed, 3 skipped** (cobertura 87,65 %). `ruff check` OK,
`ruff format` OK, `mypy` OK. Los 5 fallos eran **[C] bugs reales en Windows**: lecturas con la
codificación del sistema (cp1252) en lugar de UTF-8 (`test_architecture.py` ×2,
`test_quality_eval.py` ×2, `test_prune_backups.py`), uno de ellos también en el propio script
(`scripts/quality_eval.py`, salida del sandbox Docker). Corregidos. CI solo corre en Linux, por eso
no se detectaban.

## 2. Estado por componente

| Componente | Estado | Evidencia / notas |
|---|---|---|
| Arquitectura | Sólida: monolito modular (FastAPI + paquetes sin FastAPI), ADRs 0001–0022 | `tests/unit/test_architecture.py` vigila dependencias |
| Backend / API | Completo para v1; 55 rutas HTTP | API.md |
| Autenticación | Sólida; **[C] faltaba cambio de contraseña** → añadido | SECURITY_REVIEW_V1.md AUTH-1 |
| Autorización / usuarios / organizaciones | Sólida, con tests negativos | `tests/security/*` |
| Agentes | 7 agentes estáticos (general, developer, security, research, productivity, data, tutor) con herramientas por permiso. CRUD de agentes personales y de organización **en PR #10, no en main** | `products/personal_ai/agents.py` |
| Chat y streaming | Completo; límites, cancelación, persistencia de lo parcial | E2E jsdom |
| Memoria | Historial por conversación (8 000 caracteres); **sin memoria a largo plazo** entre conversaciones | por diseño |
| Documentos / RAG | Léxico (BM25) por organización, PDF, citas de fuente; embeddings solo esquema | ADR-0012, 0017, 0018 |
| Obsidian | Conector de solo lectura; **[C] ALTO legible por cualquier usuario** → corregido | SECURITY_REVIEW_V1.md OBS-1..5 |
| Ollama | Gateway con cortacircuitos, reintentos, métricas de inferencia | ADR-0016 |
| SQLite / migraciones | WAL, FK activadas, migraciones transaccionales con checksum | §3 |
| API keys | Hash, scopes, caducidad, límite por clave | `test_api_keys.py` |
| Logs | JSON, `request_id`, redacción; rotación por Docker (10 MiB × 5) | `test_logging.py` |
| Rate limiting | En memoria por proceso; cubre login, chat, API, Obsidian (nuevo), contraseña (nuevo) | §SECURITY |
| Frontend / PWA | ES modules, CSP estricta; **[C] 3 problemas móviles/PWA** → corregidos (§5) | E2E 36/36 |
| Accesibilidad | Roles ARIA en pestañas, labels, `aria-describedby`; objetivos táctiles corregidos | revisión en 375×812 |
| Docker | Endurecido (no root, read-only, cap_drop, límites, healthcheck, logs) | `test_container_hardening.py` |
| CI/CD | ruff, mypy, pytest+cobertura, pip-audit, bandit, SBOM, gitleaks, Trivy, terraform validate, build+healthcheck. **[R] solo Linux** | `.github/workflows/ci.yml` |
| Copias de seguridad | **[C] no había nada para Windows**; solo bash de macOS atado a una copia concreta | §6 → implementado |
| Observabilidad | Logs y `/api/admin/models`, `/usage`; **sin vista de salud/recursos/copias** | → `/api/admin/status` + pestaña Operaciones |
| Acceso remoto | Inexistente; solo 127.0.0.1 | → REMOTE_ACCESS.md (preparado, sin activar) |
| Infraestructura cloud (Terraform AWS) | Escrita, **no aplicada** (decisión del propietario) | README |
| Dependencias | pip-audit en CI; ver resultado local en RELEASE_CHECKLIST_V1.md | |

### Funcionalidades duplicadas

- **[C]** Prompt Library: app standalone (`feature/prompt-library-mvp`, PR #2, en conflicto, y el
  contenedor `nexaro-prompt-library`) **y** módulo integrado (`claude/prompt-library-module`, PR #11).
- **[C]** `feat/nexaro-dashboard-entry` es una versión anterior de PR #11 (solo difiere en
  `0011_prompt_library.sql` y ADR-0024, que en #11 son 0012 y ADR-0025).
- **[C]** Dos ramas de aislamiento: `security/conversation-isolation` (migración 0007, choca con la
  0007 de `main`) e `integration/security-conversation-isolation` (la misma, renumerada a 0008).
- **[H]** Tres «backends NEXARO» distintos en ejecución (`nexaro-ai` agent hub, NEXARO-AI-Frontend,
  NEXARO Personal AI): productos distintos según sus composes; conviene nombrarlos para no confundirlos.

## 3. Base de datos y migraciones

| Comprobación | Resultado |
|---|---|
| Migraciones | 1 (línea base idempotente en Python) + 0002–0007 SQL; PostgreSQL 0001–0007 equivalentes |
| Transacciones | Todo el lote pendiente en una transacción `BEGIN IMMEDIATE`; fallo → no queda nada (test existente) |
| Integridad | Checksum de cada migración aplicada; una base con migraciones desconocidas (código más antiguo u otra rama) **no arranca y no se toca** (tests nuevos) |
| Foreign keys | `PRAGMA foreign_keys = ON` en cada conexión; claves compuestas por organización |
| Índices | `messages(conversation_id, id)`, y los de cada migración |
| Concurrencia | WAL + `busy_timeout` 10 s + `synchronous=NORMAL`; un solo proceso uvicorn |
| Recuperación / backups | Copia online con la API de backup de SQLite (§6) |
| Actualización desde versiones anteriores | **Nuevo:** `tests/integration/test_upgrade_paths.py` crea una base real en cada versión v1…v6 con datos, arranca la app actual, hace login y lee la conversación: 6/6 PASS, `integrity_check` y `foreign_key_check` limpios |
| Migraciones destructivas | Ninguna (todas aditivas) |

**[C] ALTO (integración)** — Numeración de migraciones incompatible entre ramas pendientes:

| Rama | 0008 | 0009 | 0010 | 0011 | 0012 |
|---|---|---|---|---|---|
| `integration/security-conversation-isolation` | conversation_ownership | | | | |
| PR #8 → #11 (cadena) | conversation_title | conversation_model | user_agents | organization_agents | prompt_library |
| `feat/nexaro-dashboard-entry` | conversation_title | conversation_model | user_agents | **prompt_library** | |

Si una base aplica la 0008 de una rama y luego se despliega la otra, el arranque se aborta
(checksum distinto). No hay pérdida de datos (probado), pero el servicio no arranca. **[Rec]** §4.

## 4. Integración de funcionalidades pendientes

No se ha hecho ningún merge. Estado de GitHub (`gh pr list`, 2026-11-23):

| Funcionalidad | Rama / PR | Base | Depende de | Migraciones | Conflictos potenciales |
|---|---|---|---|---|---|
| Copia antes de migrar (en la app) | `fix/copia-antes-de-migrar` **#5** | `main` | — | — | `migrations.py`, `bootstrap.py` |
| Renombrar conversaciones | `feat/renombrar-conversaciones` **#8** | #5 | #5 | 0008 | `service.py`, `chat.js` |
| Selección de modelo por conversación (ADR-0023) | `feat/seleccion-modelo` **#9** | #8 | #8 | 0009 | `service.py`, gateway |
| Agentes personales CRUD + agentes de organización | `feat/agentes-persistentes` **#10** (incluye `feat/agentes-organizacion`, #18) | #9 | #9 | 0010, 0011 | `agents.py`, `chat.py` |
| Prompt Library integrada (ADR-0025) | `claude/prompt-library-module` **#11** | #10 | #10 | 0012 | frontend, rutas |
| Aislamiento estricto de conversaciones (triggers + acceso único) | `integration/security-conversation-isolation` (local) / `security/conversation-isolation` (remota) | `main` | — | 0008 | **`service.py`**, `migrations.py`, `state.js`, CHANGELOG (comparte 4 archivos con la cadena) |
| Dashboard como inicio | `feat/nexaro-dashboard-entry` | — | — | 0011 (choca) | **sustituida por #11** |
| Prompt Library standalone | `feature/prompt-library-mvp` **#2** (+ fix XSS **#7**) | `main` | — | — | **CONFLICTING**; duplicada por #11 |
| Coding agent / agent hub | `feature/real-coding-agent`, `feature/agent-hub-foundation`, **#6** | — | — | — | Ejecuta comandos: revisión de seguridad propia |
| App de escritorio Windows (Electron) | `claude/project-thread-17a30v` / `-3nd08p` | — | — | — | 7 468 líneas nuevas; producto aparte |

### Integración realizada (2026-11-23, con tu autorización: merges locales, sin push)

Rama local `nexaro-v1-full` en `C:\Users\pc\NEXARO-v1`: v1.0 → `main` (identidad de marca, #23) → #5 →
cadena #8–#11 → aislamiento de conversaciones con la migración renumerada a **0013**. Conflictos
resueltos: routers y documentación (aditivos), `service.py` (ids generados por el servidor + perfiles
de agente, modelo y título), migraciones (8–12 de la cadena, 13 la propiedad). Además:

- `main` estaba en rojo en CI: la identidad de marca puso colores `rgb()` fuera de `tokens.css`;
  pasan a `--shadow-overlay` y `--shadow-auth`.
- El inventario de rutas del aislamiento exigió probar las rutas nuevas: tests negativos en
  `tests/security/test_v1_route_isolation.py` (fuera de la organización y desde otra: 404).
- E2E intermitente (también en el PR #11 solo): carrera del test al navegar, corregida.
- **PR #24 descartado**: tercera migración `0008` y CRUD de agentes de organización sin uso en el
  chat, ya cubierto (y mejor) por #10.
- Resultado: 797 tests passed, E2E 40/40 estable, smoke con Ollama real 8/8, restauración 14/14,
  ensayo de la migración v7→v13 sobre una copia de los datos reales, despliegue en 8002.

### Orden recomendado (aplicado)

1. **#5** (copia antes de migrar) → `main`.
2. Cadena **#8 → #9 → #10 → #11**, en ese orden, cada una con su CI verde (son coherentes entre sí: 0008–0012).
3. **Aislamiento de conversaciones**: rebase sobre el resultado y **renumerar** su migración a
   `0013_conversation_ownership.sql` (SQLite y PostgreSQL) + entrada en `platform_migrations()`.
   Resolver `service.py` a mano conservando el acceso único por propietario. Es la rama más pequeña
   (1 migración) y la renumeración no afecta a ninguna base real: la del ThinkPad está en v6.
   *Alternativa* si prima la seguridad: integrarla primero como 0008 y renumerar la cadena (5 PRs).
4. Cerrar sin merge `feat/nexaro-dashboard-entry` y **#2**/**#7** (duplicadas por #11), después de
   comprobar que no queda nada propio (`git diff` mostró que dashboard-entry solo difiere en la
   numeración).
5. Coding agent (#6) y escritorio: fuera de v1; revisión aparte.

### Tests que necesita cada integración

- Toda la batería (`pytest`) + `tests/integration/test_upgrade_paths.py` (detecta huecos y duplicados
  de numeración: `test_migration_files_are_numbered_without_gaps_or_duplicates`).
- Cadena: los suyos propios (cada PR trae tests) + E2E jsdom.
- Aislamiento: `tests/security/test_conversation_isolation.py` (686 líneas en la rama).
- Antes de desplegar cualquiera: `scripts/backup_nexaro.ps1 -Reason pre-update` y
  `scripts/test_backup_restore.ps1` con la imagen nueva.

### Qué se ha implementado aquí y qué no

No se ha reimplementado nada de lo que ya está en PRs (selección de modelo, CRUD de agentes, Prompt
Library, aislamiento): duplicarlo crearía una tercera numeración de migraciones y más conflictos.
Esta rama solo añade migraciones **cero** (no cambia el esquema), así que no interfiere con ninguna.

## 5. Problemas encontrados y resolución

| # | Prioridad | Tipo | Problema | Resolución |
|---|---|---|---|---|
| 1 | CRÍTICO | C | NEXARO no arranca: puerto 8001 ocupado por `nexaro-prompt-library` | `NEXARO_PORT` configurable; **decisión tuya** (parar el otro contenedor o cambiar de puerto) |
| 2 | ALTO | C | Vault de Obsidian legible por cualquier usuario | Corregido (OBS-1) |
| 3 | ALTO | C | Sin copias de seguridad ni restauración en Windows | `scripts/*_nexaro.ps1`, prueba completa PASS |
| 4 | ALTO | C | Migraciones con la misma numeración en ramas distintas | Tests de rechazo seguro + plan §4 |
| 5 | ALTO | C | Despliegue desde un clon con cambios sin confirmar; 4 copias del repo | Documentado (DEPLOYMENT.md) |
| 6 | MEDIO | C | Sin cambio de contraseña | `POST /api/auth/password` + Perfil |
| 7 | MEDIO | C | DoS por notas grandes / Vault enorme | Corregido (OBS-2/3) |
| 8 | MEDIO | C | 5 tests rotos en Windows por codificación (y 1 bug real en `quality_eval.py`) | Corregido |
| 9 | MEDIO | C | Pestañas de Administración fuera de pantalla en móvil (sin scroll) | `overflow-x: auto` |
| 10 | MEDIO | C | Interfaz sin `Cache-Control`: JS/CSS antiguos tras actualizar | `no-cache` (revalidación) |
| 11 | MEDIO | C | Sin panel de estado (salud, recursos, copias, errores) | `/api/admin/status` + Operaciones |
| 12 | BAJO | C | Service worker solo en `localhost`, no en `127.0.0.1` (la URL documentada) | `window.isSecureContext` |
| 13 | BAJO | C | Selector de agente de 17 px de alto en móvil | 44 px en pantallas estrechas |
| 14 | BAJO | C | E2E del frontend no arranca en Windows: 8765 está en un rango reservado por Hyper-V (8751–8850) y el script seguía «pasando» sin servidor | `NEXARO_E2E_PORT` y fallo explícito si el servidor no arranca |
| 15 | BAJO | C | Manifest sin `id`, sin `apple-touch-icon` | Añadidos |
| 16 | BAJO | C | `ALLOWED_ORIGINS`/`COOKIE_SECURE` fijos en compose: imposible configurar HTTPS remoto sin editar el archivo | Variables con valores por defecto iguales |
| 17 | MEDIO | R | Sesiones de 7 días sin caducidad por inactividad | Recomendación |
| 18 | MEDIO | R | Copias sin cifrar | Recomendación: BitLocker |
| 19 | BAJO | R | CI solo en Linux | [Rec] job `windows-latest` con pytest |
| 20 | BAJO | R | `./frontend` montado desde el clon | [Rec] en despliegue permanente, quitar el bind mount y usar la imagen |
| 21 | BAJO | H | El MacBook podría tener una base con migraciones de otra rama | Comprobar `schema_migrations` antes de restaurar copias del Mac aquí |

## 6. Deuda técnica

- Tres stacks «NEXARO» distintos en el mismo equipo, con nombres de contenedor parecidos.
- `scripts/rebuild_backend.sh` depende de un archivo de copia concreto con hash fijo.
- Límites de intentos en memoria (aceptable con 1 réplica).
- PostgreSQL: DDL mantenido en paralelo pero la app no corre sobre él.
- Terraform AWS escrito y sin aplicar: mantenerlo cuesta; está aparcado.
- `search: false` se pasa a `dataTable` en varias vistas pero el componente no lo usa (inofensivo).

## 7. Tests que faltaban (añadidos)

| Archivo | Cubre |
|---|---|
| `tests/security/test_obsidian_access.py` (21) | Acceso al Vault por rol, rutas fuera del Vault, tamaño, tope de archivos, límite por usuario, configuración |
| `tests/security/test_password_change.py` (6) | Cambio de contraseña: origen, sesión, revocación, auditoría, límite, no afecta a otros |
| `tests/integration/test_upgrade_paths.py` (9) | Actualización v1…v6 → actual con datos; bases de otra rama rechazadas sin tocar |
| `tests/integration/test_ops_status.py` (8) | Panel de operaciones: solo admin, sin secretos, estado de copias |
| `tests/unit/test_backup_scripts.py` (29) | Helper de copias y garantías de los scripts PowerShell |
| `tests/unit/test_quality_eval.py` (+1) | Regresión del falso fallo de abstención RAG |
| `tests/security/test_frontend_policy.py` (+1) | `Cache-Control` de la interfaz |
| `tests/frontend/e2e.mjs` (+1) | Pestaña Operaciones |
| `scripts/smoke_isolated.ps1` | Imagen candidata contra el Ollama real con datos temporales (8/8 PASS) |

Resultado final: **665 passed, 0 failed, 3 skipped**, cobertura 91,70 %; E2E 36/36.

Faltan (pendiente): E2E con navegador real en CI (Chromium está en `browser.mjs`, no en CI),
pruebas de carga del streaming, test de recuperación de contraseña (no existe la función).
