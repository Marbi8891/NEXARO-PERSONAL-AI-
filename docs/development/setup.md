# Development setup

← [Documentation home](../README.md) · Next: [Testing](testing.md) · Full reference (ES): [reference.md](reference.md)

## Prerequisites

- **Python 3.12** (the version used by CI and the Docker image; `>=3.10` is the language floor).
  Python 3.13 currently cannot install the dev dependency `pgserver`.
- Node.js ≥ 20 (only for the frontend end-to-end tests).
- Optional: Docker (stack, smoke test, model evaluation sandbox), Ollama (real model).

## First run

```bash
python3.12 -m venv .venv && . .venv/bin/activate
make install        # requirements/dev.txt (pinned runtime deps + tooling)
make check          # ruff + mypy + pytest with coverage — must be green before any PR
make run            # API + UI with auto-reload on http://127.0.0.1:8001
```

`make run` expects Ollama at `OLLAMA_BASE_URL` (default `http://localhost:11434`). Without it the UI
works, and `/api/health` reports the model as unavailable.

Run `make help` to list every command.

## Project layout

```
apps/api/nexaro_api/   HTTP layer: app factory, routers, dependencies, bootstrap_admin CLI
packages/nexaro_core/  config, security, database + migrations, identity, audit, organizations, API keys
packages/ai_gateway/   gateway, policy, breaker, usage, providers (Ollama, Bedrock, SageMaker)
products/personal_ai/  chat, agents, documents, prompt library, guard (no FastAPI imports)
products/finance/      expenses
frontend/              HTML/CSS/ES modules served by the API (no build step)
tests/                 unit · integration · security · frontend (E2E)
scripts/               stack, smoke, model, backup/restore, evaluation, benchmark
infrastructure/aws/    Terraform (never applied)
docs/                  documentation and ADRs
```

Imports work without installing the project: `PYTHONPATH=.:packages:apps/api`
([ADR-0002](../decisions/0002-python-layout-and-dependencies.md)). `pyproject.toml` only configures tools.

## Conventions

- Respect the [dependency rules](../architecture/overview.md#layers-and-dependency-rules); a test enforces them.
- Significant decisions get an ADR in [`docs/decisions/`](../decisions/README.md).
- Dependencies are pinned in `requirements/*.txt`; `make audit` runs `pip-audit`.
- `pre-commit install` enables ruff, formatting and gitleaks hooks.
- Never edit a migration that has already been applied; add a new one in **both** `sqlite/` and `postgresql/`.
- Frontend: build DOM with `h()`, never `innerHTML`; colours only in `frontend/css/tokens.css`.
- Never commit secrets, databases, backups or `.env`.

See also [CONTRIBUTING.md](../../CONTRIBUTING.md).
