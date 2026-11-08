# Changelog

## [Sin publicar] — rama `refactor/nexaro-platform`

### Añadido
- Estructura de monolito modular: `apps/api`, `packages/{nexaro_core,ai_gateway}`, `products/personal_ai`.
- Auditoría append-only, `/api/admin/audit`, endpoint `/api/health/live`.
- Tests unit/integration/security (96) con cobertura ~94 %; ruff y mypy limpios.
- CI (GitHub Actions), Dockerfile con healthcheck, `.env.example`, ADR-0001..0003.

- AI Gateway (`Gateway`, `GatewayPolicy`, `UsageStore`), proveedores Bedrock y SageMaker, `GET /api/admin/usage`, ADR-0004.

### Cambiado
- La app pasa a `create_app()` (factory); el comando de admin es `python -m nexaro_api.bootstrap_admin`.
- Prompt del asistente generado desde proveedor y modelo configurados (sin modelo fijo en código).
- Índice `idx_messages_conversation_id`.

### Eliminado
- `backend/` (sustituido por la nueva estructura).

## Fase 1 — `4453ef1`
- Autenticación por cuentas con migración atómica; registro cerrado; sin admins automáticos.
