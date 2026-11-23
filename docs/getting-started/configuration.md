# Configuration

NEXARO is configured with environment variables. The full, commented list is
[`.env.example`](../../.env.example); the authoritative definitions (types, defaults, validation) are in
[`packages/nexaro_core/config/settings.py`](../../packages/nexaro_core/config/settings.py).

← [Quick start](quick-start.md) · Next: [Troubleshooting](troubleshooting.md)

## Where variables are read

| Context | Source |
|---|---|
| Docker (`make up`) | `compose.yaml` sets the backend's environment. `.env` is used by Compose for **interpolation only** (the variables listed in [Docker Compose](#docker-compose)) |
| Local development (`make run`) | Your shell environment; `make run` sets `DATABASE_PATH` and `FRONTEND_PATH` |

The application **refuses to start** on an invalid or unsafe configuration (fail-fast). For example,
`NEXARO_ENV=production` requires `COOKIE_SECURE=true` and `https` origins.

## Models and Ollama

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5:3b` | Default model ("auto" mode, with fallback) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` in Docker | Ollama endpoint |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long the model stays loaded after the last request |
| `OLLAMA_NUM_CTX` | `4096` | Context window. Keep it constant: changing it reloads the model |
| `OUTPUT_TOKENS_SHORT` / `_DEFAULT` / `_CODE` | 512 / 1024 / 2048 | Output caps per question type |
| `CHAT_HISTORY_MAX_CHARS` | `8000` | History sent to the model per request |

To change the model: set `OLLAMA_MODEL` in `.env`, then `make up && make model`.

## AI Gateway and cloud providers

Cloud providers are **disabled by default**; no data leaves the machine. See
[AI Gateway](../architecture/ai-gateway.md).

| Variable | Default | Purpose |
|---|---|---|
| `AI_PROVIDER_ORDER` | `ollama` | Route and fallback order, e.g. `ollama,bedrock` |
| `AI_MAX_INPUT_CHARS` / `AI_MAX_OUTPUT_TOKENS` | 32000 / 2048 | Hard limits for every provider |
| `AI_TIMEOUT_SECONDS`, `AI_MAX_RETRIES` | 180, 1 | Retries only on unavailability, never on timeout |
| `AI_BREAKER_THRESHOLD`, `AI_BREAKER_COOLDOWN_SECONDS` | 3, 30 | Per-provider circuit breaker |
| `AI_ALLOW_CLOUD`, `AI_CLOUD_MONTHLY_BUDGET_USD`, `AWS_REGION`, `BEDROCK_*`, `SAGEMAKER_ENDPOINT` | unset | **All** required to enable a cloud provider; otherwise the app does not start |

AWS credentials come from the standard AWS role or environment, never from a file in the repository.
The Docker image installs `boto3` only with `docker build --build-arg INSTALL_AWS=1`.

## Security and abuse limits

| Variable | Default | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | `http://127.0.0.1:8001,http://localhost:8001` | Origins accepted on state-changing requests |
| `COOKIE_SECURE` | `false` | Must be `true` behind HTTPS and in production |
| `CHAT_REQUESTS_PER_MINUTE` | `30` | Model requests per user per minute |
| `CHAT_MAX_CONCURRENT`, `CHAT_MAX_CONCURRENT_PER_USER` | 2, 2 | Concurrent generations |
| `MAX_BODY_BYTES` | `2097152` | Maximum request size (2 MiB) |
| `LOGIN_IP_MAX_ATTEMPTS` | per-account limit | Raise to ~50 behind NAT (Compose sets 50) |
| `API_DOCS` | Swagger only in development | `false` disables it (Compose sets `false`) |
| `LOG_LEVEL`, `LOG_FORMAT` | `INFO`, `json` | Structured logs with `request_id` |

## Optional integrations

| Variable | Purpose |
|---|---|
| `OBSIDIAN_VAULT_HOST_PATH` | Host folder mounted **read-only** as the Obsidian vault |
| `OBSIDIAN_ALLOWED_EMAILS` | Accounts, besides administrators, allowed to read the vault |
| `BACKUP_STATUS_PATH` | Status file written by the backup script and shown in Operations |

## Docker Compose

Read by `docker compose` from `.env`, not by the application:

| Variable | Default | Purpose |
|---|---|---|
| `NEXARO_PORT` | `8001` | Local port (always bound to `127.0.0.1`). If you change it, update `ALLOWED_ORIGINS` |
| `COMPOSE_PROFILES` | unset | `ollama` enables the bundled Ollama |
| `OLLAMA_NETWORK` | `ollama-local_default` | `nexaro_ollama` for bundled mode |
| `OLLAMA_IMAGE` | `ollama/ollama:latest` | Pin to a version or digest after the first pull |
| `OLLAMA_MEM_LIMIT` | `6g` | Memory limit of the bundled Ollama |

Related: [Docker deployment](../deployment/docker.md) · [Security](../security/README.md)
