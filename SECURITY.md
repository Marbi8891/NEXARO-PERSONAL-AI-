# Security Policy

## Scope

NEXARO Personal AI is under active development. Do not assume that an unpublished or undocumented security control is already implemented.

## Reporting a vulnerability

Please do not publish credentials, private conversation data, database files, or exploit details in a public issue.

Use GitHub's private vulnerability reporting feature for this repository if it is enabled. If private reporting is unavailable, contact the repository owner privately before sharing technical details.

## Responsible disclosure

When reporting an issue, include:

- A concise description of the affected component.
- The impact and conditions required to reproduce it.
- A minimal proof of concept that does not access another person's data.
- Any suggested mitigation, if known.

Do not test against systems or data that you do not own or have explicit permission to assess.

## Release hygiene

Before publishing application code:

- Remove real environment files, credentials, tokens and private keys.
- Exclude SQLite databases, backups, logs and personal conversation data.
- Check Git history for accidentally committed secrets.
- Use synthetic data in examples and demonstrations.
- Keep Ollama and database services off public interfaces unless a reviewed design explicitly requires otherwise.
