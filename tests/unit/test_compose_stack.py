"""Stack Docker (ADR-0021): Ollama opcional por perfil, sin puertos, con modelos persistentes, y
scripts de arranque y smoke sin operaciones destructivas.

Los tests con `docker compose config` solo necesitan la CLI de Docker (no el daemon) y se omiten
si no está. El funcionamiento real (contenedores, Ollama y el modelo) lo prueba `make smoke`.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
BACKEND = COMPOSE.split("\n  backend:\n", 1)[1].split("\n  ollama:\n", 1)[0]
OLLAMA = COMPOSE.split("\n  ollama:\n", 1)[1].split("\nvolumes:\n", 1)[0]
STACK = ROOT / "scripts" / "stack.sh"
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")

# En Windows, Git Bash va antes que `shutil.which`: System32\bash.exe es el lanzador de WSL.
_GIT_BASH = (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe")


def _find_bash() -> str | None:
    if os.name == "nt":
        for candidate in _GIT_BASH:
            if Path(candidate).is_file():
                return candidate
    found = shutil.which("bash")
    if found:
        return found
    if os.name != "nt" and Path("/bin/bash").is_file():
        return "/bin/bash"
    return None


BASH = _find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="sin bash")


def test_project_name_is_fixed_so_the_data_volume_never_changes() -> None:
    assert re.search(r"^name: nexaro-personal-ai$", COMPOSE, re.MULTILINE)


def test_ollama_is_optional_and_never_published() -> None:
    assert 'profiles: ["ollama"]' in OLLAMA
    assert "ports:" not in OLLAMA and "11434:" not in OLLAMA
    assert re.search(r"aliases:\s+- ollama", OLLAMA)  # misma URL que el Ollama externo


def test_ollama_has_a_real_healthcheck_and_persistent_models() -> None:
    assert 'test: ["CMD", "ollama", "list"]' in OLLAMA  # consulta la API del servidor
    assert "start_period:" in OLLAMA
    assert "- ollama_models:/root/.ollama" in OLLAMA
    assert re.search(r"^volumes:\n  nexaro_data:\n  ollama_models:$", COMPOSE, re.MULTILINE)
    assert "restart: unless-stopped" in OLLAMA


def test_ollama_runs_hardened() -> None:
    for required in ("- ALL", "no-new-privileges:true", "pids_limit:", "mem_limit:", "max-size:"):
        assert required in OLLAMA, required


def test_backend_waits_for_bundled_ollama_only_when_the_profile_is_active() -> None:
    depends = BACKEND.split("depends_on:", 1)[1].split("read_only:", 1)[0]
    assert "condition: service_healthy" in depends
    assert "required: false" in depends  # sin el perfil, el backend arranca solo


def test_network_and_model_are_configurable_with_the_current_defaults() -> None:
    assert 'name: "${OLLAMA_NETWORK:-ollama-local_default}"' in COMPOSE
    assert 'OLLAMA_MODEL: "${OLLAMA_MODEL:-qwen2.5:3b}"' in BACKEND
    assert 'OLLAMA_BASE_URL: "http://ollama:11434"' in BACKEND


def test_data_directory_belongs_to_the_app_user_before_dropping_root() -> None:
    lines = DOCKERFILE.splitlines()
    chown = next(i for i, line in enumerate(lines) if "chown 10001:10001 /data" in line)
    user = next(i for i, line in enumerate(lines) if line.startswith("USER "))
    assert chown < user


def test_make_targets_exist_and_nothing_destroys_volumes() -> None:
    for target in ("up:", "down:", "model:", "model-check:", "smoke:"):
        assert re.search(rf"^{target}", MAKEFILE, re.MULTILINE), target
    assert "scripts/stack.sh preflight" in MAKEFILE and "--wait" in MAKEFILE
    script = STACK.read_text(encoding="utf-8")
    for source in (MAKEFILE, script):
        # Solo código: los comentarios advierten precisamente de «nunca down -v».
        text = "\n".join(ln for ln in source.splitlines() if not ln.lstrip().startswith("#"))
        assert not re.search(r"down\s+(-\w*v|--volumes)", text)
        assert not re.search(r"volume\s+(rm|prune)|system\s+prune|rm\s+-rf", text)


@needs_bash
def test_stack_script_is_valid_bash_3_2_without_newer_features() -> None:
    assert BASH is not None
    script = STACK.read_text(encoding="utf-8")
    result = subprocess.run([BASH, "-n", str(STACK)], capture_output=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stderr
    # macOS trae bash 3.2: nada de arrays asociativos, mapfile, ${x,,} ni |&.
    for pattern in (r"declare -A", r"\bmapfile\b", r"\breadarray\b", r"\$\{\w+,,\}", r"\|&"):
        assert not re.search(pattern, script), pattern
    # Con pipefail, `| grep -q` da falsos negativos por SIGPIPE: se evita a propósito.
    assert "| grep -q" not in script


@needs_bash
def test_stack_script_rejects_unknown_commands() -> None:
    assert BASH is not None
    result = subprocess.run(  # noqa: S603
        [BASH, str(STACK), "otra"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2 and "uso:" in result.stderr


def _compose(*args: str, **env: str) -> subprocess.CompletedProcess[str]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("sin la CLI de Docker")
    probe = subprocess.run([docker, "compose", "version"], capture_output=True, check=False)  # noqa: S603
    if probe.returncode != 0:
        pytest.skip("sin docker compose")
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "OLLAMA_"))}
    return subprocess.run(  # noqa: S603
        # --env-file vacío: el .env local (p. ej. con COMPOSE_PROFILES) no altera el resultado.
        [docker, "compose", "--env-file", os.devnull, "-f", str(ROOT / "compose.yaml"), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**clean, **env},
        cwd=ROOT,
    )


def test_compose_config_default_mode_runs_only_the_backend() -> None:
    result = _compose("config", "--services")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["backend"]


def test_compose_config_bundled_mode_adds_ollama_on_its_own_network() -> None:
    result = _compose("config", COMPOSE_PROFILES="ollama", OLLAMA_NETWORK="nexaro_ollama")
    assert result.returncode == 0, result.stderr
    assert "container_name: nexaro-ollama" in result.stdout
    assert "name: nexaro_ollama" in result.stdout
    assert result.stdout.count("published:") == 1  # solo 127.0.0.1:8001 del backend
    assert "host_ip: 127.0.0.1" in result.stdout
    services = _compose("config", "--services", COMPOSE_PROFILES="ollama").stdout.split()
    assert sorted(services) == ["backend", "ollama"]
