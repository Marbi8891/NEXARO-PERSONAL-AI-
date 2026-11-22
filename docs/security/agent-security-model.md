# Agent security model

## Trust boundaries

User prompts, documents, repository files, retrieved chunks, model output, and tool output are untrusted. None may override backend policy.

## Default-deny permissions

New agents start with filesystem disabled or read-only access to explicitly configured workspace roots, terminal disabled, network disabled, Git read-only, Docker status read-only, workspace memory only when enabled, and approval required for writes and destructive actions.

## Enforcement

The server validates permissions before dispatching a tool. A system prompt is not an authorization mechanism. The model cannot grant itself permissions, add tools, alter approval policy, or expand filesystem roots.

## Filesystem

- Resolve paths against configured workspace roots.
- Reject path traversal and symlink escapes.
- Enforce file-size and total-read limits.
- Deny environment files, SSH keys, browser profiles, credential stores, and application secrets by default.
- Never mount the whole host filesystem into the backend container.

## Tool execution

Do not expose arbitrary shell execution or a generic command runner. Use narrow typed operations, strict schemas, per-tool timeouts, output limits and rate limits. Audit tool name, redacted arguments, approval, outcome and duration.

## Approval lifecycle

An approval request records the exact action, targets, normalized arguments, risk, expiry, requesting agent and workspace. The user approves that exact action. Changed arguments invalidate approval. Expired or rejected approvals never execute.

## Prompt injection

Treat documents, web pages, code comments and retrieved text as data, not instructions. Delimit retrieved context and preserve provenance. Retrieved text cannot change system policy or permissions.

## Network

Network access is disabled by default. A future research tool must validate allowed domains, redirects, DNS/IP targets, response sizes and timeouts. Never create an arbitrary URL proxy.

## Secrets and logging

Load secrets from environment or a secret manager. Never log credentials or private document contents. Do not commit .env files, databases, logs, backups or uploads.

## Tests

Cover permission denial, path traversal, symlink escape, expired approvals, altered arguments, prompt injection, oversized output, timeouts and cross-workspace isolation.
