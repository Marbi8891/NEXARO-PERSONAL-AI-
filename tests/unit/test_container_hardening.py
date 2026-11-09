"""El endurecimiento del contenedor es parte del repositorio: estos tests evitan que se pierda."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_backend_runs_with_minimal_privileges() -> None:
    for required in ("read_only: true", "no-new-privileges:true", "- ALL", "pids_limit:"):
        assert required in COMPOSE, required
    assert re.search(r"^\s+mem_limit:\s*\S+", COMPOSE, re.MULTILINE)
    assert re.search(r"^\s+cpus:\s*[\d.]+", COMPOSE, re.MULTILINE)
    assert "privileged" not in COMPOSE and "network_mode" not in COMPOSE
    assert "docker.sock" not in COMPOSE


def test_only_localhost_port_and_no_secrets_in_compose() -> None:
    ports = re.findall(r'^\s+- "([^"]+:\d+:\d+)"', COMPOSE, re.MULTILINE)
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)
    assert not re.search(r"(PASSWORD|SECRET|TOKEN|API_KEY)\s*:\s*\"?[^\s\"$]", COMPOSE)


def test_logs_are_rotated() -> None:
    assert "max-size:" in COMPOSE and "max-file:" in COMPOSE


def test_image_is_pinned_by_digest_and_runs_as_non_root() -> None:
    assert re.search(r"^FROM python:[\w.\-]+@sha256:[0-9a-f]{64}$", DOCKERFILE, re.MULTILINE)
    assert "USER 10001:10001" in DOCKERFILE
    assert "HEALTHCHECK" in DOCKERFILE


def test_data_volume_is_the_only_writable_mount() -> None:
    mounts = re.findall(r"^\s+- (\S+:/\S+)$", COMPOSE, re.MULTILINE)
    assert any(m.startswith("nexaro_data:/data") for m in mounts)
    others = [m for m in mounts if not m.startswith("nexaro_data:")]
    assert all(m.endswith(":ro") for m in others), others  # p. ej. ./frontend:/app/frontend:ro
