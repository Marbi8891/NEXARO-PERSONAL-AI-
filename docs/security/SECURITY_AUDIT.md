# Auditoría de seguridad de NEXARO Personal AI

Fecha: 2026-11-09 · Rama `feature/nexaro-design-system` · Método: lectura del código, `pip-audit`,
Bandit y pruebas automatizadas. Solo contra el entorno local propio. No es una auditoría formal ni una
certificación.

## 1. Arquitectura detectada

Navegador → `127.0.0.1:8001` → backend FastAPI (uid 10001, red externa `ollama-local_default`) →
Ollama (otro stack). SQLite en el volumen `nexaro_data`. Fuera del repositorio y **no auditados**:
Ollama, Open WebUI y Supabase (comparten Docker).

## 2. Superficie de ataque

| Zona | Detalle |
|---|---|
| Público | `POST /api/auth/register` (cerrado por defecto), `POST /api/auth/login`, `GET /api/health`, `/api/health/live` |
| Sesión | chat y streaming, conversaciones, panel, avisos |
| Administración | usuarios, auditoría, seguridad, uso (rol `admin`) |
| Por organización | miembros, claves de API, documentos, gastos (permiso por rol; no ser miembro = 404) |
| Clave de API | `/api/v1/chat`, `/api/v1/conversations*` (scopes `chat:write`, `conversations:read`) |
| Entradas de texto libre | chat, documentos (hasta 200 000 caracteres), gastos |
| Salidas | solo hacia Ollama (`OLLAMA_BASE_URL`). No hay URLs aportadas por el usuario: SSRF no aplica hoy |
| No existen | agentes, herramientas, subida de archivos binarios, ejecución de comandos |

## 3. Hallazgos

Estado a fecha de este documento. Detalle de correcciones en `REMEDIATION_REPORT.md`.

| ID | Sev. | Hallazgo | Evidencia | Estado |
|---|---|---|---|---|
| SEC-01 | HIGH | Chat sin límite por usuario ni de concurrencia (agotamiento de CPU del modelo) | `routers/chat.py`; el gateway no limitaba | Corregido |
| SEC-02 | MEDIUM | Todas las peticiones llegan con la IP de la pasarela de Docker; el límite de login por IP bloqueaba a todos | log de Docker: `172.19.0.1` en cada petición | Mitigado (umbral por IP configurable) |
| SEC-03 | MEDIUM | Los delimitadores `<fragmento>` del contexto de documentos podían cerrarse desde un documento | `documents.py` `build_context` | Corregido |
| SEC-04 | MEDIUM | Contenedor sin `cap_drop`, `no-new-privileges`, `read_only`, límites ni rotación de logs; imagen sin digest | `compose.yaml`, `Dockerfile` | Corregido en el repo; **sin verificar en Docker** |
| SEC-05 | MEDIUM | Sin límite global de tamaño de cuerpo | `main.py` | Corregido |
| SEC-06 | MEDIUM | Sin logs estructurados ni `request_id` | solo tabla `audit_events` | Corregido |
| SEC-07 | LOW | Faltaban `Permissions-Policy`, COOP, CORP, HSTS y `no-store` en `/api` | cabeceras | Corregido |
| SEC-08 | LOW | Swagger/OpenAPI abiertos en el contenedor (`NEXARO_ENV=development` por defecto) | `main.py` | Corregido (`API_DOCS=false` en compose) |
| SEC-09 | LOW | Dependencias transitivas sin fijar ni hashes; CI sin Bandit ni SBOM | `requirements/base.txt` | Parcial: CI con Bandit y SBOM; **sin lockfile con hashes** |
| SEC-10 | LOW | Copias de la base sin política de retención | `backups/` | Corregido (`scripts/prune_backups.sh`, manual) |
| SEC-11 | LOW | `/api/health` público sondea a Ollama en cada llamada | `routers/health.py` | Mitigado (`HEALTH_CACHE_SECONDS`) |
| SEC-12 | INFO | SQLite **no está cifrado** en reposo | — | Aceptado; ver `SECURITY_BASELINE.md` |
| SEC-13 | INFO | 12 SQL con f-string marcados por Bandit (B608) | Bandit | Verificado: solo huecos fijos; test que lo vigila |
| VERIFY-01 | — | ¿Escuchan Ollama (11434) u Open WebUI (8080) fuera de localhost? | UNKNOWN | **Pendiente: lo comprueba el propietario** |

## 4. Lo que ya estaba bien (comprobado)

Cookies `HttpOnly` + `SameSite=Strict` (+ `Secure` en producción), comprobación de `Origin` en toda
operación que modifica datos, CSP sin `unsafe-inline` y ningún `innerHTML` (lo impone
`tests/security/test_frontend_policy.py`), contraseñas con scrypt, sesiones con hash en base de datos,
claves de API guardadas como hash SHA-256, aislamiento por organización con RLS en PostgreSQL,
auditoría append-only con triggers, puerto publicado solo en `127.0.0.1`, `pip-audit` sin
vulnerabilidades conocidas en `requirements/base.txt`, sin secretos en el repositorio (búsqueda por
patrones; el CI ejecuta Gitleaks).

## 5. Herramientas

| Herramienta | Resultado |
|---|---|
| `pip-audit` (`requirements/base.txt`) | Sin vulnerabilidades conocidas |
| Bandit | 0 hallazgos medium/high sin justificar; 3 `assert` y 1 falso positivo (B105) de severidad baja |
| Gitleaks, Trivy, Grype, Semgrep | **No ejecutados aquí.** Gitleaks corre en el CI; Trivy/Grype/Semgrep pendientes |
| `npm audit` | No aplica: el frontend no tiene `package.json` ni dependencias |
