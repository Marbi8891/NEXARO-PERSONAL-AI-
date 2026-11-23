## Summary

<!-- What changes and why. Link the issue or roadmap item. -->

## Type

- [ ] Feature
- [ ] Fix
- [ ] Security
- [ ] Refactor
- [ ] Documentation
- [ ] Build / CI / dependencies

## How it was tested

<!-- Commands run and results. A real-model check (`make smoke`) if the change touches chat or the gateway. -->

- [ ] `make check` is green (ruff, mypy, pytest with coverage, documentation links)
- [ ] Frontend change: `bash tests/frontend/run.sh` is green
- [ ] New endpoint: tests for unauthorized and cross-tenant access

## Checklist

- [ ] No secrets, databases, backups or personal data in the diff or screenshots
- [ ] Dependency rules respected (`apps → products → packages`)
- [ ] No applied migration edited; new migrations added for both SQLite and PostgreSQL
- [ ] Documentation updated, and it describes only what the code does
- [ ] ADR added for a significant architectural decision
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
