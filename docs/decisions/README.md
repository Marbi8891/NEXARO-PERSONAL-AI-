# Decisiones de arquitectura (ADR)

Formato: id, estado, contexto, opciones, decisión, razón, trade-offs, consecuencias, fecha.
Una decisión aceptada no se cambia en silencio: se propone un *DECISION REVIEW* y se añade un ADR que la sustituye.

| ADR | Título | Estado |
|---|---|---|
| [0001](0001-modular-monolith.md) | Monolito modular | Aceptada |
| [0002](0002-python-layout-and-dependencies.md) | Estructura Python y dependencias | Aceptada |
| [0003](0003-auth-sessions.md) | Autenticación por sesiones con cookie | Aceptada |
| [0004](0004-ai-gateway.md) | AI Gateway con política, coste y proveedores | Aceptada |
| [0005](0005-migrations-multitenancy-postgres.md) | Migraciones, multitenencia y PostgreSQL | Aceptada |
| [0006](0006-aws-infrastructure.md) | Infraestructura AWS como Terraform (no aplicada) | Propuesta implementada |
| [0007](0007-frontend-es-modules.md) | Frontend con ES Modules nativos bajo CSP estricta | Aceptada |
| [0008](0008-design-system.md) | Sistema de diseño con tokens, tema claro/oscuro y módulos solo si existen | Aceptada |
| [0009](0009-api-keys-developer-module.md) | Claves de API por organización como primer módulo real (Developer) | Aceptada |
| [0010](0010-security-module-from-audit.md) | Módulo Security como vista derivada de la auditoría | Aceptada |
| [0011](0011-api-key-scopes-and-read-api.md) | Permisos por clave de API, lectura de conversaciones y límite por clave | Aceptada |
| [0012](0012-documents-lexical-search.md) | Documentos por organización con búsqueda léxica (sin embeddings por ahora) | Aceptada |
| [0013](0013-finance-expenses.md) | Módulo Finance, primer alcance: gastos de la organización | Aceptada |
| [0014](0014-streaming-and-ollama-tuning.md) | Streaming real y parámetros de Ollama configurables | Aceptada |
| [0015](0015-sqlite-wal.md) | SQLite en modo WAL | Aceptada |
| [0016](0016-gateway-circuit-breaker-and-model-status.md) | Cortacircuitos del gateway y estado de modelos | Aceptada |
| [0017](0017-documents-in-chat.md) | Documentos en el chat (opt-in) | Aceptada |
