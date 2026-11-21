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
1. Add automated tests for CRUD, rendering, missing variables, Ollama errors and persistence.
2. Add streaming, cancellation and run detail persistence UI.
3. Add JSON/Markdown import/export with schema validation and duplicate preview.
4. [x] Add Prompt Packs and install/uninstall idempotency (curated packs and basic UI/API).
5. Add workflow builder with sequential stages, explicit budgets and failure handling.
6. Add quality evaluation with clearly marked AI-generated, non-objective scores.
7. Add semantic search only after checking embedding/vector infrastructure.
8. Add auth/ownership and sharing before any multi-user or public deployment.
9. [x] Expand catalogue to 100 prompts with role-specific system instructions and structured variables. Review and refine prompt quality iteratively.
