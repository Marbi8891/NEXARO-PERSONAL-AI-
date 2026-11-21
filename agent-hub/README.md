# NEXARO Agent Hub — Coding Agent MVP
FastAPI service connecting Ollama to workspace-confined filesystem and allowlisted terminal tools.

## Local PowerShell
```powershell
cd agent-hub
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:WORKSPACE_DIR = "$PWD\workspace"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8081
```
Ollama must be available at `http://localhost:11434`. The default model is qwen2.5:3b. Coding quality is generally better with a model capable of tool calling, such as qwen2.5-coder:7b where resources permit.

## Docker
```powershell
New-Item -ItemType Directory -Force workspace
docker compose up --build
```
Loopback-only API on 8081; only `agent-hub/workspace` is mounted. Ollama is accessed via `host.docker.internal`.

## API
- `GET /health`
- `GET /api/agents`
- `GET /api/models`
- `POST /api/agents/{agent_id}/chat`
- `POST /api/orchestrator/plan` (planning-only)
- `POST /api/coding/execute` (real tool execution)

Example request:
```json
{"task":"Create calculator.py with arithmetic functions, add tests and run them.","model":"qwen2.5-coder:7b","max_iterations":12}
```

Tools: list/read/search files, write/edit files, create directories and run allowlisted commands. Workspace paths are confined. Shell operators are rejected; subprocess runs without a shell. Deletion, deployment, push and merge are not provided.

## Security note
This is a personal-use MVP, not a hardened multi-tenant sandbox. Keep the workspace to trusted source code and do not expose the API publicly. Command allowlisting and path confinement reduce risk but do not replace OS/container isolation.
