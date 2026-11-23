# Security

NEXARO is designed for **private, self-hosted** use. This page summarises the security model and links
to the detailed material. To report a vulnerability, see [SECURITY.md](../../SECURITY.md).

← [Documentation home](../README.md) · [Privacy](privacy.md)

## Principles

1. **Local by default.** The backend binds to `127.0.0.1`; Ollama has no published port; cloud inference
   is off unless explicitly enabled with a budget.
2. **Deny by default.** No default accounts, no public registration, manual approval of new accounts,
   Swagger disabled in Docker.
3. **Enforce in code, not in prompts.** Authorization, tenant isolation, agent tool permissions and
   limits are server-side checks with tests.
4. **Fail fast.** Unsafe configuration or a failed migration stops startup rather than running degraded.
5. **Everything auditable.** Append-only audit log; structured logs with `request_id`.

## Controls (implemented and tested)

| Area | Controls |
|---|---|
| Authentication | scrypt password hashing; 256-bit opaque session tokens (only SHA-256 stored); `HttpOnly`, `SameSite=Strict` cookies, `Secure` required in production; login rate limits per account and per IP with constant-time failure path; password change revokes other sessions |
| Authorization | Role and permission checks per organization; membership required (`404` for non-members, even platform admins); last administrator protected |
| Tenant isolation | `organization_id NOT NULL` + composite foreign keys; schema test fails if a new table breaks the rule; RLS in the PostgreSQL DDL |
| Web | `Origin` validation on state-changing requests; strict CSP (`script-src 'self'`, no inline code); no `innerHTML`/`eval` (enforced by a test); `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, HSTS with secure cookies; `Cache-Control: no-store` on the API |
| Abuse | Per-user model request rate, concurrency caps, request body limit (`413`), per-key API rate limit |
| AI | Restricted-topics guard; document passages neutralised before entering the prompt; agent instructions delimited after platform rules; agent tools ⊆ base agent tools; `agent.tool` audit events |
| API keys | 256-bit keys, only the hash stored, shown once, scoped, expiring, revocable, invalid when the creator loses membership |
| Audit | Append-only (database triggers block `UPDATE`/`DELETE`), pseudonymised e-mail, sensitive keys redacted |
| Container | Non-root (uid 10001), read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, memory/CPU/PID limits, base image pinned by digest |
| Supply chain (CI) | `pip-audit`, Bandit, gitleaks (checksum-verified binary), Trivy image and IaC scans, CycloneDX SBOM, pinned dependency versions |

## Known limits

- Login and API-key rate limiters are in-process memory: not shared across instances.
- Sessions last 7 days with no idle timeout.
- No forgotten-password recovery (no outbound e-mail); password change with the current password exists.
- Row Level Security exists only in the PostgreSQL DDL; the app currently runs on SQLite.
- Remote access via Tailscale Serve is prepared but not activated; when enabled, set `COOKIE_SECURE=true`.

## Detailed documents

| Document | Language | Content |
|---|---|---|
| [Threat model](THREAT_MODEL.md) | ES | Assets, trust boundaries, threats |
| [Security baseline](SECURITY_BASELINE.md) | ES | Deployment checklist with verification commands |
| [Agent security model](agent-security-model.md) | EN | Rules for agents and tools |
| [Conversation isolation](CONVERSATION_ISOLATION.md) | ES | Ownership checks and tests |
| [Security tests](SECURITY_TESTS.md) | ES | What the `tests/security` suite covers |
| [Incident response](INCIDENT_RESPONSE.md) | ES | What to do if something goes wrong |
| [Security audit (2026-11-09)](SECURITY_AUDIT.md) and [remediation](REMEDIATION_REPORT.md) | ES | Findings and fixes with tests |
| [Audits](audits/) | ES | v1.0 audit, v1.0 security review, auth audit, repository audit |
