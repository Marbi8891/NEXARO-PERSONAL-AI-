# NEXARO

Plataforma de IA propia, local primero: chat con modelos locales (Ollama), cuentas con
aprobación manual, auditoría y una base preparada para varias organizaciones y para
proveedores en la nube. Monolito modular en Python (FastAPI) con frontend HTML/CSS/ES Modules.

## Estado

| Área | Estado |
|---|---|
| Autenticación, sesiones, auditoría, administración | Implementado y probado |
| Chat con Ollama (`products/personal_ai`) | Implementado y probado |
| AI Gateway: políticas, respaldo, registro de uso, proveedores Bedrock/SageMaker | Implementado; AWS probado solo con dobles (ADR-0004) |
| Multiorganización (organizaciones, roles, documentos, agentes) | Pendiente |
| PostgreSQL | Pendiente (hoy solo SQLite) |
| AWS (Terraform) | Pendiente; **no se crea nada en AWS sin autorización expresa** |

## Arranque rápido (Docker)

```bash
docker compose up -d --build backend      # http://127.0.0.1:8001
docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin \
    --confirm-database /data/nexaro.db --email TU_CORREO
```

Requiere la red externa `ollama-local_default` con Ollama. No hay administradores ni registro
público por defecto; ver [SECURITY.md](SECURITY.md).

## Desarrollo

```bash
make install   # dependencias de desarrollo
make check     # ruff + mypy + pytest con cobertura
make run       # API local con recarga en 127.0.0.1:8001
```

Detalles en [DEVELOPMENT.md](DEVELOPMENT.md). Arquitectura en [ARCHITECTURE.md](ARCHITECTURE.md),
decisiones en [docs/decisions](docs/decisions), API en [API.md](API.md), despliegue en
[DEPLOYMENT.md](DEPLOYMENT.md).

## Estructura

```
apps/api/nexaro_api/   FastAPI: app factory, rutas, dependencias, CLI bootstrap_admin
packages/nexaro_core/  config, security, database, identity, audit
packages/ai_gateway/   contrato de proveedores y proveedor Ollama
products/personal_ai/  caso de uso de chat (sin FastAPI)
frontend/              HTML/CSS/ES Modules
tests/                 unit, integration, security
docs/decisions/        ADRs
```
