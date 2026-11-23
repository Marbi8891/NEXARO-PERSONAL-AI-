# Testing

← [Development setup](setup.md) · Next: [Release process](release-process.md)

## Suites

| Suite | Path | What it covers |
|---|---|---|
| Unit | `tests/unit/` | Core services, gateway, breaker, guard, migrations, settings, architecture rules, container/Compose/Dockerfile hardening, design tokens, scripts |
| Integration | `tests/integration/` | The full FastAPI app against a temporary SQLite database and a fake model provider |
| Security | `tests/security/` | Access control, tenant and conversation isolation, abuse limits, LLM-specific risks, logging |
| Frontend E2E | `tests/frontend/` | Real ES modules in jsdom against the real API; optional real Chromium run |

The fake provider proves the application flow, **not** model quality. Model quality is measured
separately with `make eval` ([AI evaluation](ai-evaluation.md), Spanish).

## Commands

| Command | Purpose |
|---|---|
| `make check` | Lint + type check + tests with coverage (what CI runs) |
| `make test` | `pytest` |
| `make cov` | Tests with coverage report (threshold 80 %, set in `pyproject.toml`) |
| `make lint` / `make format` | Ruff check + format check / auto-fix |
| `make typecheck` | `mypy packages apps products` (strict: `disallow_untyped_defs`) |
| `make docs-check` | Validate relative links and anchors in all Markdown files |
| `make audit` | `pip-audit` of runtime dependencies |
| `bash tests/frontend/run.sh` | Frontend E2E with jsdom |
| `BROWSER=1 bash tests/frontend/run.sh` | Also real Chromium: CSP, fonts, themes, mobile, reference screenshots |
| `make smoke` | Against the running Docker stack and a real Ollama |

Useful selections:

```bash
pytest tests/security -m security
pytest tests/integration/test_chat_stream.py -q
NEXARO_REQUIRE_POSTGRES=1 pytest tests/unit/test_migrations.py   # fail instead of skip without PostgreSQL
```

## Expected skips

Some tests skip when a tool is missing: PowerShell 7 (backup scripts), Docker plus `python:3.12-slim`
(evaluation sandbox), `terraform`/`tofu`, symlink privileges on Windows. CI installs what it needs and
makes the PostgreSQL tests mandatory with `NEXARO_REQUIRE_POSTGRES=1`.

## Rules

- Existing tests are never modified just to make them pass.
- A new endpoint needs integration tests, including the unauthorized and cross-tenant cases.
- A new table needs `organization_id` and composite foreign keys, or the schema test fails.
- Windows: set `PYTHONUTF8=1`; see [reference.md](reference.md#tests-en-windows) for Bash requirements.
