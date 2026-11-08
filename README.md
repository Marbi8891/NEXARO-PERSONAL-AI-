# NEXARO Personal AI

Local-first personal AI assistant built around Ollama, FastAPI, SQLite and Docker.

> **Project status:** under active development. This repository currently contains the initial project documentation. The application source code has not yet been published here.

## Overview

NEXARO Personal AI is being developed as a self-hosted assistant. The intended design keeps the language model and application data under the operator's control rather than depending on a hosted AI API for inference.

## Planned technology stack

- **Backend:** Python and FastAPI
- **Frontend:** HTML, CSS and JavaScript (ES modules)
- **Local inference:** Ollama
- **Data storage:** SQLite
- **Service orchestration:** Docker Compose

The exact implementation and supported deployment configuration will be documented after the source code is reviewed and added.

## Development stages

1. Establish the application structure and local development workflow.
2. Document and verify the backend, frontend, database and Ollama integration.
3. Review authentication, authorization and user-data isolation.
4. Add automated tests and deployment instructions.
5. Prepare a reproducible demonstration using synthetic data.

Features that are not verified in the published repository should be considered planned or in progress, not production-ready.

## Security and privacy

- Never commit `.env` files, API keys, passwords, session tokens or private certificates.
- Never publish the live SQLite database, conversation history, logs containing personal data, or backups.
- Do not expose Ollama or the SQLite database directly to the public internet.
- Use synthetic data for demonstrations and screenshots.
- Review every change before publishing it.

See [SECURITY.md](SECURITY.md) for reporting guidance and [docs/architecture.md](docs/architecture.md) for the current architectural outline.

## Development setup

The application source and verified setup instructions will be added after a local security review. Until then, this repository is a documentation baseline and does not yet provide a runnable installation.

## License

No license has been added yet. Unless a license is added, the repository's contents are not granted for reuse by default.
