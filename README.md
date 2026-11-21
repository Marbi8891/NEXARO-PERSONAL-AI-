# NEXARO Agent Hub MVP

Runnable FastAPI service that reads the agent catalogue and sends chat requests to Ollama. It is an isolated backend foundation; frontend integration is not included yet.

## Run locally (PowerShell)

```powershell
cd agent-hub
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```

From the repository root, the catalogue path defaults to `docs/agents/catalogue.json`. Ollama defaults to `http://localhost:11434` and model `qwen2.5:3b`.

## Docker

From this folder:

```powershell
docker compose up --build
```

The container uses Docker Desktop's `host.docker.internal` to reach Ollama on the host and binds API port 8081 to loopback only.

## API

- `GET /health`
- `GET /api/agents`
- `GET /api/agents/{agent_id}`
- `GET /api/models`
- `POST /api/agents/{agent_id}/chat`
- `POST /api/orchestrator/plan`

Chat body example:
```json
{
  "message": "Explain this Python function",
  "context": "def add(a, b): return a + b",
  "model": null
}
```

This MVP does not execute commands, modify files, browse the network, persist chats, or invoke tools. The orchestrator endpoint only produces a plan; it does not perform delegation.
