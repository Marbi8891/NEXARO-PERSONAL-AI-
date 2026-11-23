# Checklist de release — NEXARO Personal AI v1.0

Fecha: 2026-11-23 · Rama `claude/nexaro-v1-consolidation-921fe0` (sin commit) · Equipo: ThinkPad,
Windows 11, Docker 29.9.3, Compose 5.7.0, Python 3.12.10.

Estados: **PASS** (verificado ahora, con evidencia) · **FAIL** · **BLOCKED** (necesita una decisión o
acción tuya) · **NOT TESTED**.

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 1 | Tests (unit, integración, seguridad, API, BD, migraciones) | PASS | `pytest`: **665 passed, 0 failed, 3 skipped** (symlinks no disponibles en Windows; sin terraform; sin copia real en `backups/`), cobertura 91,70 % (umbral 80 %). Línea base antes de los cambios: 585 passed / 5 failed |
| 2 | Frontend E2E (jsdom contra la API real) | PASS | `NEXARO_E2E_PORT=8899 bash tests/frontend/run.sh` → 36/36 (con la CPU libre; con la evaluación de IA en paralelo hubo un timeout de 5 s en «organizaciones», no reproducido) |
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
| 12b | Copia diaria programada | PASS (provisional) | Tarea «NEXARO Backup diario» (usuario actual, sin elevación) a las 03:30 con `StartWhenAvailable`, retención 14. Ejecutada a mano el 2026-11-23 15:45: código 0, `nexaro-20261123-154529-daily` «COPIA VÁLIDA», panel actualizado. **Provisional:** apunta al script del worktree; tras integrar en `main`, vuelve a ejecutar `register_backup_task.ps1 -Register` desde el clon definitivo (sustituye la tarea) |
| 13 | NEXARO desplegado y en marcha en el ThinkPad | PASS (provisional) | 2026-11-23 15:43: `nexaro-backend` healthy en **127.0.0.1:8002** (`NEXARO_PORT=8002`, el 8001 sigue en `nexaro-prompt-library`); migración v6→v7 aplicada; datos intactos (1 usuario, 1 conversación, 2 mensajes); `integrity_check` ok; `/api/health` `model: ready`. **Provisional:** se desplegó desde el worktree de esta rama sin confirmar (`C:\Users\pc\NEXARO-PERSONAL-AI\.claude\worktrees\nexaro-v1-consolidation-921fe0`, con su `.env`): el bind mount `./frontend` apunta ahí. Tras integrar en `main`, vuelve a desplegar desde el clon definitivo antes de borrar el worktree |
| 14 | Docker build | PASS | `docker build` de esta rama: usuario 10001, HEALTHCHECK, 282 MB |
| 15 | Healthchecks y endurecimiento | PASS | `test_container_hardening.py`, `test_compose_stack.py`; healthcheck «healthy» en las pruebas con contenedor |
| 16 | Conexión a Ollama y respuesta real de IA | PASS | `scripts/smoke_isolated.ps1` con la imagen final y el Ollama real: `/api/health` `model: ready`; respuesta real de `qwen2.5:3b` en 1,7 s; panel de operaciones OK (8/8) |
| 17 | Persistencia tras reiniciar el contenedor | PASS | Mismo smoke: `docker restart` → healthy y la conversación sigue (2 mensajes); restauración en volumen nuevo también conserva datos |
| 18 | Recuperación tras reiniciar Windows | NOT TESTED | No se ha reiniciado el equipo. Configuración: `restart: unless-stopped` + Docker Desktop al iniciar sesión (DEPLOYMENT.md paso 7) |
| 19 | Login / logout / sesiones / cambio de contraseña | PASS | `test_auth_flow.py`, `test_access_control.py`, `test_password_change.py` |
| 20 | Chat y streaming | PASS | Tests de integración + E2E (Detener, persistencia de lo parcial) |
| 21 | Agentes (7 estáticos, herramientas por permiso) | PASS | `test_agents.py`, E2E |
| 22 | Agentes personales CRUD, selección de modelo, Prompt Library | NOT TESTED | No están en `main`: PRs #9, #10, #11 (AUDIT_V1.md §4) |
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

**PERSONAL BETA READY** — no PERSONAL V1 READY todavía.

- El **código** de esta rama cumple lo exigible a una v1 personal: tests, lint y tipos en verde; sin
  hallazgos de seguridad críticos ni altos abiertos; migraciones y actualización desde versiones
  anteriores probadas; copias y restauración probadas de extremo a extremo; imagen construida y
  probada contra el Ollama real.
- La **instalación** ya está en marcha en 127.0.0.1:8002 con los datos reales migrados y dos copias
  verificadas y copia diaria programada, pero aún no es una v1 estable: el backend y la tarea de copia
  corren desde un worktree con cambios sin confirmar (#12b y #13 provisionales) y el acceso remoto no
  está activado (#26).
- No es **PRODUCTION READY** (ni pretende serlo): un solo equipo, sin alta disponibilidad, límites en
  memoria, sin recuperación de contraseña por correo.

Para pasar a **PERSONAL V1 READY**: revisar y confirmar estos cambios en `main` → volver a desplegar
desde el clon definitivo con el mismo `.env` (`NEXARO_PORT=8002`) y volver a registrar la tarea de
copia desde ese clon → (opcional para v1, necesario para el móvil) Tailscale → marcar #12b, #13, #18
y #26 como PASS.
