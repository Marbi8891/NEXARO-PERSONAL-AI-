# NEXARO Agent Hub MVP

A small runnable FastAPI service that loads the proposed agent catalogue and calls Ollama. This is an isolated backend foundation; it does not yet integrate into the existing NEXARO frontend.

## Run locally

```powershell
cd agent-hub
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

Ensure Ollama is running and the configured models are installed. Defaults are:
- Ollama API: `http://localhost:11434`
- Model: `qwen2.5:3b`

## Docker

This standalone compose file binds the service to loopback only. Configure `OLLAMA_BASE_URL` to the Ollama service reachable from the container. If Ollama is on the host, use `http://host.docker.internal:11434` on Docker Desktop.

```powershell
docker compose up --build
```

## API

- `GET /health`
- `GET /api/agents`
- `GET /api/agents/{agent_id}`
- `GET /api/models`
- `POST /api/agents/{agent_id}/chat`
- `POST /api/orchestrator/plan`

Chat request:
```json
{
  "message": "Explain this Python function",
  "context": "def add(a, b): return a + b",
  "model": null
}
```

The API does not execute shell commands, modify files, or provide agent tools. Orchestrator endpoint returns a bounded planning response; it does not run delegated agents yet.
