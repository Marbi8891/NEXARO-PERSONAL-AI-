# Prompt Library MVP

This branch introduces an initial working Prompt Library module for the documented local-first stack.

## Status
- SQLite persistence for prompts, favorites, execution history and versions.
- Prompt CRUD and duplicate.
- Search, category filter and sorting.
- Dynamic variables with required-variable validation.
- Ollama execution through `/api/chat`, including SSE streaming.
- Local web UI with prompt cards, editor, run form, result modal and history.
- Seed catalogue: 26 original MVP prompts plus 100 curated catalogue prompts (idempotent import).
- Six Prompt Packs with browse, install and uninstall UI/API.
- Sequential Workflows: ordered prompt stages, shared variables, execution logs and saved history.
- Streaming prompt execution via Ollama and SSE, including execution persistence.
- JSON library export; JSON/Markdown prompt import with preview and duplicate handling.
- Prompt Builder powered by Ollama and subjective prompt quality evaluation.
- Pack installation is non-destructive; uninstall only removes the installed marker.
- Seed data is stored in `data/prompt_catalogue_100.json` and `data/prompt_packs.json`.
- Automated tests for seed idempotency, import preview, workflow CRUD, filters and version restore.

## Quick start (Docker)

```bash
docker compose -f docker-compose.prompt-library.yml up --build
```

Open http://localhost:8000. The Compose service binds to localhost. The default assumes Ollama is reachable from the Docker host at `http://host.docker.internal:11434`. If Ollama runs in another container, set `OLLAMA_URL` to its reachable address (for example, `http://ollama:11434`) and connect both containers to the same Docker network.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://localhost:8000.

## Run tests
```bash
pip install -r requirements-dev.txt
pytest
```

## Docker
The Compose file binds the web app to localhost only. Do not expose this unauthenticated single-user MVP to untrusted networks.

## Implemented APIs

- Prompt CRUD, favorites, duplicate, versions and restore.
- Prompt Pack browse/install/uninstall/export.
- JSON library export and JSON/Markdown prompt import preview.
- Prompt Builder and subjective evaluation via Ollama.
- Streaming prompt execution via SSE.
- Sequential workflows with ordered steps, shared variables and execution history.

## Known limitations
- This repository previously contained architecture documentation only. There is no existing authentication system to reuse; this MVP is local single-user and must not be exposed to untrusted networks.
- No ratings, semantic search, multi-user authorization, or per-user ownership yet. Workflow MVP is sequential and runs prompts in order; each stage uses shared variables plus `workflow_input` and `previous_output`. Pack installation currently marks a curated pack as installed; catalogue prompts are seeded into the library at startup.
- Variable metadata supports basic text, textarea, number and select forms. Backend validation currently checks that referenced variables are supplied.
- Run tests and security review before treating this as production-ready.
