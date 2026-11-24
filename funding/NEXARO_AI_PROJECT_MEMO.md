# Memoria técnica — NEXARO AI

Repositorio público: https://github.com/Marbi8891/NEXARO-PERSONAL-AI-

Documentación revisada: README, IMPLEMENTATION_STATUS, ARCHITECTURE y AUDIT_REPORT.

Arquitectura descrita: monolito modular Python/FastAPI; frontend HTML/CSS/ES Modules; SQLite operativo; AI Gateway con políticas, fallback, circuit breakers y usage tracking; proveedores Ollama y adaptadores Bedrock/SageMaker con pruebas simuladas; organizaciones, roles, API keys, auditoría y documentos/BM25.

Estados: IMPLEMENTED (documentado y probado en auditoría): auth/sesiones, auditoría, aislamiento multi-tenant, chat/conversaciones, API keys, documentos, operaciones/backups, frontend/PWA y agentes tipo perfil. PARTIAL: tools registry limitado, agentes descritos como perfiles de prompt, RAG BM25 sin embeddings. NOT IMPLEMENTED: API de tareas, embeddings/vector search, proveedores OpenAI/Gemini. NOT VERIFIED: modelo Ollama real en entorno actual, despliegue Docker completo, AWS. Terraform está documentado/aparcado, no desplegado.

La auditoría del repositorio afirma 576 tests pass, 10 skipped, cobertura 92,23%, Ruff/mypy y comprobaciones adicionales; volver a ejecutar en commit actual antes de usar como evidencia externa.

Innovación a validar: IA local-first, gobernanza de herramientas, auditoría, control de proveedores y privacidad. Hace falta benchmark, pruebas de seguridad, comparativa de mercado, pilotos y evidencia de novedad. No afirmar patentabilidad ni innovación disruptiva.
