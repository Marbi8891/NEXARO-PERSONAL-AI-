# Auditoría de recuperación de agentes — 2026-11-23

## Resultado

Los agentes no están perdidos. El repositorio conserva una implementación funcional de perfiles especializados y un catálogo amplio de plantillas. El trabajo pendiente es convertir el registro estático en un sistema administrable y conectarlo gradualmente a un runtime de ejecución.

## Recuperado del repositorio

- Registro de 7 agentes integrados: general, developer, security, research, productivity, data y tutor.
- Prompts especializados y reglas compartidas de seguridad/confidencialidad.
- Selector de agente en Chat, persistencia del agente en los mensajes y API GET /api/agents.
- Herramienta de consulta de documentos con comprobación de permisos y auditoría.
- ADR-0022 y pruebas de integración existentes.
- Catálogo de plantillas en docs/agents/catalogue.json y catalogue.md, con perfiles de desarrollo, ciberseguridad, datos/IA, educación, negocio, investigación y productividad.
- Esquema de agente en JSON Schema y YAML de General Assistant, Orchestrator y Python Developer.
- Tablas existentes agents, agent_runs y tasks, junto con permisos agents:read, agents:run y agents:manage.

## Bloqueos actuales

1. El registro usado por Chat está codificado en Python; no permite que el usuario cree agentes propios.
2. Las tablas de agentes y ejecuciones existían, pero no estaban conectadas a un CRUD de API.
3. El catálogo es documentación/templates, no un catálogo ejecutable.
4. No hay dispatcher general de herramientas, sandbox, workflow engine ni delegación entre agentes.
5. La autonomía y la memoria aparecen en los diseños, pero no son capacidades ejecutables.
6. Las plantillas con terminal, filesystem o red deben permanecer desactivadas hasta que existan permisos verificables, sandbox y controles de aprobación.

## Implementado en esta rama

- Migración 0008 para persistir categoría, modelo, herramientas, permisos, memoria, nivel de autonomía, template de origen y fecha de actualización.
- API CRUD por organización para agentes personalizados.
- Control de acceso con permisos de organización agents:read y agents:manage.
- Auditoría de creación, edición y eliminación.
- Validación de capacidades: agentes personalizados no pueden habilitar herramientas ejecutables ni permisos de terminal, filesystem o red.
- Métodos del cliente frontend para consumir el CRUD.

## Estado funcional

Los agentes personalizados de esta primera fase son perfiles de prompt persistentes y administrables. Todavía no se ejecutan desde el selector de Chat ni tienen herramientas, memoria operativa, autonomía o delegación. La API mantiene esa separación deliberadamente para no atribuir capacidades que no existen.

## Próximas fases

### Runtime v1
- Conectar agentes personalizados al chat con resolución tenant-scoped.
- Versionado de prompts y selección de modelos con allowlist.
- Registro de ejecuciones agent_runs y estados/errores.
- Interfaz de gestión de agentes y selección por workspace/organización.

### Tools v1
- Registro de herramientas con schemas.
- Permisos por agente y usuario.
- Ejecución aislada, límites de tiempo, recursos y directorios.
- Aprobación humana para acciones que modifican sistemas o datos.
- Auditoría sin almacenar contenido sensible.

### Orchestration v1
- Planner que genera plan estructurado y acotado.
- Delegación únicamente a agentes habilitados.
- Presupuesto de pasos, tokens y tiempo.
- Ejecución secuencial por defecto; paralelismo opt-in.
- Reviewer y consolidación de resultados.

### Workspace
- Proyectos, tareas, archivos, conocimiento, ejecuciones e historial.
- Memoria con alcance explícito (conversación/proyecto/global) y controles del usuario.
- Workflows programados y automatizaciones solo después de validar el runtime.
