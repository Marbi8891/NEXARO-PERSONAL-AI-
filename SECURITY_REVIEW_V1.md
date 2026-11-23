# Revisión de seguridad — NEXARO v1.0 (despliegue personal)

Fecha: 2026-11-23. Rama: `claude/nexaro-v1-consolidation-921fe0` (desde `main` 4022b0e).
Alcance: código de `main`, `compose.yaml`, `Dockerfile`, scripts y frontend. Las ramas no
integradas se analizan en AUDIT_V1.md §4 (no se han revisado línea a línea).

Clasificación: **Confirmado** (reproducido con un test o con el código), **Riesgo potencial**
(posible según el diseño, sin explotación demostrada), **Hipótesis** (sin verificar),
**Recomendación**.

## Resumen

| ID | Severidad | Hallazgo | Estado |
|---|---|---|---|
| OBS-1 | **ALTA** | Cualquier usuario autenticado leía el Vault de Obsidian completo del propietario | Corregido + tests |
| OBS-2 | MEDIA | Sin límite de tamaño de nota: lectura completa en memoria al abrir, buscar y listar (DoS) | Corregido + tests |
| OBS-3 | MEDIA | Recorrido completo del Vault en cada petición, incluidos `.git`/`node_modules` | Corregido + tests |
| OBS-4 | BAJA | Endpoints de Obsidian sin límite de peticiones | Corregido + tests |
| OBS-5 | BAJA | La ruta del Vault se leía de `os.environ` saltándose `Settings` | Corregido + test |
| AUTH-1 | MEDIA | No existía ninguna forma de cambiar la contraseña (ni usuario, ni admin, ni CLI) | Corregido (autoservicio) + tests |
| WEB-1 | BAJA | Interfaz servida sin `Cache-Control`: tras actualizar, el navegador seguía usando JS/CSS antiguos | Corregido + test |
| DB-1 | MEDIA (integración) | Ramas pendientes con la misma numeración de migraciones (dos `0008` distintas) | Mitigado: el arranque se niega sin tocar la base (tests); hay que renumerar antes de integrar |
| R-1 | MEDIA | Sesiones de 7 días sin caducidad por inactividad | Riesgo aceptado (personal); recomendación |
| R-2 | BAJA | Límites de intentos en memoria (se reinician con el proceso) | Riesgo aceptado (1 réplica) |
| R-3 | BAJA | Detrás de Docker Desktop / Tailscale Serve todas las IPs son la misma | Mitigado por el límite por cuenta |
| R-4 | MEDIA | Copias de seguridad sin cifrar en disco | Recomendación: BitLocker / destino cifrado |
| R-5 | BAJA | `./frontend` montado desde el clon: cambiar de rama cambia la interfaz en caliente | Recomendación (DEPLOYMENT.md) |
| R-6 | INFO | Ollama externo (`C:\Docker\ollama-local`) corre como root, sin `read_only` | Fuera de este repositorio; recomendación |

No se han encontrado secretos en el repositorio (búsqueda de patrones de claves AWS, GitHub,
OpenAI, claves privadas, `nxr_…`, `tskey-…` y contraseñas literales fuera de `tests/`). gitleaks no
está instalado en el equipo: se ejecuta en CI (`.github/workflows/ci.yml`, historial completo).

## Hallazgos corregidos

### OBS-1 — Vault de Obsidian legible por cualquier usuario (ALTA, confirmado)

**Evidencia:** `apps/api/nexaro_api/routers/obsidian.py` (main) solo exigía `CurrentUser`. El Vault
es un directorio del host montado en `/knowledge/obsidian`, sin propietario por usuario ni por
organización. Con el registro abierto y una cuenta aprobada, cualquiera leía todas las notas
personales del propietario (`GET /api/obsidian/note/...`, `/search`).

**Corrección:** acceso solo para administradores de la plataforma y cuentas de
`OBSIDIAN_ALLOWED_EMAILS` (sin distinguir mayúsculas). Denegación → 403 + evento de auditoría
`obsidian.access/denied`. No hay aislamiento entre usuarios ni organizaciones posible sobre un único
directorio: por eso es un recurso **del propietario**, no compartido. Si en el futuro se quiere
compartir, cada usuario necesitaría su propio Vault (ruta por usuario).

**Tests:** `tests/security/test_obsidian_access.py` (anónimo 401, usuario normal 403 + auditoría en
los 4 endpoints, admin y lista permitida 200).

### OBS-2 / OBS-3 — Agotamiento de recursos (MEDIA, confirmado por lectura de código)

`read_note`, `search` y `_metadata` hacían `read_text()` del archivo entero; `search` y `status`
recorrían el Vault completo con `rglob` en cada petición, entrando en `.git` y `node_modules` antes
de filtrar. Un archivo de cientos de MB o un Vault con miles de archivos bloqueaba un hilo y la
memoria del contenedor (1 GiB).

**Corrección (`packages/nexaro_core/obsidian/vault.py`):** lectura acotada (`OBSIDIAN_MAX_NOTE_BYTES`,
1 MiB; abrir una nota mayor → 413; búsqueda y listado la saltan sin leerla), recorrido con
`os.walk(followlinks=False)` podando directorios excluidos y ocultos, y tope de notas por recorrido
(`OBSIDIAN_MAX_FILES`, 5000; `status` indica `truncated`).

### OBS-4 / OBS-5 / rutas

- Límite de 60 peticiones/minuto por usuario (`OBSIDIAN_REQUESTS_PER_MINUTE`), independiente por cuenta.
- La ruta sale de `Settings` (única fuente de configuración); sin configuración no se recurre al entorno.
- Rutas: se rechazan absolutas (incluidas `C:...` y UNC), `..` que salga de la raíz tras `resolve()`,
  directorios ocultos/excluidos, extensiones distintas de `.md` y enlaces simbólicos que apunten
  fuera. Tests con `../`, `%2e%2e/`, `..%2f`, `..%5c` y `.obsidian/`.
- El montaje Docker sigue siendo `:ro`.

### AUTH-1 — Sin cambio de contraseña (MEDIA, confirmado)

No había endpoint, ni opción en Administración, ni en `bootstrap_admin` (solo crea o promociona).
Una contraseña comprometida no se podía cambiar sin editar la base a mano.

**Corrección:** `POST /api/auth/password` (Perfil → Contraseña): exige sesión, `Origin` permitido y
la contraseña actual; mínimo 12 caracteres y distinta de la actual; mantiene la sesión que hace el
cambio y **revoca todas las demás**; auditoría `auth.password_change` sin contraseñas; 5 fallos →
429 durante la ventana (también para la contraseña correcta), para que una sesión robada no sirva
para adivinarla. Tests: `tests/security/test_password_change.py`.

**Pendiente:** recuperación de contraseña olvidada. Para un despliegue personal sin correo saliente
se recomienda una opción `--reset-password` en `bootstrap_admin` (CLI dentro del contenedor). No
implementada.

### WEB-1 — Caché de la interfaz

Las respuestas fuera de `/api/` llevan ahora `Cache-Control: no-cache` (revalidación con ETag → 304).
Sin esto, tras desplegar una corrección de seguridad en el frontend el navegador podía seguir
ejecutando el JS antiguo durante horas (verificado en el navegador durante esta revisión).

## Verificado sin cambios (con tests existentes o nuevos)

| Área | Resultado | Evidencia |
|---|---|---|
| Login, logout, sesiones | Token de 256 bits, solo se guarda SHA-256; cookie `HttpOnly`, `SameSite=Strict`, `Secure` configurable (obligatoria con `NEXARO_ENV=production`); caducidad 7 días; logout revoca en BD | `tests/integration/test_auth_flow.py` |
| CSRF | `Origin` obligatorio en todas las escrituras + `SameSite=Strict` | `test_state_changing_routes_reject_missing_or_foreign_origin` |
| Fuerza bruta | 5 intentos/cuenta y umbral por IP, auditoría de bloqueo una sola vez, hash ficticio contra enumeración por tiempo | `tests/security/test_access_control.py` |
| Registro y administradores | Registro cerrado por defecto, cuentas pendientes de aprobación, último admin protegido, admin no se crea por API | `test_access_control.py`, `test_bootstrap_admin.py` |
| Conversaciones | Leer/escribir/borrar/streaming de una conversación ajena → 404; la propiedad se comprueba antes de llamar al modelo; el historial de otro usuario nunca llega al modelo | `test_access_control.py`, `test_conversation_lifecycle.py`, `test_llm_security.py`, `test_restricted_topics.py` |
| Documentos | Aislados por organización (claves foráneas compuestas + membresía); roles lectores/escritores | `test_documents.py`, `test_tenant_isolation.py` |
| Agentes y herramientas | Documentos solo si el agente tiene la herramienta y el usuario el permiso; auditoría `agent.tool` | `test_agents.py` |
| Claves de API | `secrets.token_urlsafe(32)`, hash SHA-256, prefijo visible, caducidad, revocación, scopes (`chat:write`, `conversations:read`), límite por clave/minuto, mueren con la membresía del creador, nunca en logs ni auditoría | `test_api_keys.py` |
| Endpoints de administración | 401/403 + auditoría de la denegación; nuevo `/api/admin/status` solo admin | `test_access_control.py`, `test_ops_status.py` |
| Streaming | Mismos límites y concurrencia que el chat; el lease se libera si el cliente corta | `test_abuse_limits.py` |
| SQL | Todo parametrizado; los fragmentos interpolados son constantes (test que lo vigila) | `test_sql_injection.py` |
| Logs | JSON con `request_id`, sin cuerpos ni consultas, claves sensibles redactadas | `tests/security/test_logging.py` |
| Cabeceras | CSP estricta, `nosniff`, `DENY`, `no-referrer`, COOP/CORP, HSTS con `COOKIE_SECURE`, `no-store` en `/api/` | `test_abuse_limits.py`, `test_frontend_policy.py` |
| Cuerpo de petición | 2 MiB máximo antes de parsear | `test_oversized_body_is_rejected_before_parsing` |

### Rate limiting por superficie

| Superficie | Límite |
|---|---|
| Login | 5 fallos/cuenta/15 min; `LOGIN_IP_MAX_ATTEMPTS` por IP (50 en compose por la NAT de Docker Desktop) |
| Cambio de contraseña | 5 fallos/cuenta/15 min |
| Chat y streaming | 30/min por usuario; 2 generaciones simultáneas en total y por usuario |
| Borrar conversación | Comparte el tope de concurrencia del chat |
| API pública (`/api/v1`) | 60/min por clave; fallos de autenticación limitados por IP |
| Obsidian | 60/min por usuario |
| Documentos | Tope de documentos por organización y tamaño de cuerpo; **sin** límite por minuto (riesgo bajo: requiere rol de escritor) |
| Administración | Sin límite por minuto (requiere rol admin) |

## Docker

| Control | backend | ollama (perfil incluido) |
|---|---|---|
| Usuario no root | uid 10001 | imagen oficial (root) — ver R-6 |
| Raíz de solo lectura | sí (`read_only`, `/tmp` tmpfs 64 MiB) | no (escribe modelos) |
| `cap_drop: ALL` + `no-new-privileges` | sí | sí |
| Límites | 1 GiB RAM, 2 CPU, 200 procesos | 6 GiB, 512 procesos |
| Healthcheck | `HEALTHCHECK` de la imagen (`/api/health/live`) | `ollama list` |
| Puertos | solo `127.0.0.1:8001` | ninguno |
| Logs | json-file 10 MiB × 5 (rotación) | 10 MiB × 3 |
| Volúmenes | `nexaro_data` (único escribible); Vault `:ro`; `./frontend` `:ro` | `ollama_models` |
| Imagen | `python:3.12-slim` fijada por digest; `apt-get upgrade` en build | `OLLAMA_IMAGE` (fíjala por digest) |
| Secretos | ninguno en compose; no hay secretos de aplicación (sesiones aleatorias en BD) | — |

## Recomendaciones (no aplicadas)

1. Activar BitLocker en el ThinkPad (las copias y el volumen Docker contienen conversaciones).
2. Al activar Tailscale: `COOKIE_SECURE=true` y solo orígenes `https://` + loopback (REMOTE_ACCESS.md).
3. Caducidad por inactividad de sesión (p. ej. 24 h) además de los 7 días absolutos.
4. `--reset-password` en `bootstrap_admin` para recuperar una cuenta sin correo saliente.
5. Antes de integrar `feature/real-coding-agent` / `claude/coding-agent-hardening`: revisión de
   seguridad específica (ejecuta comandos); debe quedar desactivado por defecto (lo hace PR #6).
6. Renumerar migraciones al integrar ramas (AUDIT_V1.md §4) — nunca editar una migración ya aplicada.
