# IMPLEMENTATION_STATUS — NEXARO Personal AI

Actualizado: 2026-11-22. Estados: `IMPLEMENTED` (implementado y verificado en esta auditoría),
`IMPLEMENTED_PARTIALLY`, `BROKEN`, `NOT_IMPLEMENTED`, `DOCUMENTED_ONLY`, `NOT_VERIFIED` (existe
código, pero no se ha podido ejecutar aquí). Un test con modelo simulado verifica el flujo de la
aplicación, **no** la integración con un modelo real.

## 1. Progreso del MVP

El MVP son los 20 pasos que definió el propietario. Cada paso cuenta una vez.

| # | Paso | Estado | Evidencia |
|---|---|---|---|
| 1 | Instalar o iniciar NEXARO | NOT_VERIFIED | `make up` y `compose.yaml` existen; Docker no disponible en la auditoría |
| 2 | Acceder a la aplicación | IMPLEMENTED | E2E jsdom 35 OK (`tests/frontend/run.sh`); la API sirve `frontend/` |
| 3 | Autenticarse | IMPLEMENTED | `tests/integration/test_auth_flow.py`, `tests/security/test_access_control.py` |
| 4 | Seleccionar un modelo | IMPLEMENTED | `GET /api/models` + campo `model` + selector del chat; `tests/unit/test_model_selection.py`, `tests/integration/test_model_selection.py` y E2E «modelo: la lista viene del proveedor…». Con Ollama real: NOT_VERIFIED (como el paso 6). Falta modelo por defecto por usuario y por agente |
| 5 | Crear una conversación | IMPLEMENTED | `test_chat.py`, `test_conversation_lifecycle.py` |
| 6 | Conversar con el modelo | NOT_VERIFIED | Flujo verificado con modelo simulado (`test_chat_stream.py`); Ollama real no disponible aquí |
| 7 | Crear un agente | IMPLEMENTED | `POST /api/agents/custom`, pantalla `#/agents`; `tests/integration/test_custom_agents.py` y E2E «agentes: crear uno personal…» |
| 8 | Configurar sus instrucciones | IMPLEMENTED | `instructions` delimitadas tras las reglas fijas; test «custom_agent_is_really_used_in_chat» comprueba el prompt enviado y que no pueden cerrar su delimitador |
| 9 | Configurar sus herramientas | IMPLEMENTED_PARTIALLY | `tools` ⊆ herramientas del agente base, comprobado en el servidor (test 403 sin «documents»); hoy solo existe la herramienta «documents», falta el registro de herramientas |
| 10 | Ejecutar el agente | IMPLEMENTED_PARTIALLY | Selector de agente en el chat (`test_agents.py`, E2E); un agente es un perfil de prompt, no un ejecutor con herramientas propias |
| 11 | Consultar el resultado | IMPLEMENTED | `messages.agent` (migración 7) y respuesta guardada; `test_agents.py` |
| 12 | Recuperar el historial | IMPLEMENTED | `GET /api/conversations/{id}`; E2E «al reabrir la conversación está el texto parcial» |
| 13 | Cargar un documento | IMPLEMENTED | Texto y PDF: `test_documents.py`, `test_documents_pdf.py` |
| 14 | Consultarlo mediante RAG | IMPLEMENTED_PARTIALLY | Recuperación real por fragmentos con BM25 y fuentes (`test_chat_documents.py`); no hay embeddings ni búsqueda vectorial |
| 15 | Crear una tarea | NOT_IMPLEMENTED | Tabla `tasks` sin API (migración 2) |
| 16 | Consultar su estado | NOT_IMPLEMENTED | Igual que 15 |
| 17 | Ver logs | IMPLEMENTED | `GET /api/admin/audit`, logs JSON con `request_id` (`tests/security/test_logging.py`) |
| 18 | Reiniciar la aplicación | NOT_VERIFIED | `make smoke` recrea los contenedores; no ejecutado aquí |
| 19 | Comprobar que los datos persisten | NOT_VERIFIED | Volumen `nexaro_data`; depende de 18 |
| 20 | Otro usuario no accede a los datos | IMPLEMENTED | `tests/security/test_tenant_isolation.py`, `test_access_control.py` |

**Cálculo**

```
Total pasos del MVP:               20
Implementados y verificados:       11   (2, 3, 4, 5, 7, 8, 11, 12, 13, 17, 20)
Implementados parcialmente:         3   (9, 10, 14)
No implementados:                   2   (15, 16)
No verificados:                     4   (1, 6, 18, 19)
Rotos:                              0

Progreso verificado = 11 / 20 = 55 %
```

Los parciales y los no verificados no suman. Los pasos 1, 6, 18 y 19 pasarían a verificados con
una ejecución de `make up && make model && make smoke` en el Mac o el ThinkPad.

## 2. Otras funcionalidades

| Funcionalidad | Estado | Evidencia |
|---|---|---|
| Streaming (SSE) | IMPLEMENTED | `test_chat_stream.py`, E2E |
| Cancelar respuesta («Detener») | IMPLEMENTED | E2E «botón Detener corta la respuesta» |
| Eliminar conversación | IMPLEMENTED | `DELETE /api/conversations/{id}`, `test_conversation_lifecycle.py` |
| Renombrar conversación | IMPLEMENTED | `PATCH /api/conversations/{id}`; `test_conversation_lifecycle.py` (propietario, 404 ajeno, origen, límites) y E2E «renombrar conversación» |
| Proveedor Ollama | NOT_VERIFIED | Cliente real en `packages/ai_gateway/providers/ollama`; probado con dobles |
| OpenAI / Gemini | NOT_IMPLEMENTED | No hay proveedor |
| Bedrock / SageMaker | IMPLEMENTED_PARTIALLY | Probados solo con dobles (ADR-0004) |
| Cortacircuitos y estado de modelos | IMPLEMENTED | `test_gateway_wiring.py`, `GET /api/admin/models` |
| Agentes predefinidos (7) | IMPLEMENTED | `GET /api/agents`, `test_agents.py` |
| Catálogo de 86 agentes | DOCUMENTED_ONLY | `docs/agents/catalogue.json` (`"status": "proposed_catalogue"`) |
| Agentes personales (CRUD, duplicar, activar) | IMPLEMENTED | `test_custom_agents.py` (12 tests, incluido aislamiento entre usuarios) |
| Agent Builder con IA | NOT_IMPLEMENTED | Solo creación manual |
| Orquestación multiagente | DOCUMENTED_ONLY | `docs/architecture/system-overview.md`; PR #3 tiene `POST /api/orchestrator/plan` fuera del monolito, no evaluado |
| Equipos de agentes | NOT_IMPLEMENTED | — |
| Registro de herramientas | IMPLEMENTED_PARTIALLY | Una herramienta (`documents`) con permiso por agente y usuario y auditoría `agent.tool` |
| Agente de código con herramientas (PR #3) | IMPLEMENTED_PARTIALLY | 9 tests OK; servicio aparte sin autenticación (AUDIT_REPORT SEC-01) |
| Biblioteca de prompts | IMPLEMENTED | Módulo de la plataforma (ADR-0025): `test_prompt_library.py` (17) y E2E del frontend; packs y workflows del PR #2 no portados |
| Memoria (usuario, agente, proyecto, equipo) | NOT_IMPLEMENTED | — |
| Documentos DOCX, CSV | NOT_IMPLEMENTED | Solo texto y PDF |
| Organizaciones, miembros, roles | IMPLEMENTED | `test_organizations.py` |
| Claves de API y `/api/v1/*` | IMPLEMENTED | `test_api_keys.py` |
| Finanzas (gastos) | IMPLEMENTED | `test_expenses.py` |
| Resumen de seguridad (admin) | IMPLEMENTED | `test_security_summary.py` |
| Panel y avisos | IMPLEMENTED | `test_dashboard.py` |
| PWA | IMPLEMENTED_PARTIALLY | `manifest.webmanifest`, `sw.js`; instalación no probada |
| Migraciones SQLite (1–10) | IMPLEMENTED | `test_startup_migration.py` |
| Copia verificada antes de migrar | IMPLEMENTED | `test_migrations.py`, `test_startup_backs_up_legacy_database_before_migrating` |
| PostgreSQL | IMPLEMENTED_PARTIALLY | DDL validado (6 tests con pgserver); la app no lo usa |
| Terraform AWS | NOT_VERIFIED | Escrito, no aplicado; aparcado por el propietario |
| CI en GitHub del linaje A | NOT_VERIFIED | Nunca se ha ejecutado sobre `backup/macbook` |
