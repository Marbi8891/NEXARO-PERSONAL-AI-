# Prompt Library development plan

## MVP (this branch)
- [x] Prompt CRUD
- [x] Search/category/sort
- [x] Favorites
- [x] Dynamic template variables
- [x] Ollama execution
- [x] Execution history
- [x] Version snapshots on edit
- [x] Seed prompts

## Next increments
1. [x] Add tests for catalogue, pack metadata, import preview and workflow CRUD. Continue adding coverage for execution errors and Ollama integration.
2. [x] Add SSE streaming for prompt execution, execution persistence and client-side abort.
3. [x] Add JSON library export and JSON/Markdown prompt import preview with duplicate handling.
4. [x] Add Prompt Packs and install/uninstall idempotency (curated packs and basic UI/API).
5. [x] Add sequential Workflow Builder, ordered stages, shared variables, execution logs and error persistence. Future: budgets, pause/resume, retries.
6. [x] Add AI prompt quality evaluation with subjective scores and recommendations.
7. Add semantic search only after checking embedding/vector infrastructure.
8. Add auth/ownership and sharing before any multi-user or public deployment.
9. [x] Expand catalogue to 100 prompts with role-specific system instructions and structured variables. Review and refine prompt quality iteratively.
10. [x] Add Prompt Builder backed by Ollama.
