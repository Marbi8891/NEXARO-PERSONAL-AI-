# Changelog

## [Sin publicar] — rama `refactor/nexaro-platform`

### Añadido
- Agentes de organización (ADR-0024): `/api/organizations/{org}/agents` con los mismos campos que los personales; los gestionan propietario y administrador (`agents:manage`), los usan propietario, administrador y miembro (`agents:run`). Aparecen en el selector del chat como «Nombre · Organización» y dejan de estar disponibles al salir de la organización. Migración 11: columnas nuevas en la tabla `agents`, sin borrar datos.
- Agentes personales (Fase 5): `/api/agents/custom` para crear, ver, editar, duplicar (nace desactivado), activar/desactivar y borrar; solo el propietario (404 para el resto). Parten de un agente predefinido, heredan sus reglas y como máximo sus herramientas; instrucciones propias delimitadas en el prompt y modelo por defecto opcional. Se eligen en el chat como cualquier agente. Pantalla «Agentes» (`#/agents`) y migración 10 (`user_agents`, SQLite y PostgreSQL).
- Selección de modelo (Fase 3): `GET /api/models` descubre los modelos instalados en Ollama; campo `model` en `/api/chat`, `/api/chat/stream` y `/api/v1/chat` (nombre instalado o `auto`); la conversación recuerda su modelo (migración 9, SQLite y PostgreSQL). Un modelo elegido se usa sin respaldo y, si no está instalado, el error es claro y no se guarda el turno. Selector «Modelo» en el chat que muestra el modelo activo.
- Renombrar conversaciones: `PATCH /api/conversations/{id}` (`{title}`, 1–120 caracteres, solo el propietario, auditoría `conversation.rename` sin el título), botón ✎ en el historial con diálogo propio, y migración 8 (`conversations.title`, SQLite y PostgreSQL).
- Copia automática y verificada de la base SQLite antes de aplicar migraciones pendientes sobre datos existentes (`<nombre>.pre-migration-v<N>-<fecha>.db`); sin copia válida no se migra.
- Auditoría de la Fase 0 (2026-11-22): `AUDIT_REPORT.md`, `IMPLEMENTATION_STATUS.md` (progreso verificado del MVP: 8 de 20) y `ROADMAP.md`. Versión canónica consolidada: `backup/macbook` fusionada con la documentación de `main`.
- Agentes (F27, ADR-0022): `general`, `developer`, `security`, `research`, `productivity`, `data` y `tutor` (el modo tutor pasa a ser un agente). `GET /api/agents`; campo `agent` en `/api/chat`, `/api/chat/stream` y `/api/v1/chat` (`mode` sigue valiendo). Cada agente añade reglas al prompt general y declara sus herramientas: los documentos exigen que el agente tenga la herramienta y que el usuario tenga `documents:read`; el tutor no la tiene. Usos y denegaciones quedan en la auditoría (`agent.tool`, sin contenido). Migración 7: `messages.agent` registra qué agente dio cada respuesta. Selector «Agente» en el chat, que recuerda la elección (también la del antiguo selector de modo) y retoma el agente al reabrir una conversación.
- Docker y Ollama (F26, ADR-0021): servicio `ollama` opcional con el perfil `ollama` (sin puertos, volumen `ollama_models`, healthcheck `ollama list`, endurecido) y el backend esperando a que esté sano solo con el perfil activo. `make up` (preflight de Docker, Compose >= 2.20, modo y red, y `--wait`), `make model` y `make model-check` (`scripts/ollama_model.py`, idempotente, con timeouts y reintentos) y `make smoke` (`scripts/stack.sh`: servicios, salud, modelo, generación real y persistencia tras recrear los contenedores).
- `/api/health` comprueba también que el modelo configurado está instalado (503 «Modelo de IA no disponible»), con la misma llamada a Ollama.
- Modo tutor de programación: `mode: "tutor"` en `/api/chat`, `/api/chat/stream` y `/api/v1/chat`, y un selector «Modo» en el chat. Guía con pistas y no da la solución hasta que hay un intento propio (ADR-0020).
- Evaluación de calidad del modelo: `scripts/quality_eval.py`, 31 casos en `scripts/eval/cases.json` y `make eval` para comparar modelos con el prompt de producción. Puntuación determinista y ejecución del código generado en un contenedor sin red.
- Bloqueo de preguntas sobre el modelo de IA y la infraestructura interna: filtro determinista en el backend (chat, streaming, `/api/v1/chat` y `documents/ask`) que responde con un texto fijo sin consultar al modelo. El prompt de sistema ya no incluye el proveedor, el modelo ni el stack (ADR-0019).
- Documentos PDF con texto: `POST /api/organizations/{id}/documents/pdf` (cuerpo binario) y subida desde Documentos; extracción con `pypdf==7.0.0`, sin OCR, con límites de tamaño, páginas y texto (ADR-0018).
- Documentos en el chat (Fase 4): interruptor «Consultar mis documentos» (opt-in por mensaje) que añade al modelo los mejores fragmentos BM25 de la organización elegida y muestra las fuentes; exige `documents:read` (ADR-0017).
- Gateway (Fase 2): cortacircuitos por proveedor (`AI_BREAKER_THRESHOLD`, `AI_BREAKER_COOLDOWN_SECONDS`) que falla en el acto si Ollama está caído y lo vuelve a probar tras el enfriamiento, `GET /api/admin/models` (salud, modelo configurado, instalado o no, modelos instalados) y pestaña «Modelos» en Administración (ADR-0016).
- Estabilización (Fase 1): `DELETE /api/conversations/{id}` (con botón en el historial), imagen Docker con el frontend incluido, SQLite en modo WAL con espera de bloqueos (ADR-0015), `/api/chat` con el mismo historial acotado y tope de salida que el streaming, y un turno sin respuesta ya no deja mensajes huérfanos.
- Endurecimiento de seguridad (F20): límites de ritmo y concurrencia del modelo, cuerpo máximo, umbral de login por IP configurable, cabeceras adicionales, Swagger cerrable, delimitadores de documentos a prueba de inyección, logs JSON con `request_id`, contenedor con privilegios mínimos e imagen por digest, tests de inyección SQL, Bandit y SBOM en CI, `scripts/prune_backups.sh` y `docs/security/`.
- Rendimiento de inferencia (F19): streaming real Ollama→cliente (`POST /api/chat/stream`, SSE), cliente HTTP único, `keep_alive`/`num_ctx`/`num_thread` configurables, tope de salida adaptativo, historial acotado, métricas de TTFT/carga/tokens por segundo (migración 6, panel de Administración), botón «Detener», Markdown seguro en el chat, `scripts/ollama_benchmark.py`, ADR-0014.
- Estructura de monolito modular: `apps/api`, `packages/{nexaro_core,ai_gateway}`, `products/personal_ai`.
- Auditoría append-only, `/api/admin/audit`, endpoint `/api/health/live`.
- Tests unit/integration/security (96) con cobertura ~94 %; ruff y mypy limpios.
- CI (GitHub Actions), Dockerfile con healthcheck, `.env.example`, ADR-0001..0003.

- AI Gateway (`Gateway`, `GatewayPolicy`, `UsageStore`), proveedores Bedrock y SageMaker, `GET /api/admin/usage`, ADR-0004.

- Migraciones versionadas con checksum (`schema_migrations`), modelo multiorganización, API de organizaciones y miembros, DDL de PostgreSQL con RLS validado con servidor real, ADR-0005.

- Terraform para AWS por entorno (dev/staging/prod), ADR-0006, costes y job de CI con `terraform validate`; sin aplicar.

- Frontend modular (ES Modules, CSS por capas, router por hash, PWA): acceso, registro, chat con historial, administración (usuarios, auditoría, uso) y organizaciones; CSP estricta; prueba E2E con jsdom; ADR-0007.

- Identidad visual y sistema de diseño (F10): tokens claro/oscuro, Inter autoalojada, símbolo y logotipo, iconos PWA, selector de tema, test de contraste WCAG AA, ADR-0008, `docs/design-system.md`.
- Componentes y marco (F11): cabecera con menú de usuario y perfil, tabla de datos (búsqueda, filtros, orden, paginación), estados cargando/error/vacío, avisos, confirmación modal, formularios consistentes y cajón de navegación móvil.
- Prueba en Chromium real (`BROWSER=1 tests/frontend/run.sh`) con capturas de referencia.
- Panel y avisos (F12): `GET /api/dashboard` (actividad del usuario y, solo para administradores, cuentas, uso del modelo y contadores de seguridad) y `GET /api/notifications` (avisos derivados del estado real, sin persistencia ni datos personales); vista `#/dashboard`, gráfico de barras SVG accesible y campana en la cabecera. Sin cifras inventadas: lo que no hay se muestra como 0 o vacío.
- Módulo Developer (F13): claves de API por organización (hash SHA-256, secreto mostrado una vez, caducidad opcional, revocación, auditoría), `POST /api/v1/chat` con `Authorization: Bearer`, uso por clave (`GET /api/organizations/{id}/usage`), migración 3 (SQLite y PostgreSQL), vista `#/developer` y ADR-0009.
- Documentación final (F14): `API.md` completa, sección Frontend en `ARCHITECTURE.md`, guía de instalación y copias en `DEPLOYMENT.md`, pruebas de frontend en `DEVELOPMENT.md`, `SECURITY.md` actualizado e `docs/informe-calidad-profesional.md`.
- Módulo Security (F15): `GET /api/admin/security` y vista `#/security` (solo administradores) con accesos fallidos, denegaciones, bloqueos, IP de origen e incidencias, calculados desde la auditoría existente (sin tablas nuevas); ADR-0010.

### Cambiado
- Seguridad de dependencias: `fastapi` 0.120.4 → 0.160.0 y `starlette` fijado en 1.10.0 (pip-audit encontraba 10 avisos en starlette 0.49.3: PYSEC-2026-161, -248, -249, -2280, -2281).
- Imagen Docker: `apt-get upgrade` de los parches de Debian sobre la base fijada (Trivy marcaba zlib1g, CVE-2026-85091, HIGH con arreglo).
- CI: gitleaks se ejecuta con el binario oficial verificado por checksum sobre todo el historial; `gitleaks-action` fallaba en PR que incluyen el commit raíz.
- CI: `aquasecurity/trivy-action` fijado por commit a v0.36.0; la etiqueta `0.28.0` ya no existe y los jobs `docker` y `terraform-scan` no podían arrancar.
- La app pasa a `create_app()` (factory); el comando de admin es `python -m nexaro_api.bootstrap_admin`.
- Prompt del asistente generado desde proveedor y modelo configurados (sin modelo fijo en código).
- Índice `idx_messages_conversation_id`.

### Corregido
- Instalación desde cero: `/data` se crea en la imagen con propietario 10001. Antes, un volumen nuevo era de root y el backend no podía crear la base. Los volúmenes con datos no cambian (ADR-0021).

### Eliminado
- `backend/` (sustituido por la nueva estructura).

## Fase 1 — `4453ef1`
- Autenticación por cuentas con migración atómica; registro cerrado; sin admins automáticos.
- Developer ampliado (F16): permisos por clave (`chat:write`, `conversations:read`), `GET /api/v1/conversations[/{id}]` limitado a conversaciones creadas con claves de la organización, límite de 60 peticiones/minuto por clave (429 + `Retry-After`), migración 4 (SQLite y PostgreSQL) y ADR-0011.
- Documentos (F17): subida de texto por organización, búsqueda léxica BM25 y preguntas con fuentes (`/api/organizations/{id}/documents`), vista `#/documents`, sin migración nueva y ADR-0012.
- Finanzas, gastos (F18): registro con importes exactos en céntimos, resumen mensual y gráfico de 6 meses, filtros, edición, exportación CSV segura para hojas de cálculo (`/api/organizations/{id}/expenses`), vista `#/finance` solo para propietarios y administradores, migración 5 (SQLite y PostgreSQL con RLS), permisos `expenses:*` y ADR-0013.
