# Docker deployment

← [Documentation home](../README.md) · Installation steps: [installation.md](../getting-started/installation.md)

## Services

| Service | Container | Image | Exposure |
|---|---|---|---|
| `backend` | `nexaro-backend` | Built from `Dockerfile` (Python 3.12 slim, pinned by digest) | `127.0.0.1:${NEXARO_PORT:-8001}` → 8000 |
| `ollama` (profile `ollama`) | `nexaro-ollama` | `${OLLAMA_IMAGE:-ollama/ollama:latest}` | None (private network only) |

| Volume | Content |
|---|---|
| `nexaro-personal-ai_nexaro_data` | SQLite database (`/data/nexaro.db`), pre-migration copies, backup status |
| `nexaro-personal-ai_ollama_models` | Models (bundled mode only) |

The Compose project name is fixed (`nexaro-personal-ai`), so volume names do not depend on the clone folder.

## Hardening

The backend container runs with a read-only root filesystem, a 64 MB `tmpfs` for `/tmp`, non-root
uid 10001, `cap_drop: ALL`, `no-new-privileges`, `pids_limit: 200`, `mem_limit: 1g`, `cpus: 2.0` and
rotated logs. The frontend is mounted read-only. Verify a running deployment with the
[security baseline](../security/SECURITY_BASELINE.md) checklist.

## Lifecycle

| Task | Command |
|---|---|
| Start / update (preflight, build, wait for healthy) | `make up` |
| Download the configured model if missing | `make model` (`make model-check` only checks) |
| End-to-end verification | `make smoke` |
| Follow logs | `make logs` |
| Stop (keeps volumes) | `make down` |
| Rebuild only the backend, with verified backup and rollback tag | `scripts/rebuild_backend.sh` |

> **Never `docker compose down -v`.** It deletes the database volume.

## Upgrades and migrations

- Updating means rebuilding **only** `backend` while keeping the volume.
- Pending migrations run at startup in one transaction. On a database with data, a verified copy
  (`/data/nexaro.pre-migration-v<N>-<UTC date>.db`) is written first; if the copy fails, nothing is migrated.
- Migrations have no "down" step. To roll back, restore the previous image (`rollback-<date>` tag) **and**
  the pre-migration copy.

## Health

| Endpoint | Meaning |
|---|---|
| `GET /api/health/live` | Process is alive (container healthcheck) |
| `GET /api/health` | Backend + Ollama + model; `503` if Ollama or the model is unavailable |
| Administration → Operations | Services, CPU/memory (cgroups), disk, database integrity, last backup |

## Validate the configuration

```bash
docker compose config --quiet   # syntax and interpolation of compose.yaml + .env
```

## Further reading (Spanish)

- [Deployment reference](deployment-reference.md): Windows/ThinkPad permanent deployment, performance tuning, AWS
- [Operations](operations.md) · [Backup and restore](backup-restore.md) · [Remote access](remote-access.md)
- [AWS cost estimate](aws-costs.md): Terraform is written but has **never been applied**
