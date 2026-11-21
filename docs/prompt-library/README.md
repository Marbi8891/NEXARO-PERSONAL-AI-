# Prompt Library MVP

This branch introduces an initial working Prompt Library module for the documented local-first stack.

## Status
- SQLite persistence for prompts, favorites, execution history and versions.
- Prompt CRUD and duplicate.
- Search, category filter and sorting.
- Dynamic variables with required-variable validation.
- Ollama execution through its `/api/chat` endpoint (non-streaming MVP).
- Local web UI with prompt cards, editor, run form, result modal and history.
- Initial seed catalogue: 26 prompts.
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
- No streaming, ratings, import/export, prompt packs, workflow execution, semantic search or per-user authorization yet.
- Variable metadata supports basic text, textarea, number and select forms. Backend validation currently checks that referenced variables are supplied.
- Run tests and security review before treating this as production-ready.
