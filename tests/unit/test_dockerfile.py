"""El contenedor no corre como root: el código copiado debe ser legible por su usuario."""

from pathlib import Path

DOCKERFILE = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text().splitlines()


def test_app_is_made_readable_before_dropping_privileges() -> None:
    lines = [line.strip() for line in DOCKERFILE]
    chmod = next(i for i, line in enumerate(lines) if "chmod -R a+rX /app" in line)
    copy = max(i for i, line in enumerate(lines) if line.startswith("COPY apps/api"))
    user = next(i for i, line in enumerate(lines) if line.startswith("USER "))
    assert copy < chmod < user
