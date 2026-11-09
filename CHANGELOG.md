# Changelog

## [Sin publicar] — rama `refactor/nexaro-platform`

### Añadido
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
- La app pasa a `create_app()` (factory); el comando de admin es `python -m nexaro_api.bootstrap_admin`.
- Prompt del asistente generado desde proveedor y modelo configurados (sin modelo fijo en código).
- Índice `idx_messages_conversation_id`.

### Eliminado
- `backend/` (sustituido por la nueva estructura).

## Fase 1 — `4453ef1`
- Autenticación por cuentas con migración atómica; registro cerrado; sin admins automáticos.
- Developer ampliado (F16): permisos por clave (`chat:write`, `conversations:read`), `GET /api/v1/conversations[/{id}]` limitado a conversaciones creadas con claves de la organización, límite de 60 peticiones/minuto por clave (429 + `Retry-After`), migración 4 (SQLite y PostgreSQL) y ADR-0011.
- Documentos (F17): subida de texto por organización, búsqueda léxica BM25 y preguntas con fuentes (`/api/organizations/{id}/documents`), vista `#/documents`, sin migración nueva y ADR-0012.
- Finanzas, gastos (F18): registro con importes exactos en céntimos, resumen mensual y gráfico de 6 meses, filtros, edición, exportación CSV segura para hojas de cálculo (`/api/organizations/{id}/expenses`), vista `#/finance` solo para propietarios y administradores, migración 5 (SQLite y PostgreSQL con RLS), permisos `expenses:*` y ADR-0013.
