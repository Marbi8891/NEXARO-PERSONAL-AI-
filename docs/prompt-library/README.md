# Prompt Library MVP

This branch introduces an initial working Prompt Library module for the documented local-first stack.

## Status
- SQLite persistence for prompts, favorites, execution history and versions.
- Prompt CRUD and duplicate.
- Search, category filter and sorting.
- Dynamic variables with required-variable validation.
- Ollama execution through its `/api/chat` endpoint (non-streaming MVP).
- Local web UI with prompt cards, editor, run form, result modal and history.
- Seed catalogue: 26 original MVP prompts plus 100 curated catalogue prompts (idempotent import).
- Six Prompt Packs with browse, install and uninstall UI/API.
- Sequential Workflows: ordered prompt stages, shared variables, execution logs and saved history.
- Streaming prompt execution via Ollama and SSE, including execution persistence.
- JSON library export; JSON/Markdown prompt import with preview and duplicate handling.
- Prompt Builder powered by Ollama and subjective prompt quality evaluation.
- Pack installation is non-destructive; uninstall only removes the installed marker.
- Seed data is stored in `data/prompt_catalogue_100.json` and `data/prompt_packs.json`.
- Basic unit tests for variable rendering and seed idempotency.

## Quick start (Docker)\n\n```bash\ndocker compose -f docker-compose.prompt-library.yml up --build\n```\n\nOpen http://localhost:8000. The Compose service binds to localhost. Connect it to the private network containing Ollama; the Compose file intentionally does not expose Ollama. Set `OLLAMA_URL` and `OLLAMA_MODEL` to match your local service/model.\n\n## Run locally
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
The included Compose file is a standalone starting point. Connect the app to the existing Ollama service/network and avoid publishing Ollama publicly.

## Implemented APIs\n\n- Prompt CRUD, favorites, duplicate, versions and restore.\n- Prompt Pack browse/install/uninstall/export.\n- JSON library export and JSON/Markdown prompt import preview.\n- Prompt Builder and subjective evaluation via Ollama.\n- Streaming prompt execution via SSE.\n- Sequential workflows with ordered steps, shared variables and execution history.\n\n## Known limitations
- This repository previously contained architecture documentation only. There is no existing authentication system to reuse; this MVP is local single-user and must not be exposed to untrusted networks.
- No ratings, semantic search, multi-user authorization, or per-user ownership yet. Workflow MVP is sequential and runs prompts in order; each stage uses shared variables plus `workflow_input` and `previous_output`. Pack installation currently marks a curated pack as installed; catalogue prompts are seeded into the library at startup.
- Variable metadata supports basic text, textarea, number and select forms. Backend validation currently checks that referenced variables are supplied.
- Run tests and security review before treating this as production-ready.
