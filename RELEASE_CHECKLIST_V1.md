# Checklist de release — NEXARO Personal AI v1.0

Fecha: 2026-11-23 · Rama `claude/nexaro-v1-consolidation-921fe0` (sin commit) · Equipo: ThinkPad,
Windows 11, Docker 29.9.3, Compose 5.7.0, Python 3.12.10.

Estados: **PASS** (verificado ahora, con evidencia) · **FAIL** · **BLOCKED** (necesita una decisión o
acción tuya) · **NOT TESTED**.

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 1 | Tests (unit, integración, seguridad, API, BD, migraciones) | PASS | Versión completa (`nexaro-v1-full`): **797 passed, 0 failed, 3 skipped** (symlinks en Windows, terraform, copia real en `backups/`). Solo v1 antes de integrar: 665 passed. Línea base inicial: 585 passed / 5 failed |
| 2 | Frontend E2E (jsdom contra la API real) | PASS | 40/40 en 6 de 6 ejecuciones seguidas. El check de agentes fallaba de forma intermitente también en el PR #11 por separado (3 de 4): era una carrera del propio test, corregida con `enterChat()` |
| 3 | Ruff, formato, mypy | PASS | `ruff check`: sin errores; `ruff format --check`: 205 archivos formateados; `mypy packages apps products`: sin errores (78 archivos) |
| 4 | Dependencias (pip-audit) | PASS | `pip-audit -r requirements/base.txt -r requirements/aws.txt`: «No known vulnerabilities found» |
| 5 | Secretos | PASS (local) / NOT TESTED (gitleaks) | Búsqueda de patrones sin hallazgos; gitleaks no está instalado aquí (corre en CI con el historial completo) |
| 6 | Seguridad: hallazgos críticos/altos abiertos | PASS | OBS-1 (ALTA) corregido; ninguno abierto (SECURITY_REVIEW_V1.md) |
| 7 | Aislamiento entre usuarios (conversaciones, documentos, Obsidian, API keys, streaming) | PASS | Tests negativos en `tests/security/` y `tests/integration/` |
| 8 | Migraciones y actualización desde versiones anteriores | PASS | `test_upgrade_paths.py`: v1…v6 → v7 con datos, 9/9 |
| 9 | Bases de otras ramas no se corrompen | PASS | Rechazo sin tocar la base (2 tests) |
| 10 | Copia de seguridad | PASS | `backup_nexaro.ps1` en marcha y parado (entorno temporal) |
| 11 | Restauración (arranque, login, conversaciones, documentos) | PASS | `test_backup_restore.ps1`: 14/14 (BACKUP_RESTORE.md) |
| 12a | Primera copia de los datos reales | PASS | `C:\Users\pc\NEXARO-Backups\nexaro-20261123-154227-pre-update` (esquema v6, antes de actualizar; backend parado, volumen `:ro`) y `nexaro-20261123-154314-manual` (v7, backend en marcha). Ambas «COPIA VÁLIDA». La primera destapó un bug de la copia en frío (base WAL sin `-shm` en un volumen de solo lectura) que la prueba con datos sintéticos no cubría: corregido + test de regresión |
| 12b | Copia diaria programada | PASS | Tarea «NEXARO Backup diario» a las 03:30 apuntando a `C:\Users\pc\NEXARO-v1\scripts\backup_nexaro.ps1`; ejecución de prueba: código 0, `nexaro-20261123-171517-daily` (esquema v13) |
| 13 | NEXARO desplegado y en marcha en el ThinkPad | PASS | 2026-11-23 17:15, versión completa desde `C:\Users\pc\NEXARO-v1` (rama local `nexaro-v1-full`, `.env` con `NEXARO_PORT=8002`): healthy en 127.0.0.1:8002; migraciones 8–13 aplicadas sobre tus datos (antes ensayadas sobre una copia restaurada); 2 conversaciones y 4 mensajes intactos; integridad ok; copia `pre-update` verificada antes y copia automática del PR #5 dentro del volumen |
| 14 | Docker build | PASS | `docker build` de esta rama: usuario 10001, HEALTHCHECK, 282 MB |
| 15 | Healthchecks y endurecimiento | PASS | `test_container_hardening.py`, `test_compose_stack.py`; healthcheck «healthy» en las pruebas con contenedor |
| 16 | Conexión a Ollama y respuesta real de IA | PASS | `scripts/smoke_isolated.ps1` con la imagen final y el Ollama real: `/api/health` `model: ready`; respuesta real de `qwen2.5:3b` en 1,7 s; panel de operaciones OK (8/8) |
| 17 | Persistencia tras reiniciar el contenedor | PASS | Mismo smoke: `docker restart` → healthy y la conversación sigue (2 mensajes); restauración en volumen nuevo también conserva datos |
| 18 | Recuperación tras reiniciar Windows | NOT TESTED | No se ha reiniciado el equipo. Configuración: `restart: unless-stopped` + Docker Desktop al iniciar sesión (DEPLOYMENT.md paso 7) |
| 19 | Login / logout / sesiones / cambio de contraseña | PASS | `test_auth_flow.py`, `test_access_control.py`, `test_password_change.py` |
| 20 | Chat y streaming | PASS | Tests de integración + E2E (Detener, persistencia de lo parcial) |
| 21 | Agentes (7 estáticos, herramientas por permiso) | PASS | `test_agents.py`, E2E |
| 22 | Renombrar, modelo por conversación, agentes propios y de organización, Prompt Library | PASS | Integrados (PRs #5, #8–#11) y aislamiento de conversaciones (migración 0013). Tests de cada PR + `tests/security/test_v1_route_isolation.py`. PR #24 descartado: tercera migración 0008 y funcionalidad ya cubierta por #10 |
| 23 | Documentos y RAG (aislamiento, citas, abstención) | PASS | `test_documents*.py`, `test_chat_documents.py`; evaluación del modelo en AI_EVALUATION.md |
| 24 | API pública (`/api/v1`, claves, scopes, límites) | PASS | `test_api_keys.py` |
| 25 | PWA y móvil | PASS | Revisión en 375×812 en navegador real: sin desbordamiento horizontal en 8 pantallas; pestañas desplazables; controles de 44 px; manifest e icono. Instalación real en Android: NOT TESTED (requiere HTTPS → Tailscale) |
| 26 | Acceso remoto privado | **BLOCKED** | Preparado (REMOTE_ACCESS.md, `remote_access.ps1`); Tailscale no instalado: requiere tu autorización |
| 27 | Logs estructurados, sin secretos, con `request_id`, rotación | PASS | `tests/security/test_logging.py`; json-file 10 MiB × 5 |
| 28 | Monitorización | PASS | `/api/admin/status` + Operaciones (`test_ops_status.py`, E2E, revisión en navegador) |
| 29 | Evaluación de la IA reproducible | PASS | `qwen2.5:3b`: 34/42 (81 %) con código ejecutado en sandbox; latencia mediana 30,7 s; 6,2 tok/s; 0 errores. Debilidades reales documentadas (tutor 1/4, una alucinación de redes, revela su prompt sin el filtro) — AI_EVALUATION.md |
| 30 | Documentación | PASS | README, DEPLOYMENT, SECURITY, ARCHITECTURE, docs/OPERATIONS, BACKUP_RESTORE, REMOTE_ACCESS, SECURITY_REVIEW_V1, AUDIT_V1, AI_EVALUATION, RELEASE_NOTES_V1, este documento |
| 31 | CI en GitHub | NOT TESTED | No se ha hecho push (instrucción del encargo). La configuración de CI no cambia |

## Veredicto

**PERSONAL V1 READY** para uso local en el ThinkPad, con dos salvedades.

- Código: tests, lint, tipos y E2E en verde; sin hallazgos de seguridad críticos ni altos abiertos;
  migraciones v1→v13 probadas (también sobre una copia de tus datos); copias y restauración probadas
  de extremo a extremo; imagen probada contra el Ollama real.
- Instalación: en marcha desde una ruta estable, datos migrados, copias verificadas y copia diaria
  programada y probada.
- Salvedad 1: el acceso remoto (#26) sigue pendiente de instalar Tailscale; hasta entonces NEXARO solo
  se usa desde el propio ThinkPad.
- Salvedad 2: la rama `nexaro-v1-full` solo existe en este equipo (no se ha hecho push). Si el disco
  falla, el código integrado se pierde (tus datos están en las copias). Recomendado: subirla y abrir un PR.
- No es **PRODUCTION READY** (ni pretende serlo): un solo equipo, sin alta disponibilidad, límites en
  memoria, sin recuperación de contraseña por correo. #18 (reinicio de Windows) sigue NOT TESTED.
