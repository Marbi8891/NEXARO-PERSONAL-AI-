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
Loopback-only API on 8081; only `agent-hub/workspace` is mounted. The container joins the existing external Docker network `nexaro_ai` and reaches Ollama at `http://ollama:11434` (create the network and attach your Ollama container to it first).

## API
- `GET /health`
- `GET /api/agents`
- `GET /api/models`
- `POST /api/agents/{agent_id}/chat`
- `POST /api/orchestrator/plan` (planning-only)
- `POST /api/coding/execute` (real tool execution; disabled by default, requires `Authorization: Bearer <AGENT_HUB_API_TOKEN>`)

Example request:
```json
{"task":"Create calculator.py with arithmetic functions, add tests and run them.","model":"qwen2.5-coder:7b","max_iterations":12}
```

Tools: list/read/search files, write/edit files, create directories and run allowlisted commands. Workspace paths are confined. Shell operators are rejected; subprocess runs without a shell. Deletion, deployment, push and merge are not provided.

## Enabling the coding agent

The coding agent is **off by default**: `/api/coding/execute` answers 503 and `/health` reports `coding_agent: disabled`.
To enable it, set in `.env` (or the shell before `docker compose up`):

```
CODING_AGENT_ENABLED=true
AGENT_HUB_API_TOKEN=<a long random value you generate, e.g. python -c "import secrets;print(secrets.token_urlsafe(32))">
```

Every request then needs `Authorization: Bearer <token>`. If the token is empty, `/health` reports `misconfigured` and the endpoint stays closed.

`run_command` is a second, separate opt-in (`CODING_AGENT_ALLOW_COMMANDS=true`). While it is off the tool is not offered to the model and the backend refuses it if the model names it anyway. **Allowing commands means arbitrary code execution**: `python`, `node`, `pip`, `npm` and `make` can run any code, so the allowlist does not confine them to the workspace. Only enable it inside the hardened container, never when running uvicorn directly on your machine.

Files inside any `.git` directory cannot be read or written by the agent, so it cannot plant Git hooks or `core.fsmonitor` settings that `git status` would execute.

## Security note
This is a personal-use MVP, not a hardened multi-tenant sandbox. Keep the workspace to trusted source code and do not expose the API publicly. Command allowlisting and path confinement reduce risk but do not replace OS/container isolation.
