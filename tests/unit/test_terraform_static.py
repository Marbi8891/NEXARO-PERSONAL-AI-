"""Comprobaciones estáticas de la infraestructura (no sustituyen a `terraform validate`/`plan`).

Cubren los fallos de cableado más habituales y las reglas de seguridad del proyecto. El CI ejecuta
además `terraform validate` real por entorno, donde sí hay acceso al registro de proveedores.
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

hcl2 = pytest.importorskip("hcl2")

TF_ROOT = Path(__file__).resolve().parents[2] / "infrastructure/aws/terraform"
MODULES = TF_ROOT / "modules"
ENVS = TF_ROOT / "envs"


def tf_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.tf"))


def parse(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        parsed: dict[str, Any] = hcl2.load(handle)
    return parsed


def unquote(value: object) -> str:
    return str(value).strip('"')


def module_interface(directory: Path) -> tuple[dict[str, bool], set[str]]:
    """(variables -> ¿obligatoria?, outputs) de un módulo."""
    variables: dict[str, bool] = {}
    outputs: set[str] = set()
    for path in tf_files(directory):
        if path.parent != directory:
            continue
        parsed = parse(path)
        for block in parsed.get("variable", []):
            for name, body in block.items():
                variables[unquote(name)] = "default" not in body
        for block in parsed.get("output", []):
            outputs.update(unquote(name) for name in block if not name.startswith("__"))
    return variables, outputs


def module_calls(directory: Path) -> list[tuple[str, str, dict[str, Any]]]:
    calls = []
    for path in tf_files(directory):
        if path.parent != directory:
            continue
        for block in parse(path).get("module", []):
            for name, body in block.items():
                calls.append((unquote(name), unquote(body["source"]), body))
    return calls


def call_sites() -> list[Path]:
    return [MODULES / "stack", *sorted(p for p in ENVS.iterdir() if p.is_dir())]


def test_there_is_infrastructure_to_check() -> None:
    assert len(tf_files(TF_ROOT)) > 30
    assert {p.name for p in ENVS.iterdir()} == {"dev", "staging", "prod"}


def test_every_file_parses() -> None:
    for path in tf_files(TF_ROOT):
        parse(path)


@pytest.mark.parametrize("site", call_sites(), ids=lambda p: p.name)
def test_module_calls_match_the_module_interface(site: Path) -> None:
    calls = module_calls(site)
    assert calls
    for name, source, body in calls:
        variables, _ = module_interface((site / source).resolve())
        passed = {k for k in body if not k.startswith("__")} - {
            "source",
            "depends_on",
            "count",
            "for_each",
            "providers",
        }
        assert passed <= variables.keys(), (
            f"{site.name}.{name}: argumentos inexistentes {passed - variables.keys()}"
        )
        missing = {v for v, required in variables.items() if required} - passed
        assert not missing, f"{site.name}.{name}: faltan variables obligatorias {missing}"


@pytest.mark.parametrize("site", call_sites(), ids=lambda p: p.name)
def test_module_output_references_exist(site: Path) -> None:
    text = "\n".join(p.read_text() for p in tf_files(site) if p.parent == site)
    sources = {name: (site / source).resolve() for name, source, _ in module_calls(site)}
    for module_name, output in re.findall(r"module\.(\w+)\.(\w+)", text):
        assert module_name in sources, f"{site.name}: módulo desconocido {module_name}"
        assert output in module_interface(sources[module_name])[1], (
            f"{site.name}: {module_name} no tiene el output {output}"
        )


def test_environments_use_all_their_inputs() -> None:
    stack_vars, _ = module_interface(MODULES / "stack")
    for env in ENVS.iterdir():
        env_vars, _ = module_interface(env)
        text = (env / "main.tf").read_text()
        for variable in env_vars:
            assert f"var.{variable}" in text, f"{env.name}: var.{variable} sin usar"
    assert stack_vars["desired_count"] is False  # tiene valor por defecto seguro (0)


def test_wildcards_require_an_explicit_justification() -> None:
    offenders = []
    for path in tf_files(MODULES):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'"\*"|"[a-z0-9]+:\*"', line) and "allow-wildcard" not in line:
                offenders.append(f"{path.relative_to(TF_ROOT)}:{number}: {line.strip()}")
    assert offenders == []


def test_no_literal_secrets_in_infrastructure() -> None:
    pattern = re.compile(r"^\s*(password|master_password|secret_key|access_key|token)\s*=", re.M)
    for path in tf_files(TF_ROOT):
        assert not pattern.search(path.read_text()), path
    for path in TF_ROOT.rglob("*.tfvars"):
        pytest.fail(f"tfvars real en el repositorio: {path}")


def test_every_bucket_blocks_public_access_and_is_encrypted() -> None:
    for path in tf_files(MODULES):
        text = path.read_text()
        buckets = len(re.findall(r'resource "aws_s3_bucket" ', text))
        assert buckets == len(re.findall(r'resource "aws_s3_bucket_public_access_block"', text)), (
            path
        )
        assert buckets == len(
            re.findall(r'resource "aws_s3_bucket_server_side_encryption_configuration"', text)
        ), path


def test_database_uses_managed_secret_and_encryption() -> None:
    text = (MODULES / "database/main.tf").read_text()
    assert (
        "manage_master_user_password   = true" in text.replace("  ", " ")
        or "manage_master_user_password" in text
    )
    assert re.search(r"storage_encrypted\s*=\s*true", text)
    assert not re.search(r"master_password", text)


def test_app_is_https_only_and_not_deployed_by_default() -> None:
    app = (MODULES / "app/main.tf").read_text()
    assert 'type = "redirect"' in app.replace("  ", " ") or 'type = "redirect"' in app
    assert "TLS13" in app
    variables = (MODULES / "app/variables.tf").read_text()
    assert re.search(r'variable "desired_count"[^}]*default\s*=\s*0', variables, re.S)
    for env in ENVS.iterdir():
        assert re.search(r"desired_count\s*=\s*0", (env / "main.tf").read_text()), env.name


def test_task_role_has_no_blanket_permissions() -> None:
    app = (MODULES / "app/main.tf").read_text()
    assert "bedrock:*" not in app and "s3:*" not in app and "sagemaker:*" not in app
    assert "var.bedrock_model_arns" in app  # solo ARNs explícitos


def test_production_is_protected_and_audited() -> None:
    prod = (ENVS / "prod/main.tf").read_text()
    for setting in (
        "deletion_protection  = true",
        "enable_cloudtrail     = true",
        "enable_guardduty      = true",
    ):
        assert setting in prod, setting
    assert "force_destroy_buckets = false" in prod
    for env in ENVS.iterdir():
        text = (env / "main.tf").read_text()
        assert 'backend "s3"' in text and "default_tags" in text, env.name


@pytest.mark.skipif(
    not (shutil.which("tofu") or shutil.which("terraform")), reason="sin tofu/terraform"
)
def test_formatting_is_canonical() -> None:
    binary = shutil.which("tofu") or shutil.which("terraform")
    assert binary
    result = subprocess.run(  # noqa: S603
        [binary, "fmt", "-check", "-recursive", str(TF_ROOT)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout
