# NEXARO Personal AI

Local-first personal AI assistant built around Ollama, FastAPI, SQLite and Docker.

> **Project status:** architecture and Agent Hub foundation in progress. The files in this branch define the proposed multi-agent foundation and configuration catalogue. They are not a claim that every agent or execution capability is already implemented.

## Product direction

- Persistent chat and model management.
- Configurable specialist agents.
- User-controlled memory and project workspaces.
- A permissioned tool registry.
- Multi-agent orchestration.
- Local document retrieval (RAG).
- Task and automation management.

## Planned stack

- Backend: Python, FastAPI, Pydantic, SQLAlchemy.
- Frontend: HTML, CSS and JavaScript ES modules.
- Local inference: Ollama.
- Persistence: SQLite initially, with a migration path to PostgreSQL.
- Runtime: Docker Compose.

## Important status distinction

The Agent Hub documents and seed configurations are a design foundation. Agent execution, persistent CRUD, tool calling, memory, RAG, and frontend screens must be implemented and tested before being described as available.

## Security and privacy

- Never commit .env files, credentials, tokens, certificates, personal conversation history, live databases, or private logs.
- Do not expose Ollama or SQLite directly to the public internet.
- Treat retrieved documents and tool output as untrusted input.
- Enforce tool permissions in backend code, not prompts alone.
- Default agents to read-only access and disable terminal/network access.

See [SECURITY.md](SECURITY.md) and [docs/security/agent-security-model.md](docs/security/agent-security-model.md).

## License

No license has been added. Until one is added, no reuse rights are granted.
