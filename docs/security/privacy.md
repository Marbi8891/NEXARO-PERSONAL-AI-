# Privacy

How NEXARO handles personal data in a default self-hosted installation. This describes the software's
behaviour; it is not a legal privacy policy for any particular deployment.

← [Security](README.md)

## Where data lives

| Data | Location | Leaves the host? |
|---|---|---|
| Accounts, sessions (hashed), conversations, documents, prompts, agents, expenses | SQLite file in the `nexaro-personal-ai_nexaro_data` Docker volume | No |
| Model weights and inference | Ollama, on the same host | No |
| Audit log | Same database, append-only, e-mail pseudonymised | No |
| Application logs | Docker JSON logs, rotated (10 MB × 5) | No |
| Backups | Wherever you store them (outside the repository) | Only if you copy them |
| Obsidian vault (optional) | Your host folder, mounted read-only | No |

## Defaults that protect privacy

- **No cloud inference.** Prompts and documents are sent only to the local Ollama unless an operator
  sets `AI_ALLOW_CLOUD=true` with a provider and a monthly budget.
- **No telemetry.** NEXARO does not send analytics or usage data anywhere.
- **Self-hosted fonts and assets.** The UI loads nothing from third-party CDNs.
- **Minimal exposure.** Only `127.0.0.1` is published; Ollama is on a private network.
- **Restricted visibility.** Users see only their own conversations and agents; organization data
  requires membership; the security summary shows failed-login IPs only to administrators and never
  shows e-mails.

## If you enable a cloud provider

Prompts, conversation history sent as context, and retrieved document passages for those requests are
sent to the configured AWS service in your account and region. Review the provider's data-handling
terms before enabling it.

## Operator responsibilities

- Encrypt the disk that holds the Docker volumes and backups (e.g. BitLocker, FileVault, LUKS).
- Keep backups outside the repository; they contain the same data as the database.
- Do not include real data in screenshots, issues or logs you share.
- When enabling remote access, use a private network layer (Tailscale Serve, never Funnel) and
  `COOKIE_SECURE=true`.
