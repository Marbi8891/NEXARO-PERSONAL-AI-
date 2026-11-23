# NEXARO roadmap

Direction and priorities for NEXARO. There are **no committed dates**: items move forward in small,
tested pull requests, in the order below, on the existing modular monolith (no framework change, no
microservices). Exact current status of every feature: [capability matrix](docs/product/capabilities.md).

**Legend:** ✅ done · 🔄 in progress · ⏭ next · 📋 planned · 💡 future

## Completed

| Area | Delivered |
|---|---|
| Platform core | Accounts with manual approval, sessions, password change, append-only audit, organizations, roles and permissions, tenant isolation at the database level |
| AI | Local chat via Ollama with streaming and cancel; AI Gateway with fallback, circuit breaker, limits and usage ledger; per-conversation model selection |
| Agents | 7 built-in agents, personal agents (CRUD, duplicate, enable/disable), organization agents API, per-agent tool permissions with audit |
| Knowledge | Text and PDF documents, BM25 retrieval with cited sources in chat, read-only Obsidian vault, versioned prompt library with a 100-prompt catalogue |
| Developer | Scoped API keys with per-key rate limits and usage, `/api/v1` |
| Operations | 13 versioned migrations with verified pre-migration backup, Windows backup/restore with a restore drill, operations panel, hardened Docker deployment, `make smoke` against a real model |
| Quality | ~800 tests, strict typing, security CI (pip-audit, Bandit, gitleaks, Trivy, SBOM), reproducible model evaluation |

## In progress

| # | Item | Scope |
|---|---|---|
| 1 | 🔄 **v1.0 stabilization** | Tag and publish `v1.0.0` through the release workflow; repository and documentation professionalization; keep `make smoke` green on the target machines |

## Next

| # | Item | Scope |
|---|---|---|
| 2 | ⏭ **Security audit findings** | Idle session timeout (in addition to the 7-day limit); `--reset-password` in `bootstrap_admin`; versioned scrypt cost with rehash; shared rate-limit store before running more than one instance; enable Trivy IaC scan as blocking. Source: [v1.0 security review](docs/security/audits/security-review-v1.md) |
| 3 | ⏭ **Model Manager** | Default model per user and per agent; pull/remove models from the UI (admin, audited); model metadata and recommended hardware |

## Planned

| # | Item | Scope |
|---|---|---|
| 4 | 📋 **Intelligent Model Router** | Task-aware routing on top of the AI Gateway (e.g. code vs. short questions), with explicit, explainable rules and no silent model substitution |
| 5 | 📋 **Agent Runtime** | Executor with a common tool contract (name, schema, permission, timeout, audit), step/time/token budgets, cancellation and execution history; tools disabled unless configured |
| 6 | 📋 **Persistent Task Engine** | API on the existing `tasks` table: create, status, list, ownership; resumable after restart |
| 7 | 📋 **Orchestrator** | Sequential plans with hard limits on steps, time and tokens; user approval for sensitive steps |
| 8 | 📋 **Controlled multi-agent execution** | Agent teams on top of the orchestrator, sequential by default on modest hardware |
| 9 | 📋 **Memory system** | Scoped memory (user, agent, project) with expiry, visibility and deletion |
| 10 | 📋 **Advanced RAG** | Local embeddings via Ollama alongside BM25; Markdown, CSV and DOCX extractors |
| 11 | 📋 **Prompt Library integration** | Port the remaining prototype features (packs, workflows) into the platform module (ADR-0025) |
| 12 | 📋 **Secure Coding Agent** | Bring the coding-agent prototype into the monolith only with authentication, opt-in commands, approval before execution and a sandbox; disabled by default |

## Future

| Item | Condition |
|---|---|
| 💡 PostgreSQL runtime | The DDL is already validated in CI; needs the data-access layer |
| 💡 Additional cloud providers (OpenAI, Gemini) | Only on explicit owner request: they add cost and send data off-host |
| 💡 AWS deployment | Terraform is written but parked; **nothing is created in AWS without explicit authorization** |
| 💡 English UI | Interface translation (the UI is currently Spanish) |
| 💡 Organization agents UI, AI-assisted Agent Builder | After the Agent Runtime |

## Pending owner decisions

- **D2:** integrate the prototype PRs (#2 prompt library, #3/#6 coding agent, #7) into the monolith, or close them as prototypes.
- **D3:** keep Finance, Developer and multi-organization inside "Personal AI", or split product scope.
- **D4:** model selector for all users or administrators only (currently all; ADR-0023 vs. ADR-0019).
- **Licence:** the code is proprietary today; choose whether to adopt an open-source licence.

Resolved: D1 (`main` is the canonical lineage, 2026-11-22) · D5 (both personal and organization agents, ADR-0024).
