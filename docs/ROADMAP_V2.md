# NEXARO Roadmap v2

Fecha: 2026-11-24
Base: `main` (revisión documental y de archivos accesibles desde GitHub)
Estado: propuesta de trabajo; no implica que las tareas estén implementadas.

## Objetivo

Evolucionar NEXARO hacia una plataforma personal/local-first de IA con agentes y automatización controlada, manteniendo la arquitectura modular actual, el control de datos, los permisos explícitos y la compatibilidad con Windows.

## Principios de desarrollo

- No reescribir el monolito modular ni migrar el frontend a React sin una decisión justificada.
- Mantener SQLite como backend de datos por defecto hasta que una necesidad real justifique PostgreSQL.
- Las funciones deben aparecer como disponibles solo si tienen API, UI y pruebas funcionales.
- Los agentes no pueden elevar permisos ni ejecutar herramientas que no tengan autorizadas.
- Las acciones que escriben, borran, publican, envían datos o afectan al sistema requieren aprobación explícita.
- Local-first por defecto; los datos no se envían a proveedores cloud sin configuración y autorización.
- Cada cambio debe incluir tests y documentación cuando afecte a comportamiento, seguridad, configuración o despliegue.
- No desplegar, crear recursos cloud ni tocar datos reales sin autorización.

## Estado de partida

La documentación del repositorio describe autenticación y sesiones, auditoría, organizaciones, claves API, AI Gateway, chat con Ollama, agentes especializados, documentos con búsqueda BM25, finanzas, panel de operaciones, PWA, backups y restauración.

La revisión accesible de los archivos de `main` confirma una arquitectura de monolito modular, frontend HTML/CSS/ES Modules, controles de seguridad, CI con análisis estático, tests, auditoría de dependencias, SBOM y escaneo de imagen Docker.

**Pendiente de verificación de ejecución:** no se ha ejecutado el CI, los tests ni Docker desde este análisis. Además, `AUDIT_V1.md` describe una consolidación local fechada el 23-11-2026 y menciona ramas/PRs y un worktree; esos detalles deben contrastarse con el estado remoto actual antes de tomarlos como estado de `main`.

## Prioridades

### P0 — Establecer una línea base reproducible

**P0.1 — Reconciliar Git y documentación**
- Comparar `main`, PRs abiertos/cerrados, ramas activas y archivos del audit anterior.
- Identificar funcionalidades documentadas pero no presentes en `main`.
- Comprobar numeración y checksum de migraciones en todas las ramas candidatas.
- Resultado: informe de diferencias y decisión de qué integrar, cerrar o archivar.

**P0.2 — Calidad y CI multiplataforma**
- Mantener el job Linux actual como gate.
- Añadir job Windows para tests que no requieran Docker y documentar los tests condicionados.
- Añadir E2E frontend con Chromium en CI, si el tiempo y estabilidad son aceptables.
- Hacer que tests de scripts detecten correctamente herramientas ausentes; evitar skips silenciosos que oculten regresiones.
- Gate: lint, format, mypy, tests, cobertura, frontend E2E, security y build/healthcheck.

**P0.3 — Seguridad y release gate**
- Revisión de permisos en todas las rutas nuevas y existentes.
- Tests negativos de ownership, multitenancy, Origin/CSRF, scopes, límites y logs.
- Verificar que secretos y datos personales no aparezcan en logs, fixtures, artifacts o capturas.
- Revisar dependencias y actualizar solo con tests y changelog.
- Crear checklist de release y política de rollback/backups.

### P1 — Agent Runtime seguro y persistente

**P1.1 — Contrato de agentes**
- Definir schema de agente: identidad, descripción, modelo, prompt, herramientas permitidas, permisos, límites, timeout y política de aprobación.
- Versionar configuración de agentes y registrar cambios.
- Separar planner/orchestrator de la ejecución de herramientas.
- No permitir que un agente modifique su propio set de permisos.

**P1.2 — Orquestación**
- Implementar un coordinador que pueda seleccionar agentes y dividir tareas en subtareas.
- Mensajes entre agentes mediante schemas Pydantic con IDs, tipo, estado, payload validado y trazabilidad.
- Compartir solo el contexto mínimo necesario; evitar copiar el historial completo entre agentes.
- Prevenir ciclos de delegación, loops y runaway mediante profundidad máxima, presupuesto de pasos, timeout y límites de tokens/coste.
- El usuario debe poder inspeccionar plan, agentes seleccionados, progreso, resultados y errores sin exponer chain-of-thought.

**P1.3 — Task system durable**
- API de tareas: crear, consultar, cancelar, reintentar y listar.
- Estados: queued, running, waiting_approval, succeeded, failed, cancelled, expired.
- Persistencia de estado y eventos; recuperación segura tras reinicio.
- Idempotencia para acciones repetibles.
- Backoff limitado y política de dead-letter/error terminal.
- Inicialmente ejecutar worker dentro del monolito; no introducir Redis/Celery hasta que una necesidad medida lo justifique.

**P1.4 — Human approval**
- Cola de aprobaciones con acción, alcance, destino, argumentos resumidos, expiración y huella de la acción.
- Aprobación vinculada al usuario, tarea y payload exacto; cambios de payload invalidan la aprobación.
- Acciones de lectura de bajo riesgo pueden tener políticas automáticas; escritura, borrado, publicación, comunicación externa y comandos requieren aprobación.
- Auditoría de solicitud, aprobación, rechazo, ejecución y resultado.

### P2 — Contexto, memoria y conocimiento

**P2.1 — RAG híbrido**
- Conservar BM25 como baseline.
- Añadir embeddings como opción, con proveedor local primero.
- Recuperación híbrida, reranking opcional y citas de fuentes.
- Separar indexación de consulta y soportar reindexación incremental.
- Aislamiento estricto por usuario/organización y ACL por documento.
- Evaluación con dataset de preguntas y respuestas de referencia; medir relevancia, citas y latencia.

**P2.2 — Memoria controlada**
- Memoria por usuario y proyecto, con tipos: preferencia, hecho, objetivo, decisión, resumen y temporal.
- Propuesta de memoria generada por IA, revisión humana y confirmación antes de persistir.
- Edición, caducidad, eliminación y procedencia visible.
- Evitar guardar secretos, categorías sensibles o datos no necesarios.
- Recuperar solo memoria pertinente para cada tarea; trazabilidad de qué elementos se utilizaron.

**P2.3 — Context manager**
- Presupuesto de contexto por modelo.
- Resumen de conversación configurable y verificable.
- Selección de documentos/memorias por relevancia.
- Evitar duplicados y prompt injection de documentos mediante delimitación y política de confianza.

### P3 — AI Gateway y proveedores

- Unificar políticas de proveedor, modelo, privacidad, presupuesto, timeout y límites.
- Panel de latencia, tokens, costes estimados, errores, circuit breaker y disponibilidad.
- Costes de cloud calculados con tarifas versionadas; mostrar que son estimaciones.
- Política de fallback: no cambiar silenciosamente de modelo cuando una conversación fija modelo.
- Configuración de proveedores desde administración con secretos fuera de la BD/logs.
- Pruebas con proveedores simulados y un smoke-test opcional que nunca se ejecute automáticamente con credenciales reales.
- Evaluación comparativa de modelos con casos deterministas y resultados guardados localmente.

### P4 — Experiencia de usuario y frontend

- Dashboard centrado en tareas recientes, estado de agentes, aprobaciones y salud de los servicios.
- Chat con panel de ejecución: plan resumido, subtareas, herramientas, progreso, errores y resultado.
- Historial de tareas separado del historial de conversaciones.
- Accesibilidad WCAG: teclado, focus, contraste, lectores de pantalla, tamaño táctil y estados.
- Diseño responsive validado en 360–390 px y escritorio.
- Mejoras progresivas; mantener ES Modules y sistema de diseño actual.
- Estados vacíos, errores, carga, cancelación y recuperación consistentes.

### P5 — Operaciones y distribución

- Diagnóstico exportable sin secretos ni datos personales.
- Backups programables, verificación de integridad, retención y restore drill.
- Política de actualizaciones: versión, changelog, migraciones, backup previo y rollback.
- Health/readiness más granular (DB, proveedor, modelo, espacio, backup).
- Documentación de instalación Windows, Docker y uso local.
- Opción de empaquetado desktop solo tras estabilizar API y UI.
- No activar AWS/Terraform ni acceso remoto público sin autorización explícita.

## Backlog inicial de ejecución

| ID | Tarea | Prioridad | Dependencias | Criterio de aceptación |
|---|---|---:|---|---|
| NX-001 | Verificar estado remoto de main, PRs y ramas respecto al AUDIT_V1 | P0 | — | Informe de diferencias con evidencia |
| NX-002 | Ejecutar baseline CI/test suite y registrar resultados | P0 | NX-001 | Resultado reproducible; bugs separados de skips |
| NX-003 | Añadir CI Windows | P0 | NX-002 | Job estable; tests no aplicables identificados |
| NX-004 | E2E Chromium en CI | P0 | NX-002 | Smoke UI en Chromium; artifacts sanitizados |
| NX-005 | Auditoría de rutas y permisos | P0 | NX-001 | Matriz endpoint→permiso y tests negativos |
| NX-006 | Diseño de contrato Agent Runtime | P1 | NX-005 | Schemas, ADR y threat model aprobados |
| NX-007 | Persistencia de tareas y estados | P1 | NX-006 | CRUD, cancelación, reinicio y tests |
| NX-008 | Cola de aprobación con payload inmutable | P1 | NX-007 | Aprobación/rechazo/expiración auditados |
| NX-009 | Orquestador de agentes MVP | P1 | NX-006–008 | Una tarea multiagente limitada, reproducible y trazable |
| NX-010 | Métricas y trazas de ejecución | P1 | NX-007 | Vista/API de estados y duración; sin chain-of-thought |
| NX-011 | RAG híbrido opcional | P2 | NX-005 | BM25 + embeddings, ACL y evaluación |
| NX-012 | Memoria explícita con revisión humana | P2 | NX-011 | Proponer, editar, confirmar, eliminar y auditar |
| NX-013 | Context manager | P2 | NX-011–012 | Contexto acotado y selección explicable |
| NX-014 | AI Gateway dashboard y políticas | P3 | NX-002 | Métricas, presupuestos y rutas visibles |
| NX-015 | UX del Agent Workspace | P4 | NX-009–010 | Progreso, approvals, errores y resultados |
| NX-016 | Release/backup/restore drills | P5 | NX-002 | Checklist automatizable y restore probado |

## Primera iteración

No empezar con una implementación multiagente grande.

1. NX-001: reconciliar el estado real de Git.
2. NX-002: establecer baseline.
3. NX-005: revisar seguridad y permisos.
4. NX-006: escribir ADR y schemas para Agent Runtime.
5. Implementar un primer flujo vertical: una tarea, un agente, una herramienta permitida, aprobación si hay escritura, persistencia, cancelación y auditoría.
6. Expandir a delegación multiagente solo cuando el flujo vertical pase todos los gates.

## Definition of Done

Una tarea se considera terminada cuando:
- El cambio tiene alcance pequeño y revisión de diff.
- Tests unitarios/integración y tests de seguridad aplicables pasan.
- Lint, format y typecheck pasan.
- CI verde.
- No rompe migraciones ni datos existentes.
- Documentación y changelog actualizados.
- Los permisos y logs revisados.
- No se ha desplegado ni afectado datos reales sin aprobación.

## Registro de decisiones

Las decisiones que cambien arquitectura, datos, seguridad, permisos, proveedores o despliegue deben documentarse en ADR. Las funcionalidades experimentales deben quedar detrás de configuración y no presentarse como producción-ready.
