# Changelog

## [Sin publicar] — rama `refactor/nexaro-platform`

### Añadido
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

### Cambiado
- La app pasa a `create_app()` (factory); el comando de admin es `python -m nexaro_api.bootstrap_admin`.
- Prompt del asistente generado desde proveedor y modelo configurados (sin modelo fijo en código).
- Índice `idx_messages_conversation_id`.

### Eliminado
- `backend/` (sustituido por la nueva estructura).

## Fase 1 — `4453ef1`
- Autenticación por cuentas con migración atómica; registro cerrado; sin admins automáticos.
