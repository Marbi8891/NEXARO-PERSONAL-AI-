# Contributing to NEXARO

Thank you for your interest. NEXARO values small, verifiable changes and honest documentation.

> **Licence:** NEXARO is currently proprietary (see [LICENSE](LICENSE)). Open an issue to discuss a
> change before investing significant work, so ownership of contributions can be agreed.

## Before you start

- Read the [architecture overview](docs/architecture/overview.md) and the relevant [ADRs](docs/decisions/README.md).
- Check the [roadmap](ROADMAP.md) and the [capability matrix](docs/product/capabilities.md).
- Security issues go through [SECURITY.md](SECURITY.md), never a public issue.

## Workflow

1. Branch from `main`; keep each pull request small and focused.
2. Set up the environment: [development setup](docs/development/setup.md).
3. `make check` must be green (ruff, mypy, pytest with coverage, documentation links).
4. Significant architectural decisions need an ADR in `docs/decisions` (status, context, options,
   decision, rationale, trade-offs, consequences, date).
5. Respect the dependency rules in the [architecture overview](docs/architecture/overview.md#layers-and-dependency-rules); a test checks them.
6. No secrets, databases, backups or personal data in commits, screenshots or issues.
7. Commit messages use a prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `security:`, `build:`, `ci:`.
8. Fill in the pull request template, including how you tested the change.

## Rules that are not negotiable

- Existing tests are not modified just to make them pass.
- A migration that has been applied is never edited; add a new one for both SQLite and PostgreSQL.
- Authorization and limits are enforced in server code, not in prompts or the frontend.
- Documentation states only what the code does; planned work is labelled as planned.
- The frontend never uses `innerHTML`/`eval`; colours live only in `frontend/css/tokens.css`.
