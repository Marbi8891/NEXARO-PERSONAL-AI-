# ROADMAP — NEXARO Personal AI

Priorizado según AUDIT_REPORT.md (2026-11-22). P0 > P1 > P2; las P3 esperan. Se trabaja en PR
pequeños sobre la versión canónica (linaje `backup/macbook`), sin cambiar de framework.

## Top 10

| # | P | Tarea | Necesita al propietario |
|---|---|---|---|
| 1 | P0 | Consolidar la versión canónica en `main` (fusión de `backup/macbook` + documentación de `main`) y pasar el CI completo en GitHub por primera vez | Sí: aprobar y fusionar el PR |
| 2 | P0 | Verificar Docker + Ollama real: `make up`, `make model`, `make smoke` (pasos 1, 6, 18, 19 del MVP) | Sí: se ejecuta en su Mac o ThinkPad |
| 3 | P0 | PR #3: no fusionar tal cual. Añadir autenticación, quitar `python`/`pip`/`npx`/`docker` de la lista o exigir aprobación previa, y llevarlo al monolito como herramienta del registro | Decidir si se integra |
| 4 | P1 | Selección de modelo en tiempo real: descubrir modelos de Ollama, modelo por defecto, modelo por conversación, error claro si no está instalado (sin cambio silencioso) | No |
| 5 | P1 | Agentes persistentes con propietario: CRUD sobre la tabla `agents`, duplicar, activar/desactivar; los 7 actuales como semilla | No |
| 6 | P2 | ✅ Renombrar conversaciones (`PATCH /api/conversations/{id}`) | No |
| 7 | P2 | Tareas: API sobre la tabla `tasks` (crear, estado, listar, propietario) | No |
| 8 | P2 | Registro de herramientas: contrato común (nombre, schema, permiso, timeout, auditoría) y herramientas desactivadas si no están configuradas | No |
| 9 | P2 | Documentos: extractores Markdown, CSV y DOCX; embeddings locales con Ollama como opción junto a BM25 | No |
| 10 | P2 | Integrar la biblioteca de prompts (PR #2) como módulo `products/prompts` con autenticación, en lugar de una app aparte | Decidir si se integra |

## Después (no empezar hasta cerrar lo anterior)

- Agent Builder con generación por IA y confirmación antes de guardar.
- Orquestación secuencial con límites de pasos, tiempo y tokens; luego equipos.
- Memoria con ámbitos (usuario, agente, proyecto) y expiración.
- Proveedores OpenAI y Gemini **solo si el propietario lo pide**: implican coste.
- Capa de acceso PostgreSQL.
- Terraform AWS: aparcado; nada se crea en AWS sin autorización expresa.

## Decisiones pendientes del propietario

- D1: ¿`backup/macbook` pasa a ser `main`? (propuesta: sí, por fusión, sin borrar ramas).
- D2: ¿Se integran PR #2 y PR #3 en el monolito o se cierran como prototipos?
- D3: ¿Se mantienen los módulos Finanzas, Developer y multiorganización dentro de «Personal AI»?
