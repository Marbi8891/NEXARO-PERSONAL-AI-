# Product capability matrix

Factual inventory of what NEXARO does **today**, verified against the source code and the test suite
of `main` (v1.0.0, November 2026). It is the single English reference for product status; the
step-by-step MVP evidence (in Spanish) lives in [implementation-status.md](implementation-status.md).

| Status | Meaning |
|---|---|
| **IMPLEMENTED** | Code exists, is reachable from the API/UI and is covered by automated tests |
| **PARTIALLY IMPLEMENTED** | Works, but with a documented gap in scope |
| **EXPERIMENTAL** | Code exists but has not been validated against the real target system |
| **PLANNED** | Schema, design or catalogue exists; no usable functionality |
| **DEPRECATED** | Kept for reference; not part of the product direction |

> Tests use a fake model provider for the chat flow. A test that passes proves the application flow,
> **not** the quality of a real model's answers. Real-Ollama validation is done with `make smoke`.

## AI workspace

| Capability | Status | Evidence / notes |
|---|---|---|
| Chat with local models via Ollama | IMPLEMENTED | `products/personal_ai/service.py`, `packages/ai_gateway/providers/ollama/`; verified with real Ollama and `qwen2.5:3b` via `make smoke` |
| Streaming responses (SSE) and cancellation | IMPLEMENTED | `POST /api/chat/stream`; `tests/integration/test_chat_stream.py`, frontend E2E "Detener" |
| Conversation history: list, reopen, rename, delete | IMPLEMENTED | `/api/conversations*`; `test_conversation_lifecycle.py` |
| Per-conversation model selection | PARTIALLY IMPLEMENTED | `GET /api/models` lists installed Ollama models; no per-user or per-agent default model yet (ADR-0023) |
| Markdown rendering without `innerHTML` | IMPLEMENTED | `frontend/js/markdown.js`; a test forbids `innerHTML`/`eval` |
| Restricted-topics guard (model, infrastructure, internal) | IMPLEMENTED | `products/personal_ai/guard.py` (ADR-0019) |
| Programming tutor mode | IMPLEMENTED | Agent `tutor` (ADR-0020) |

## Agents

| Capability | Status | Evidence / notes |
|---|---|---|
| Built-in specialised agents (7) | IMPLEMENTED | General, Developer, Security, Research, Productivity, Data, Tutor; `products/personal_ai/agents.py` (ADR-0022) |
| Personal agents: create, edit, duplicate, enable/disable | IMPLEMENTED | `/api/agents/custom`, `#/agents` screen; `test_custom_agents.py` |
| Organization agents (API) | PARTIALLY IMPLEMENTED | `/api/organizations/{id}/agents` (ADR-0024); no dedicated UI screen yet |
| Per-agent, per-user tool permissions with audit | PARTIALLY IMPLEMENTED | Server-side check and `agent.tool` audit event; only one tool exists (`documents`) |
| Agent runtime (agent executes tools autonomously) | PLANNED | Today an agent is a prompt profile plus allowed tools, not an executor |
| Multi-agent orchestration, agent teams | PLANNED | Target design only: [../architecture/target-architecture.md](../architecture/target-architecture.md) |
| Catalogue of 86 agent definitions | PLANNED | `docs/agents/catalogue.json` (`"status": "proposed_catalogue"`) |
| AI-assisted Agent Builder | PLANNED | Only manual creation exists |
| Secure coding agent with filesystem/shell tools | EXPERIMENTAL | Prototype outside the monolith (PR #3), not merged: lacks authentication (see audits) |

## Knowledge

| Capability | Status | Evidence / notes |
|---|---|---|
| Document upload (plain text and PDF) | IMPLEMENTED | `test_documents.py`, `test_documents_pdf.py`; 200,000 chars per document, 100 per organization |
| Lexical retrieval (BM25) with cited sources in chat | IMPLEMENTED | ADR-0012, ADR-0017; `test_chat_documents.py` |
| Embeddings / vector search | PLANNED | Table exists in migration 2; no API |
| DOCX, CSV, Markdown extractors | PLANNED | — |
| Obsidian vault (read-only, owner-only) | IMPLEMENTED | `/api/obsidian/*`; `test_obsidian_access.py` |
| Prompt library: versions, restore, rendering, 100-prompt catalogue | IMPLEMENTED | ADR-0025; `test_prompt_library.py`. Packs and workflows from the original prototype were not ported |
| Memory (user, agent, project) | PLANNED | — |
| Tasks / persistent task engine | PLANNED | `tasks` table exists (migration 2); no API |

## AI Gateway and providers

| Capability | Status | Evidence / notes |
|---|---|---|
| Provider routing, fallback order, retries | IMPLEMENTED | `packages/ai_gateway/gateway.py`, `AI_PROVIDER_ORDER` (ADR-0004) |
| Per-provider circuit breaker and model status | IMPLEMENTED | ADR-0016; `GET /api/admin/models` |
| Usage and cost ledger, monthly cloud budget | IMPLEMENTED | `packages/ai_gateway/usage.py`; cloud requires an explicit budget to start |
| Ollama provider | IMPLEMENTED | Default and only provider enabled out of the box |
| AWS Bedrock and SageMaker providers | EXPERIMENTAL | Implemented, tested only with test doubles; cloud is **off by default** |
| OpenAI, Gemini or other hosted providers | PLANNED | Not implemented; only on explicit owner request (cost) |
| Intelligent model router (task-aware routing) | PLANNED | Roadmap |

## Platform, security and operations

| Capability | Status | Evidence / notes |
|---|---|---|
| Accounts with manual approval, sessions, password change | IMPLEMENTED | scrypt, opaque session tokens (only SHA-256 stored), `SameSite=Strict` cookies |
| Append-only audit log | IMPLEMENTED | Triggers block UPDATE/DELETE; pseudonymised e-mail |
| Organizations, members, roles, permissions | IMPLEMENTED | Composite foreign keys enforce tenant isolation; `test_tenant_isolation.py` |
| API keys with scopes, per-key rate limit and usage; `/api/v1/*` | IMPLEMENTED | ADR-0009, ADR-0011; `test_api_keys.py` |
| Security summary (admin) | IMPLEMENTED | `GET /api/admin/security`; ADR-0010 |
| Operations panel: services, resources, errors, backups | IMPLEMENTED | `GET /api/admin/status` |
| Dashboard and notifications from real data | IMPLEMENTED | `test_dashboard.py` |
| Light/dark theme, responsive layout, PWA manifest | PARTIALLY IMPLEMENTED | PWA installation not tested |
| Versioned SQLite migrations (13) with verified backup before migrating | IMPLEMENTED | `test_migrations.py`, `test_startup_migration.py` |
| Backup and restore (Windows PowerShell scripts) | IMPLEMENTED | Full restore drill passed; [../deployment/backup-restore.md](../deployment/backup-restore.md) |
| Docker Compose deployment (external or bundled Ollama) | IMPLEMENTED | Hardened container (read-only FS, non-root, `cap_drop: ALL`); ADR-0021 |
| Private remote access (Tailscale Serve) | EXPERIMENTAL | Prepared and documented, not activated |
| PostgreSQL runtime | PLANNED | DDL validated against a real server in CI; the app runs only on SQLite |
| AWS infrastructure (Terraform) | EXPERIMENTAL | Written and validated statically; **never applied**; parked by owner decision (ADR-0006) |

## Product modules

| Module | Status | Notes |
|---|---|---|
| NEXARO Personal AI | IMPLEMENTED | Core product: chat, agents, documents, prompts |
| NEXARO Developer | IMPLEMENTED | API keys and `/api/v1` |
| NEXARO Security | IMPLEMENTED | Admin security summary |
| NEXARO Finance | IMPLEMENTED | Expenses with monthly summary and CSV export. Scope within the product is an open owner decision (D3 in the roadmap) |
| NEXARO Business | PLANNED | Brand identity only; hidden from navigation |

## Deprecated

| Item | Notes |
|---|---|
| `docs/architecture.md` (generic "intended architecture") | Removed; superseded by [../architecture/overview.md](../architecture/overview.md) |
| `docs/product/roadmap.md` (phase checklist) | Removed; superseded by [ROADMAP.md](../../ROADMAP.md) |
