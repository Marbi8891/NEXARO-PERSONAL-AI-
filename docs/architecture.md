# Architecture

## Status

This document describes the intended local architecture based on the current project design. It is not a substitute for reviewing the implementation. Components, ports, environment variables and network rules must be checked against the actual source and Compose files before being treated as definitive.

## Components

| Component | Technology | Responsibility |
|---|---|---|
| Web client | HTML, CSS, JavaScript ES modules | User interface |
| API | Python, FastAPI | Application endpoints and business logic |
| Local model runtime | Ollama | Local language-model inference |
| Persistence | SQLite | Application and conversation data |
| Service orchestration | Docker Compose | Local service lifecycle |

## Intended request flow

1. The browser sends application requests to the FastAPI backend.
2. The backend validates the request and applies authentication and authorization checks.
3. When a request needs language-model inference, the backend communicates with Ollama over a private service network.
4. Application data is stored in SQLite through backend-controlled operations.
5. The backend returns the result to the browser.

## Security boundaries

- The browser must not connect directly to SQLite.
- Ollama should remain on a private/local network and should not be exposed publicly by default.
- Authentication and authorization must be enforced by the backend, not only by frontend controls.
- Conversation queries must be scoped to the authenticated user.
- Secrets and live user data must remain outside version control.
- Remote access, if enabled, should use a private access layer and should not expose internal service ports.

## Items to verify before release

- Actual Compose services, networks, volumes and published ports.
- Configuration and secret-management approach.
- Session lifecycle, cookie settings, CSRF protections and rate limits.
- User approval and role-management behavior.
- Database initialization and migration procedure.
- Automated test coverage and backup/restore procedure.
