# NEXARO documentation

← [Back to the repository](../README.md)

The guides below are in English. The detailed references marked **ES** are in Spanish: the project's
working language, kept as the source of truth for operational detail.

## Getting started

| | |
|---|---|
| [Installation](getting-started/installation.md) | Requirements, Ollama modes, `make up`, first administrator |
| [Quick start](getting-started/quick-start.md) | First chat, agents, documents and prompts |
| [Configuration](getting-started/configuration.md) | Every environment variable that matters |
| [Troubleshooting](getting-started/troubleshooting.md) | Symptoms, causes, fixes |

## Product

| | |
|---|---|
| [Capability matrix](product/capabilities.md) | What is implemented, partial, experimental or planned |
| [Roadmap](../ROADMAP.md) | Direction and priorities |
| [Product overview](product/overview.md) · **ES** | Goals, users, roles, scope |
| [User guide](product/user-guide.md) · **ES** | Every screen in detail |
| [Brand identity](product/brand.md) | Name, voice, logo, colours |
| [Brand architecture](product/brand-architecture.md) · [Design system](product/design-system.md) | Product family and UI rules |
| [Implementation status (MVP evidence)](product/implementation-status.md) · **ES** | Historical step-by-step evidence |

## Architecture

| | |
|---|---|
| [Architecture overview](architecture/overview.md) | Context, layers, request flow, data |
| [AI Gateway](architecture/ai-gateway.md) | Providers, routing, limits, privacy guarantees |
| [Agents](architecture/agents.md) | Agent model, safety rules, tools, evolution |
| [Module reference](architecture/modules.md) · **ES** | Responsibilities of each module |
| [API reference](architecture/api-reference.md) · **ES** | HTTP routes, auth, permissions, errors |
| [Target architecture](architecture/target-architecture.md) | Planned agent runtime, orchestrator, memory |
| [Agent catalogue](agents/catalogue.md) | Proposed agent definitions (design artefact) |
| [Obsidian integration](integrations/obsidian.md) | Read-only vault connector |

## Security

| | |
|---|---|
| [Security overview](security/README.md) | Principles, controls, known limits, detailed documents |
| [Privacy](security/privacy.md) | Where data lives and what can leave the host |
| [Reporting a vulnerability](../SECURITY.md) | Private disclosure |
| [Audits](security/audits/) · **ES** | v1.0 audit and security review, auth audit, repository audit |

## Deployment and operations

| | |
|---|---|
| [Docker deployment](deployment/docker.md) | Services, hardening, lifecycle, upgrades |
| [Deployment reference](deployment/deployment-reference.md) · **ES** | Windows permanent deployment, tuning, AWS |
| [Operations](deployment/operations.md) · **ES** | Monitoring, persistence, troubleshooting |
| [Backup and restore](deployment/backup-restore.md) · **ES** | Verified backups and restore drills |
| [Remote access](deployment/remote-access.md) · **ES** | Private access with Tailscale Serve |
| [AWS costs](deployment/aws-costs.md) | Estimate for the (unapplied) Terraform |

## Development

| | |
|---|---|
| [Development setup](development/setup.md) | Environment, layout, conventions |
| [Testing](development/testing.md) | Suites, commands, expected skips |
| [Release process](development/release-process.md) | Versioning, tagging, automated release |
| [Development reference](development/reference.md) · **ES** | Windows tests, frontend, evaluation details |
| [AI evaluation](development/ai-evaluation.md) · **ES** | Reproducible model-quality evaluation |
| [Quality report](development/quality-report.md) · **ES** | Professional quality review |
| [Contributing](../CONTRIBUTING.md) | How to propose changes |

## Decisions and history

| | |
|---|---|
| [Architecture Decision Records](decisions/README.md) | 25 ADRs, one per significant decision |
| [Changelog](../CHANGELOG.md) | Version history |
| [v1.0 release notes](releases/v1.0-notes.md) · [v1.0 checklist](releases/v1.0-checklist.md) · **ES** | Release evidence |
| [Assets and screenshots](assets/README.md) | Logo files and screenshot plan |

## Conventions

- Documentation states only what the code does. Planned work is labelled as such.
- Never paste real secrets, cookies, keys or personal data into docs, issues or screenshots.
- The API inventory lives only in the API reference; other pages link to it instead of copying it.
