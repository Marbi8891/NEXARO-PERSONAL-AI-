import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prune_backups.sh"

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
pytestmark = pytest.mark.skipif(BASH is None, reason="sin bash")


def run(directory: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), "--dir", str(directory), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def make(directory: Path) -> None:
    for stamp in ("20261101-000001", "20261102-000001", "20261103-000001", "20261104-000001"):
        (directory / f"nexaro.pre-rebuild-{stamp}.db").write_bytes(b"x")
    (directory / "nexaro-pre-auth-migration-20261108.db").write_bytes(b"original")
    (directory / "notas.txt").write_text("no tocar")


def test_dry_run_deletes_nothing(tmp_path: Path) -> None:
    make(tmp_path)
    result = run(tmp_path, "--keep", "2")
    assert result.returncode == 0 and "simulación" in result.stdout
    assert len(list(tmp_path.glob("nexaro.pre-rebuild-*.db"))) == 4


def test_apply_keeps_newest_and_never_touches_the_original_backup(tmp_path: Path) -> None:
    make(tmp_path)
    result = run(tmp_path, "--keep", "2", "--apply")
    assert result.returncode == 0
    left = sorted(p.name for p in tmp_path.glob("nexaro.pre-rebuild-*.db"))
    assert left == [
        "nexaro.pre-rebuild-20261103-000001.db",
        "nexaro.pre-rebuild-20261104-000001.db",
    ]
    assert (tmp_path / "nexaro-pre-auth-migration-20261108.db").read_bytes() == b"original"
    assert (tmp_path / "notas.txt").exists()


def test_rejects_bad_arguments_and_missing_directory(tmp_path: Path) -> None:
    assert run(tmp_path, "--keep", "0").returncode == 2
    assert run(tmp_path, "--keep", "abc").returncode == 2
    assert run(tmp_path / "no-existe").returncode == 2
    assert "nada que podar" in run(tmp_path, "--keep", "5").stdout
