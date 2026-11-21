# NEXARO AI roadmap

This roadmap distinguishes planned capabilities from verified implementation.

## Phase 0 — Repository and runtime baseline
- [ ] Inspect frontend, backend, Docker Compose and Ollama integration.
- [ ] Record actual ports, networks, volumes and entrypoints.
- [ ] Establish test and lint commands.
- [ ] Verify startup and health checks.
- [ ] Add sanitized environment example.

## Phase 1 — Agent Hub foundation
- [ ] Agent definition schema and validation.
- [ ] Seed catalogue and categories.
- [ ] Persistent agent CRUD.
- [ ] Agent Hub UI.
- [ ] Model availability validation.
- [ ] Configuration versioning.

## Phase 2 — Agent execution
- [ ] Executor and streaming.
- [ ] Execution history and cancellation.
- [ ] Runtime budgets and loop limits.
- [ ] Agent chat history.

## Phase 3 — Permissioned tools
- [ ] Tool contract and registry.
- [ ] Per-agent tool grants.
- [ ] Approval lifecycle.
- [ ] Read-only filesystem restricted to roots.
- [ ] Code analysis and Git read operations.
- [ ] Docker status read-only tool.
- [ ] Audit logs.

## Phase 4 — Multi-agent orchestration
- [ ] Task decomposition.
- [ ] Agent selection from enabled catalogue.
- [ ] Sequential delegation by default.
- [ ] Result aggregation and source attribution.
- [ ] Approval before side effects.
- [ ] Bounded retries and failure recovery.

## Phase 5 — Memory and workspaces
- [ ] Workspace CRUD and isolation.
- [ ] User-managed explicit memories.
- [ ] Workspace-scoped memories.
- [ ] Search, edit and deletion.
- [ ] Context budgeting and retention.

## Phase 6 — Knowledge Base / RAG
- [ ] Document upload and validation.
- [ ] Local extraction, chunking and metadata.
- [ ] Local embeddings and vector-store adapter.
- [ ] Retrieval citations.
- [ ] Deletion and index cleanup.

## Phase 7 — Tasks and automation
- [ ] Task manager.
- [ ] Manual workflows.
- [ ] Scheduler with explicit activation.
- [ ] Approval gates.
- [ ] Execution logs and retry policy.

## Definition of done

A feature is complete only when API and UI behavior exist, server-side validation and permissions are enforced, automated tests pass, failure paths are covered, and documentation describes tested behavior. A design document or prompt is not an implemented feature.
