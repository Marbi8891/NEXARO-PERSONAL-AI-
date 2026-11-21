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
- Pack installation is non-destructive; uninstall only removes the installed marker.
- Seed data is stored in `data/prompt_catalogue_100.json` and `data/prompt_packs.json`.
- Basic unit tests for variable rendering and seed idempotency.

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
The included Compose file is a standalone starting point. Connect the app to the existing Ollama service/network and avoid publishing Ollama publicly.

## Known limitations
- This repository previously contained architecture documentation only. There is no existing authentication system to reuse; this MVP is local single-user and must not be exposed to untrusted networks.
- No streaming, ratings, import/export, workflow execution, semantic search or per-user authorization yet. Pack installation currently marks a curated pack as installed; catalogue prompts are seeded into the library at startup.
- Variable metadata supports basic text, textarea, number and select forms. Backend validation currently checks that referenced variables are supplied.
- Run tests and security review before treating this as production-ready.
