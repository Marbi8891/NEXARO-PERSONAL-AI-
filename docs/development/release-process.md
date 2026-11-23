# Release process

← [Testing](testing.md) · [Documentation home](../README.md)

NEXARO uses [Semantic Versioning](https://semver.org/). The version lives in `pyproject.toml`
(`[project].version`) and every release has an entry in [CHANGELOG.md](../../CHANGELOG.md).

## 1. Prepare

1. All work for the release is merged into `main`, and CI on `main` is green.
2. Update `pyproject.toml` `version`.
3. In `CHANGELOG.md`, rename the `[Unreleased]` section to `[X.Y.Z] — YYYY-MM-DD`.
4. For a major or minor release, write release notes in `docs/releases/vX.Y-notes.md` and run the
   release checklist (model: [v1.0 checklist](../releases/v1.0-checklist.md)).
5. Open a pull request `release: vX.Y.Z` and merge it after review.

## 2. Verify on real infrastructure

The CI cannot run a real model. Before tagging, on a machine with Docker and Ollama:

```bash
make up && make model && make smoke     # must end with SMOKE OK
```

Back up production data first ([backup-restore.md](../deployment/backup-restore.md)).

## 3. Tag

```bash
git checkout main && git pull
git tag -a vX.Y.Z -m "NEXARO vX.Y.Z"
git push origin vX.Y.Z
```

## 4. Automated release

Pushing a `v*.*.*` tag runs [`.github/workflows/release.yml`](../../.github/workflows/release.yml), which:

1. Fails if the tag does not match the `pyproject.toml` version.
2. Runs lint, type checking and the full test suite (PostgreSQL tests mandatory).
3. Builds the Docker image and scans it with Trivy (fails on fixable HIGH/CRITICAL).
4. Generates a CycloneDX SBOM.
5. Creates the GitHub Release with the matching `CHANGELOG.md` section as notes and the SBOM attached.

No image is pushed to a registry: NEXARO is built from source on the target machine.

## 5. After the release

- Deploy following [Docker deployment](../deployment/docker.md#upgrades-and-migrations).
- Add a new `[Unreleased]` section to `CHANGELOG.md`.
