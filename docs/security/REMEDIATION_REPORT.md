# Informe de remediación

Cada fila enlaza el hallazgo (`SECURITY_AUDIT.md`) con el cambio y la prueba que lo demuestra.
Commits: `164a191` (lotes 1-2), `991d903` (3), `788c993` (4), `b04eb03` (5).

| ID | Cambio | Dónde | Prueba |
|---|---|---|---|
| SEC-01 | `acquire_generation`: 429 por ritmo (30/min) y por usuario, 503 si el modelo está saturado; concesiones que caducan solas; se libera al terminar, fallar o cancelar | `deps.py`, `routers/chat.py`, `api_keys.py`, `documents.py`, `nexaro_core/security/concurrency.py` | `test_abuse_limits.py` |
| SEC-02 | Limitador de IP aparte con `LOGIN_IP_MAX_ATTEMPTS` (compose: 50). Por defecto igual que antes | `routers/auth.py`, `settings.py`, `compose.yaml` | `test_abuse_limits.py::test_one_ip_failing_logins...`; los tests antiguos pasan sin cambios |
| SEC-03 | `build_context` neutraliza `<fragmento`/`</fragmento` y aplana el título | `products/personal_ai/documents.py` | `test_llm_security.py` |
| SEC-04 | `read_only`, `tmpfs /tmp`, `cap_drop: ALL`, `no-new-privileges`, `pids_limit`, `mem_limit 1g`, `cpus 2`, rotación `10m × 5`, imagen por digest | `compose.yaml`, `Dockerfile` | `test_container_hardening.py` (estático) |
| SEC-05 | `BodyLimitMiddleware` (413 por `Content-Length` y por conteo en chunked), `MAX_BODY_BYTES` | `apps/api/nexaro_api/limits.py` | `test_abuse_limits.py` |
| SEC-06 | `request_id` (acepta uno válido o genera uno), línea de acceso JSON, eventos de seguridad en el log, error interno con `request_id` y sin detalles | `nexaro_core/observability`, `request_context.py`, `audit/service.py` | `test_logging.py` |
| SEC-07 | `Permissions-Policy`, COOP, CORP, HSTS (solo con cookies seguras), `Cache-Control: no-store` en `/api` | `main.py` | `test_abuse_limits.py` |
| SEC-08 | `API_DOCS` (por defecto solo en desarrollo; nunca en producción); compose lo cierra | `main.py`, `settings.py` | `test_abuse_limits.py` |
| SEC-09 | Bandit y SBOM CycloneDX en el CI | `.github/workflows/ci.yml` | SBOM generado en local (4 componentes directos) |
| SEC-10 | `scripts/prune_backups.sh`: simulación por defecto, conserva las N últimas y nunca toca `nexaro-pre-auth-migration-*` | `scripts/` | `test_prune_backups.py` |
| SEC-11 | `HEALTH_CACHE_SECONDS` (compose: 5) | `routers/health.py` | `test_abuse_limits.py` |
| SEC-13 | Marcados con `nosec B608` + test que impide nuevos huecos variables | `test_sql_injection.py` | 5 tests |

## Riesgos que quedan

| Riesgo | Por qué | Qué haría falta |
|---|---|---|
| Ollama/Open WebUI expuestos (VERIFY-01) | No se puede comprobar desde el repo | Que el propietario ejecute `docker ps` y `lsof` (ver `SECURITY_BASELINE.md`) |
| El endurecimiento del contenedor no se ha ejecutado en Docker | El entorno de desarrollo no tiene Docker | `scripts/rebuild_backend.sh --yes`; si el arranque falla por `read_only`, ver `INCIDENT_RESPONSE.md` |
| Sin lockfile con hashes | Se evaluó, pero mezclar plataformas (macOS/Linux, Python 3.10/3.12) sin probarlo en la imagen es más riesgo que beneficio hoy | `pip-compile --generate-hashes` dentro de la imagen |
| Trivy, Grype, Semgrep sin ejecutar | No disponibles en este entorno | Añadir Trivy al CI sobre la imagen |
| SQLite sin cifrar; copias sin cifrar | Requiere decidir clave y gestión | FileVault del Mac (no verificado) o cifrado de las copias con `age` |
| Límites en memoria | Se reinician con el proceso y no se comparten entre réplicas (ADR-0003) | Almacén compartido si hay varias réplicas |
| Rendimiento antes/después | No medido: sin acceso a Ollama desde el entorno de desarrollo | `scripts/ollama_benchmark.py` tras el despliegue |
| Registro de acciones de agentes | No hay agentes | Diseñarlo con la primera herramienta |
