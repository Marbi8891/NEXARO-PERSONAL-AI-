# Installation

NEXARO runs as a single Docker Compose stack: the NEXARO backend (API + web UI) and an Ollama
model server. Everything listens on `127.0.0.1` only.

← [Documentation home](../README.md) · Next: [Quick start](quick-start.md)

## Requirements

| Requirement | Notes |
|---|---|
| Docker Engine or Docker Desktop | **Docker Compose ≥ 2.20** (needed for optional `depends_on`) |
| `make`, `curl`, `bash` | macOS / Linux. On Windows, see [Windows](#windows) |
| RAM | ~4 GB free for Docker with the default model `qwen2.5:3b` |
| Disk | ~3 GB (image + model) |
| CPU | Works on CPU; a GPU is not required |

## Choose an Ollama mode

NEXARO always reaches Ollama as `http://ollama:11434` on a private Docker network. Ollama never
publishes a port from this project ([ADR-0021](../decisions/0021-compose-ollama-profile-and-smoke.md)).

| | **Bundled** (recommended for new installs) | **External** (default in `compose.yaml`) |
|---|---|---|
| Ollama runs in | the `ollama` service of this `compose.yaml` (profile) | an existing Ollama container from `~/Docker/ollama-local` |
| Docker network | `nexaro_ollama` (created by `make up`) | `ollama-local_default` (must already exist) |
| `.env` | `COMPOSE_PROFILES=ollama` and `OLLAMA_NETWORK=nexaro_ollama` | nothing |

If you do not already run a separate Ollama stack, use **bundled** mode:

```bash
git clone https://github.com/Marbi8891/NEXARO-PERSONAL-AI-.git nexaro
cd nexaro
printf 'COMPOSE_PROFILES=ollama\nOLLAMA_NETWORK=nexaro_ollama\n' >> .env
```

`.env` is read by Docker Compose and is ignored by Git. Do not run both modes on the same network;
`make up` refuses to.

## Install

```bash
make up      # preflight checks, build, start, wait until healthy
make model   # download the configured model only if missing (~2 GB for qwen2.5:3b)
make smoke   # end-to-end check: services, health, model, real answer, persistence after restart
```

`make smoke` must end with `SMOKE OK`.

## Create the first administrator

There are **no default accounts and no public registration**. Create the first administrator
explicitly (you will be prompted for a password, minimum 12 characters):

```bash
docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin \
    --confirm-database /data/nexaro.db --email you@example.com
```

Open <http://127.0.0.1:8001> and sign in.

## Windows

Windows has no `make`, and PowerShell does not continue lines with `\`. From the clone folder:

| macOS / Linux | Windows (PowerShell) |
|---|---|
| `make up` | `docker compose up -d --build --wait` |
| `make model` | `Get-Content scripts\ollama_model.py -Raw \| docker exec -i nexaro-backend sh -c 'python - ensure "$OLLAMA_MODEL"'` |
| `make smoke` | `pwsh -File scripts\smoke_isolated.ps1 -Image nexaro-personal-ai-backend` |
| first admin | `docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin --confirm-database /data/nexaro.db --email you@example.com` |

The permanent Windows deployment (port, backups, scheduled tasks) is described in the
[deployment reference](../deployment/deployment-reference.md) (Spanish).

## Uninstall or stop

```bash
make down    # stops containers; data volumes are kept
```

> **Never run `docker compose down -v`.** It deletes the `nexaro-personal-ai_nexaro_data` volume,
> which holds the database.

## Next steps

- [Quick start](quick-start.md): first conversation, agents and documents.
- [Configuration](configuration.md): model, ports, limits, providers.
- [Troubleshooting](troubleshooting.md).
