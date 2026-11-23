# NEXARO

Plataforma de IA propia, local primero: chat con modelos locales (Ollama), cuentas con
aprobación manual, auditoría y una base preparada para varias organizaciones y para
proveedores en la nube. Monolito modular en Python (FastAPI) con frontend HTML/CSS/ES Modules.

## Identidad visual

NEXARO usa una arquitectura de marca corporativa con productos bajo una marca matriz. Consulta [Brand Architecture](docs/brand-architecture.md) y el [Design System](docs/design-system.md).

**Brand line:** Intelligence under your control.

## Estado

| Área | Estado |
|---|---|
| Autenticación, sesiones, auditoría, administración | Implementado y probado |
| Chat con Ollama (`products/personal_ai`) | Implementado y probado |
| Docker: Ollama externo o incluido (perfil), `make model`, `make smoke`, salud del modelo | Implementado. Verificado en el Mac con Ollama y `qwen2.5:3b` reales (modo externo, `make smoke`); modo incluido probado solo con un Ollama simulado (ADR-0021) |
| AWS (Terraform: red, KMS, ECR, S3, ALB+Fargate, Aurora, alarmas, presupuesto) | Escrito, **no validado ni aplicado** (ADR-0006) |
| AI Gateway: políticas, respaldo, registro de uso, proveedores Bedrock/SageMaker | Implementado; AWS probado solo con dobles (ADR-0004) |
| Multiorganización: organizaciones, miembros, roles y permisos | Implementado y probado |
| Interfaz (sistema de diseño, tema claro/oscuro, panel con datos reales, avisos, PWA) | Implementado; probado con jsdom y Chromium |
| Developer: claves de API por organización con permisos, `/api/v1/chat` y `/api/v1/conversations`, límite y uso por clave | Implementado y probado |
| Documentos: subida de texto, búsqueda BM25 y preguntas con fuentes | Implementado y probado |
| Finanzas: gastos con resumen mensual y exportación CSV | Implementado y probado |
| Security: resumen de seguridad derivado de la auditoría (solo administradores) | Implementado y probado |
| Finance, Business | Solo identidad de marca; sin funcionalidad (no aparecen en la navegación) |
| Agentes: 6 especializados + tutor, herramientas con permiso por agente y usuario, auditoría `agent.tool`, selector en el chat | Implementado y probado (ADR-0022) |
| Tareas, embeddings | Solo esquema (sin API) |
| Migraciones versionadas | Implementado (SQLite, hasta la 7) |
| PostgreSQL | DDL validado con un servidor real; la app aún no ejecuta sobre él |
| AWS (Terraform) | Aparcado por decisión del propietario; **no se crea nada en AWS sin autorización expresa** |

## Arranque rápido (Docker)

```bash
make up        # comprueba el entorno, construye y espera a que todo esté sano: http://127.0.0.1:8001
make model     # descarga qwen2.5:3b solo si falta
make smoke     # servicios, salud, modelo, respuesta real y persistencia tras reiniciar
docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin \
    --confirm-database /data/nexaro.db --email TU_CORREO
```

Por defecto usa el Ollama de `~/Docker/ollama-local`; en una máquina sin él, el perfil `ollama` lo
incluye ([DEPLOYMENT.md](DEPLOYMENT.md)). No hay administradores ni registro público por defecto; ver
[SECURITY.md](SECURITY.md).

## Documentación

La documentación de la aplicación está centralizada en [docs/README.md](docs/README.md).

- [Descripción del producto](docs/PRODUCT.md)
- [Guía de usuario](docs/USER_GUIDE.md)
- [Arquitectura](ARCHITECTURE.md)
- [API](API.md)
- [Desarrollo](DEVELOPMENT.md)
- [Despliegue y operación](docs/OPERATIONS.md)
- [Seguridad](SECURITY.md)
- [Sistema de diseño](docs/design-system.md)
- [Decisiones técnicas (ADRs)](docs/decisions/)

## Desarrollo

```bash
make install   # dependencias de desarrollo
make check     # ruff + mypy + pytest con cobertura
make run       # API local con recarga en 127.0.0.1:8001
```

Detalles en [DEVELOPMENT.md](DEVELOPMENT.md).

## Estructura

```
apps/api/nexaro_api/   FastAPI: app factory, rutas, dependencias, CLI bootstrap_admin
packages/nexaro_core/  config, security, database, identity, audit, organizations, api_keys
packages/ai_gateway/   gateway, políticas, registro de uso y proveedores (Ollama, Bedrock, SageMaker)
products/personal_ai/  caso de uso de chat (sin FastAPI)
frontend/              HTML/CSS/ES Modules (js/, css/, views/), PWA; sistema de diseño en docs/design-system.md
tests/                 unit, integration, security, frontend (E2E jsdom: tests/frontend/run.sh)
docs/                 documentación funcional, técnica, operación y decisiones
```
