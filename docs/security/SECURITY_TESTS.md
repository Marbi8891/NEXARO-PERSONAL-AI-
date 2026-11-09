# Pruebas de seguridad

Se ejecutan solo contra la aplicación de pruebas (BD temporal, proveedor de IA falso). Resultado a fecha
2026-11-09: **380 pytest pasados** (con PostgreSQL real), 32 comprobaciones de frontend, `ruff` y `mypy` limpios.

```
source .venv/bin/activate
NEXARO_REQUIRE_POSTGRES=1 pytest -q
bandit -q -r apps packages products --severity-level medium --confidence-level medium
pip-audit -r requirements/base.txt
bash tests/frontend/run.sh
```

| Área pedida | Fichero | Qué demuestra |
|---|---|---|
| Acceso no autorizado | `tests/security/test_access_control.py` | 401 sin sesión, 403 sin rol, 404 sin pertenencia |
| Acceso cruzado entre usuarios | `test_access_control.py`, `test_tenant_isolation.py`, `test_llm_security.py` | ni la API ni el modelo ven datos ajenos |
| Inyección SQL | `test_sql_injection.py` | cargas hostiles en filtros, ids y búsquedas se tratan como datos; huecos de f-string fijos |
| XSS | `test_frontend_policy.py` + E2E | sin `innerHTML`; el HTML del modelo se ve como texto; CSP sin `unsafe-inline` |
| CORS / Origin | `test_access_control.py`, `test_abuse_limits.py` | sin `Origin` válido: 403 |
| Rate limiting | `test_access_control.py`, `test_abuse_limits.py` | login, claves de API, chat por usuario |
| Validación de entrada | `test_abuse_limits.py` y las suites de cada módulo | 413 por tamaño, 422 por tipo |
| Manipulación de archivos | — | **No aplica**: no hay subida de ficheros (solo texto plano en documentos) |
| SSRF | — | **No aplica**: no hay URLs de usuario |
| Exposición de secretos | `test_logging.py`, `test_container_hardening.py` | ni contraseñas ni contenido en logs; sin secretos en compose |
| Acceso a Ollama | — | **No verificable aquí** (VERIFY-01) |
| Prompt injection | `test_llm_security.py` | delimitadores no forjables; rol de sistema único; contexto como dato |
| Abuso de herramientas | — | **No aplica**: no hay herramientas ni agentes |
| Persistencia y recuperación tras reinicio | `test_startup_migration.py`, `scripts/rebuild_backend.sh` (conteos antes/después) | migraciones, rollback y base intacta |
| Streaming y cancelación | `test_chat_stream.py` | el streaming sigue funcionando con los límites; cancelar conserva lo generado y libera el hueco |
| Contenedor | `test_container_hardening.py` | análisis estático de `compose.yaml` y `Dockerfile`; **no sustituye arrancarlo** |

## Límites

Estas pruebas demuestran los controles descritos en las rutas probadas. No demuestran ausencia de
vulnerabilidades. Quedan sin probar: arranque real del contenedor endurecido, exposición de Ollama y
Open WebUI, y comportamiento bajo carga real.
