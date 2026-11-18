# NEXARO

Plataforma de IA propia, local primero: chat con modelos locales (Ollama), cuentas con
aprobación manual, auditoría y una base preparada para varias organizaciones y para
proveedores en la nube. Monolito modular en Python (FastAPI) con frontend HTML/CSS/ES Modules.

## Estado

| Área | Estado |
|---|---|
| Autenticación, sesiones, auditoría, administración | Implementado y probado |
| Chat con Ollama (`products/personal_ai`) | Implementado y probado |
| Docker: Ollama externo o incluido (perfil), `make model`, `make smoke`, salud del modelo | Implementado; probado con Docker y un Ollama simulado. **VERIFY** con Ollama real (ADR-0021) |
| AWS (Terraform: red, KMS, ECR, S3, ALB+Fargate, Aurora, alarmas, presupuesto) | Escrito, **no validado ni aplicado** (ADR-0006) |
| AI Gateway: políticas, respaldo, registro de uso, proveedores Bedrock/SageMaker | Implementado; AWS probado solo con dobles (ADR-0004) |
| Multiorganización: organizaciones, miembros, roles y permisos | Implementado y probado |
| Interfaz (sistema de diseño, tema claro/oscuro, panel con datos reales, avisos, PWA) | Implementado; probado con jsdom y Chromium |
| Developer: claves de API por organización con permisos, `/api/v1/chat` y `/api/v1/conversations`, límite y uso por clave | Implementado y probado |
| Documentos: subida de texto, búsqueda BM25 y preguntas con fuentes | Implementado y probado |
| Finanzas: gastos con resumen mensual y exportación CSV | Implementado y probado |
| Security: resumen de seguridad derivado de la auditoría (solo administradores) | Implementado y probado |
| Finance, Business | Solo identidad de marca; sin funcionalidad (no aparecen en la navegación) |
| Agentes, tareas, embeddings | Solo esquema (sin API) |
| Migraciones versionadas | Implementado (SQLite, hasta la 6) |
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

## Desarrollo

```bash
make install   # dependencias de desarrollo
make check     # ruff + mypy + pytest con cobertura
make run       # API local con recarga en 127.0.0.1:8001
```

Detalles en [DEVELOPMENT.md](DEVELOPMENT.md). Arquitectura en [ARCHITECTURE.md](ARCHITECTURE.md),
diseño en [docs/design-system.md](docs/design-system.md), decisiones en [docs/decisions](docs/decisions), API en [API.md](API.md), despliegue en
[DEPLOYMENT.md](DEPLOYMENT.md).

## Estructura

```
apps/api/nexaro_api/   FastAPI: app factory, rutas, dependencias, CLI bootstrap_admin
packages/nexaro_core/  config, security, database, identity, audit, organizations, api_keys
packages/ai_gateway/   gateway, políticas, registro de uso y proveedores (Ollama, Bedrock, SageMaker)
products/personal_ai/  caso de uso de chat (sin FastAPI)
frontend/              HTML/CSS/ES Modules (js/, css/, views/), PWA; sistema de diseño en docs/design-system.md
tests/                 unit, integration, security, frontend (E2E jsdom: tests/frontend/run.sh)
docs/decisions/        ADRs
```
