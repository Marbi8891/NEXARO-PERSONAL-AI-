# AUDIT_REPORT — NEXARO Personal AI

Fecha: 2026-11-22. Fase 0, inspección de solo lectura. Todo lo que figura como «verificado» se ha
ejecutado en esta auditoría (contenedor Linux, Python 3.12.3, Node 22). Lo que no se ha podido
ejecutar aquí figura como `NOT_VERIFIED`, aunque otro documento diga que funciona.

## 1. Estado del repositorio

Repositorio: `Marbi8891/NEXARO-PERSONAL-AI-` (público). Hay **dos historias de Git sin ningún
commit en común**:

| Linaje | Ramas | Contenido | Último commit |
|---|---|---|---|
| A. Aplicación | `backup/macbook` (69f95b7), `feature/tutor-mode` (= macbook), `backup/thinkpad` (175d1ab, 5 commits por detrás), `feature/nexaro-design-system` (= thinkpad), `refactor/nexaro-platform` (3497a03, 29 por detrás) | Monolito modular FastAPI + frontend ES Modules, 308 archivos, F1–F27 | 2026-11-18, F27 agentes |
| B. Documentación | `main` (6d7e8b3), `feature/agent-hub-foundation`, `feature/prompt-library-mvp` (PR #2), `feature/real-coding-agent` (PR #3) | En `main` solo hay 13 archivos de diseño: catálogo de 86 agentes «proposed_catalogue», esquemas y roadmap. Las ramas de los PR añaden dos servicios independientes | 2026-11-21 |

**Hallazgo principal (P0, riesgo de pérdida):** la aplicación real no está en `main`. Solo existe
en ramas `backup/*` y en ramas de trabajo. Si se borrase una de esas ramas o se tomase `main` como
fuente de verdad, se perdería el producto. El linaje A contiene a los demás de su historia
(`thinkpad` y `refactor/nexaro-platform` son antecesores de `backup/macbook`), así que
`backup/macbook` es la versión más reciente y completa.

Decisión propuesta: **`backup/macbook` es la versión canónica** y se fusiona en `main` conservando
la documentación de `main` (rama `claude/project-thread-17a30v`). Ninguna rama antigua se borra.

## 2. Arquitectura encontrada (linaje A)

Monolito modular (ADR-0001) con dependencias dirigidas comprobadas por
`tests/unit/test_architecture.py`:

```
apps/api (FastAPI)  ──►  products/{personal_ai, finance}  ──►  packages/{nexaro_core, ai_gateway}
frontend/ (HTML + CSS + ES Modules, PWA, CSP estricta) servido por la propia API
```

- Persistencia: SQLite en modo WAL con migraciones versionadas y checksum (1–7). DDL paralelo de
  PostgreSQL validado contra un servidor real, pero la aplicación no se ejecuta sobre PostgreSQL.
- IA: `ai_gateway` con políticas, respaldo, cortacircuitos y registro de uso. Proveedores Ollama
  (real), Bedrock y SageMaker (probados solo con dobles). El modelo se fija con `OLLAMA_MODEL`.
- Docker: `Dockerfile` (usuario 10001, imagen base por digest), `compose.yaml` endurecido
  (`read_only`, `cap_drop: ALL`, límites, logs rotados), Ollama externo o incluido por perfil.
- 22 ADR en `docs/decisions/`.

Linaje B (ramas de PR, **fuera** del monolito):

- PR #2 `feature/prompt-library-mvp`: otra app FastAPI (`app/main.py`, 675 líneas en un archivo) con
  SQLite propio, catálogo de 100 prompts y frontend propio. Sin autenticación.
- PR #3 `feature/real-coding-agent`: servicio `agent-hub/` con agente de código sobre Ollama y
  herramientas de archivo y comandos. Sin autenticación.

## 3. Pruebas ejecutadas en esta auditoría

| Qué | Resultado |
|---|---|
| `ruff check .` y `ruff format --check .` (linaje A) | OK (173 archivos) |
| `mypy packages products apps` | OK (73 archivos) |
| `pytest --cov` (linaje A) | **576 passed, 10 skipped**, cobertura 92,23 % (umbral 80 %) |
| Saltados | 6 de `quality_eval` (no hay Docker), 1 de Terraform (no hay binario), 1 de copia real en `backups/` |
| `tests/integration/test_postgres_schema.py` (pgserver real) | 6 passed |
| `bash tests/frontend/run.sh` (frontend real con jsdom contra la API real y modelo simulado) | **35 comprobaciones OK** |
| PR #2 `pytest` | 8 passed |
| PR #3 `agent-hub/pytest` | 9 passed |

No ejecutado aquí: Docker, Ollama real, `make smoke`, navegador Chromium (`BROWSER=1`),
Terraform, Bandit, pip-audit, gitleaks. El job `ci.yml` del linaje A solo se dispara en `main`,
`refactor/**`, `security/**` y en PR: **la rama `backup/macbook` nunca ha pasado CI en GitHub**.
El PR de consolidación lo ejecutará por primera vez.

## 4. Funcionalidades

El detalle con evidencias está en [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md). Resumen
del MVP definido por el propietario (20 pasos): **8 verificados de 20 (40 %)**.

## 5. Bugs y defectos

| ID | Prioridad | Defecto | Evidencia |
|---|---|---|---|
| BUG-01 | P0 | La aplicación no está en `main`; solo en ramas `backup/*` | §1 |
| BUG-02 (corregido) | P3 | `tests/frontend/run.sh` no tiene bit de ejecución (`100644`); la documentación dice ejecutarlo directamente | `git ls-files -s tests/frontend/run.sh`; `Permission denied` |
| BUG-03 | P2 | No se puede renombrar una conversación (no hay endpoint) | No existe `PATCH /api/conversations/{id}` |
| BUG-04 | P2 | El README del linaje B en `main` describe una arquitectura «planned» que no coincide con la real | `README.md` de `main` |

## 6. Riesgos de seguridad

| ID | Prioridad | Riesgo | Evidencia |
|---|---|---|---|
| SEC-01 | P0 (si se fusiona o expone) | PR #3: el servicio `agent-hub` no tiene autenticación y su herramienta `run_command` permite al modelo ejecutar `python`, `pip`, `npm`, `npx`, `docker`, `make`, `git`… sin aprobación del usuario. `python -c` ya es ejecución arbitraria de código dentro del contenedor | `agent-hub/app/tools.py:10` (`ALLOWED_COMMANDS`), `agent-hub/app/main.py` sin dependencias de auth |
| SEC-02 | P1 | PR #2: API sin autenticación ni propietario de los datos | `app/main.py`, rutas `@app.*` sin `Depends` |
| SEC-03 | P2 | El limitador de intentos es en memoria (no se comparte entre instancias) | `ARCHITECTURE.md`, límites conocidos |
| SEC-04 | P2 | La imagen de Ollama por defecto es `ollama/ollama:latest` (sin fijar) | `compose.yaml` |

Lo que sí está implementado y probado en el linaje A: sesiones con token guardado solo como
SHA-256, scrypt, registro cerrado, último admin protegido, auditoría append-only, aislamiento por
organización y usuario (`tests/security/test_tenant_isolation.py`, `test_access_control.py`),
pruebas de inyección SQL, CSP sin `unsafe-inline`, filtro de temas internos, delimitadores de
documentos contra inyección de prompt.

## 7. Código duplicado

- Tres implementaciones de «agentes» que no se conectan: `products/personal_ai/agents.py`
  (7 perfiles, en uso), `docs/agents/catalogue.json` (86 propuestos, sin código) y
  `agent-hub/app/registry.py` (PR #3, lee el catálogo).
- Dos backends FastAPI más fuera del monolito (PR #2 y PR #3), cada uno con su SQLite, su
  configuración y su Docker.
- `docs/architecture.md` (linaje B) y `ARCHITECTURE.md` (linaje A) describen arquitecturas
  distintas.

## 8. Deuda técnica

- Agentes definidos en código: no hay CRUD aunque la tabla `agents` existe (migración 2).
- Tareas y embeddings: solo esquema.
- PostgreSQL sin capa de acceso.
- Terraform de AWS escrito y no aplicado (aparcado por el propietario).

## 9. Estado de Docker y base de datos

- Docker: configuración revisada, **no ejecutada** aquí. La documentación afirma que `make smoke`
  pasó en el Mac con `qwen2.5:3b` (ADR-0021); no se ha podido comprobar.
- Base de datos: SQLite en el volumen `nexaro-personal-ai_nexaro_data`, ruta `/data/nexaro.db`.
  `Makefile` evita `down -v`. No he tocado ninguna base de datos real.

## 10. Prioridades

Ver [ROADMAP.md](ROADMAP.md).
