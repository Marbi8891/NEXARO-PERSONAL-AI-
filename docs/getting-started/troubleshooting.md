# Troubleshooting

← [Configuration](configuration.md) · [Documentation home](../README.md)

Start with these three commands:

```bash
docker compose ps                        # are both services up and healthy?
curl -s http://127.0.0.1:8001/api/health # backend + Ollama + model status
docker compose logs --tail 100 backend   # structured JSON logs with request_id
```

`/api/health/live` only says the process is alive (used by the container healthcheck).
`/api/health` checks Ollama and the model, and returns `503` when either is unavailable.

## Installation and startup

| Symptom | Cause | Fix |
|---|---|---|
| `no existe la red ollama-local_default` | External mode, but no external Ollama stack | Use [bundled mode](installation.md#choose-an-ollama-mode) or start your Ollama stack |
| `habría dos 'ollama'` | Bundled mode on the external network | Set `OLLAMA_NETWORK=nexaro_ollama` in `.env` |
| `hace falta Docker Compose >= 2.20` | Old Compose | Update Docker Desktop or `docker-compose-plugin` |
| `Docker no responde` | Docker daemon not running | Start Docker Desktop / the Docker service |
| Cannot open `127.0.0.1:8001` | Container stopped or port in use | `docker compose ps`; set `NEXARO_PORT` and `ALLOWED_ORIGINS` |
| App exits at startup with a configuration error | Invalid or unsafe settings (fail-fast) | Read the error; see [Configuration](configuration.md) |
| App exits during a migration | A migration failed; nothing was applied | Check logs. A verified copy `nexaro.pre-migration-v<N>-*.db` is kept next to the database |

## Models

| Symptom | Cause | Fix |
|---|---|---|
| `/api/health` → `Modelo de IA no disponible` | Model not downloaded | `make model` |
| `/api/health` → `Servicio de IA no disponible` | Ollama unreachable | Check the Ollama container and network |
| `make model` stops "without progress" | Slow or interrupted network | Run it again; Ollama resumes |
| First answer is slow | Model loading on CPU | Expected; `OLLAMA_KEEP_ALIVE=30m` keeps it loaded |
| "Model not installed" when a conversation is pinned | Pinned model was removed from Ollama | Pull it again or choose another model |

## Accounts and access

| Symptom | Cause | Fix |
|---|---|---|
| No way to sign in on a fresh install | No default accounts by design | [Create the first administrator](installation.md#create-the-first-administrator) |
| New user cannot sign in | Accounts need manual approval | Administration → approve |
| `403` on a state-changing request | `Origin` not in `ALLOWED_ORIGINS` | Add the exact origin (scheme, host, port) |
| Login rate-limited behind NAT | All users share one IP | Raise `LOGIN_IP_MAX_ATTEMPTS` |

## Data

- The database is a single SQLite file in the `nexaro-personal-ai_nexaro_data` volume.
- **Never** run `docker compose down -v`.
- Backup and restore: [backup-restore.md](../deployment/backup-restore.md) (Spanish).

More operational detail (Spanish): [operations.md](../deployment/operations.md).
