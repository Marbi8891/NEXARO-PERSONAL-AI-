"""Evaluación de calidad: casos válidos, puntuación determinista y un Ollama falso."""

import importlib.util
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from products.personal_ai.prompts import build_system_prompt

SPEC = importlib.util.spec_from_file_location(
    "quality_eval", Path(__file__).resolve().parents[2] / "scripts/quality_eval.py"
)
assert SPEC and SPEC.loader
qe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qe)

CASES = {c["id"]: c for c in qe.load_cases(qe.DEFAULT_CASES)}

# Soluciones correctas escritas a mano: si los asserts de un caso estuvieran mal, todos los modelos
# fallarían ese caso y el informe mentiría.
REFERENCE = {
    "py-iban": """
def es_iban_es_valido(iban: str) -> bool:
    iban = iban.replace(" ", "").upper()
    if len(iban) != 24 or not iban.startswith("ES") or not iban[2:].isdigit():
        return False
    moved = iban[4:] + "1428" + iban[2:4]
    return int(moved) % 97 == 1
""",
    "py-nif": """
def letra_dni(numero: int) -> str:
    return "TRWAGMYFPDXBNJZSQVHLCKE"[numero % 23]
""",
    "py-agrupar": """
def agrupar_por(items, clave):
    grupos = {}
    for item in items:
        if clave in item:
            grupos.setdefault(item[clave], []).append(item)
    return grupos
""",
    "py-bug": """
def media(valores):
    return sum(valores) / len(valores) if valores else 0.0
""",
}


def fenced(code: str, lang: str = "python") -> str:
    return f"Aquí tienes la solución:\n\n```{lang}\n{code}\n```\n"


@pytest.fixture
def sandbox() -> None:
    """Las pruebas que ejecutan código de verdad necesitan Docker y la imagen del sandbox."""
    problem = qe.sandbox_problem()
    if problem:
        pytest.skip(f"sin sandbox Docker: {problem}")


def test_cases_file_is_valid_and_covers_every_category() -> None:
    assert len(CASES) >= 30
    per_category: dict[str, int] = {}
    for case in CASES.values():
        per_category[case["category"]] = per_category.get(case["category"], 0) + 1
    assert set(per_category) == qe.CATEGORIES
    assert min(per_category.values()) >= 2


@pytest.mark.parametrize(
    "case",
    [
        {"id": "a", "category": "python", "prompt": "x", "otra": 1},
        {"id": "a", "category": "inventada", "prompt": "x"},
        {"id": "a", "category": "python"},
        {"id": "a", "category": "python", "prompt": "x", "messages": []},
    ],
)
def test_malformed_cases_are_rejected(tmp_path: Path, case: dict[str, Any]) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([case]))
    with pytest.raises(ValueError):
        qe.load_cases(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    case = {"id": "a", "category": "python", "prompt": "x"}
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([case, case]))
    with pytest.raises(ValueError, match="repetido"):
        qe.load_cases(path)


@pytest.mark.parametrize("case_id", sorted(REFERENCE))
def test_reference_solutions_satisfy_their_asserts(case_id: str) -> None:
    # Código escrito a mano (no generado): se puede ejecutar aquí, sin Docker.
    namespace: dict[str, Any] = {}
    exec(REFERENCE[case_id], namespace)  # noqa: S102
    exec(CASES[case_id]["python_tests"], namespace)  # noqa: S102


@pytest.mark.usefixtures("sandbox")
@pytest.mark.parametrize("case_id", sorted(REFERENCE))
def test_reference_solutions_pass_their_case_in_the_sandbox(case_id: str) -> None:
    checks = qe.grade(CASES[case_id], fenced(REFERENCE[case_id]), run_code=True)
    assert [c for c in checks if not c.passed] == []


def test_every_python_case_with_tests_has_a_reference_solution() -> None:
    assert {k for k, c in CASES.items() if "python_tests" in c} == set(REFERENCE)


@pytest.mark.usefixtures("sandbox")
def test_wrong_code_fails_and_reports_the_assertion() -> None:
    wrong = "def letra_dni(numero):\n    return 'A'"
    check = qe.run_python(wrong, CASES["py-nif"]["python_tests"])
    assert not check.passed and "AssertionError" in check.detail


@pytest.mark.usefixtures("sandbox")
def test_code_is_imported_so_its_main_block_and_input_do_not_run() -> None:
    code = "def doble(x):\n    return 2 * x\n\nif __name__ == '__main__':\n    input('n: ')\n"
    assert qe.run_python(code, "assert doble(2) == 4").passed


def test_untagged_block_is_used_only_when_there_is_no_python_block() -> None:
    assert qe.python_code("```\nx = 1\n```") == "x = 1\n"
    answer = "```bash\npip install x\n```\n```python\ny = 2\n```"
    assert qe.python_code(answer) == "y = 2\n"
    assert not qe.run_python("", "assert True").passed


class FakeDocker:
    """Sustituye a subprocess.run: registra cada orden y nunca ejecuta nada."""

    def __init__(self, *, inspect_rc: int = 0, run_rc: int = 0, timeout: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.inspect_rc, self.run_rc, self.timeout = inspect_rc, run_rc, timeout
        self.workdir: Path | None = None

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        rc = 0
        if argv[1:3] == ["image", "inspect"]:
            rc = self.inspect_rc
        elif argv[1] == "run":
            mount = argv[argv.index("--mount") + 1]
            self.workdir = Path(mount.split("source=")[1].split(",")[0])
            assert (self.workdir / "solution.py").is_file()
            if self.timeout:
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            rc = self.run_rc
        return subprocess.CompletedProcess(argv, rc, "", "Cannot connect to the Docker daemon")

    def runs(self) -> list[list[str]]:
        return [c for c in self.calls if c[1] == "run"]


def test_sandbox_command_isolates_the_generated_code(tmp_path: Path) -> None:
    argv = qe.sandbox_command("docker", "nexaro-eval-x", tmp_path)
    flags = " ".join(argv)
    for expected in [
        "--rm", "--network none", "--read-only", "--cap-drop ALL",
        "--security-opt no-new-privileges", "--memory 256m", "--memory-swap 256m", "--cpus 1",
        "--pids-limit 64", "--pull never", "--user 65534:65534",
        f"type=bind,source={tmp_path},target=/sandbox,readonly",
    ]:  # fmt: skip
        assert expected in flags
    assert "-v" not in argv and "--volume" not in argv and "--privileged" not in argv
    assert str(qe.ROOT) not in flags  # el repositorio no se monta
    assert sys.executable not in argv
    assert argv[argv.index(qe.SANDBOX_IMAGE) + 1 :][:4] == [
        "timeout",
        "-k",
        "1",
        str(qe.CODE_TIMEOUT_SECONDS),
    ]


def test_without_docker_nothing_is_executed(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("no debe lanzar ningún proceso")

    monkeypatch.setattr(qe.shutil, "which", lambda name: None)
    monkeypatch.setattr(qe.subprocess, "run", forbidden)
    check = qe.run_python("def f():\n    return 1", "assert f() == 1")
    assert not check.passed and "Docker no está instalado" in check.detail


def test_with_docker_down_only_the_inspect_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeDocker(inspect_rc=1)
    monkeypatch.setattr(qe.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(qe.subprocess, "run", fake)
    check = qe.run_python("x = 1", "assert x == 1")
    assert not check.passed and "Docker no disponible" in check.detail
    assert "docker pull" in check.detail
    assert fake.runs() == [] and len(fake.calls) == 1


def test_code_runs_only_through_docker_and_is_cleaned_up(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeDocker()
    monkeypatch.setattr(qe.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(qe.subprocess, "run", fake)
    assert qe.run_python("x = 1", "assert x == 1").passed
    assert all(c[0] == "/usr/bin/docker" and sys.executable not in c for c in fake.calls)
    [run] = fake.runs()
    name = run[run.index("--name") + 1]
    assert fake.calls[-1] == ["/usr/bin/docker", "rm", "-f", name]
    assert fake.workdir is not None and not fake.workdir.exists()  # directorio temporal borrado


def test_timeout_kills_the_container(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeDocker(timeout=True)
    monkeypatch.setattr(qe.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(qe.subprocess, "run", fake)
    check = qe.run_python("while True:\n    pass", "")
    assert not check.passed and "supera" in check.detail
    [run] = fake.runs()
    assert fake.calls[-1] == ["/usr/bin/docker", "rm", "-f", run[run.index("--name") + 1]]


@pytest.mark.parametrize(
    ("returncode", "detail"),
    [(124, "supera"), (125, "error de Docker"), (137, "proceso terminado")],
)
def test_sandbox_exit_codes_are_explained(
    monkeypatch: pytest.MonkeyPatch, returncode: int, detail: str
) -> None:
    monkeypatch.setattr(qe.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(qe.subprocess, "run", FakeDocker(run_rc=returncode))
    check = qe.run_python("x = 1", "")
    assert not check.passed and detail in check.detail


@pytest.mark.usefixtures("sandbox")
def test_runaway_code_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qe, "CODE_TIMEOUT_SECONDS", 1)
    check = qe.run_python("while True:\n    pass", "")
    assert not check.passed and "supera" in check.detail


def test_text_checks() -> None:
    case = {
        "must_include": [["Contenedor"], ["imagen", "aislad"]],
        "must_not_include": ["máquina virtual completa"],
        "max_chars": 200,
    }
    good = (
        "Docker ejecuta aplicaciones en un contenedor aislado de la máquina, con sus dependencias."
    )
    assert all(c.passed for c in qe.grade(case, good, run_code=False))
    bad = "Docker es una máquina virtual completa. " * 10
    failed = {c.name for c in qe.grade(case, bad, run_code=False) if not c.passed}
    assert failed == {"incluye", "no_incluye", "longitud"}


def test_spanish_detection_ignores_code_blocks() -> None:
    code = "```python\nfor item in items:\n    print(item, 'is the value of the item')\n```"
    assert qe.is_spanish(f"Esta es la solución para recorrer la lista con un bucle.\n{code}")
    assert not qe.is_spanish("This is the answer to the question and it is in English.")
    assert qe.is_spanish(f"Here:\n{code}")  # casi solo código: el idioma no se juzga


def test_code_length_check_counts_only_non_empty_code_lines() -> None:
    case = {"max_code_lines": 2, "spanish": False}
    short = "Prueba esto:\n```python\nx = 1\n\ny = 2\n```"
    assert all(c.passed for c in qe.grade(case, short, run_code=False))
    long = "```python\na = 1\nb = 2\n```\n```js\nlet c = 3;\n```"
    [check] = qe.grade(case, long, run_code=False)
    assert not check.passed and "3 líneas" in check.detail


def test_tutor_cases_are_sent_with_the_tutor_prompt() -> None:
    tutor = [c for c in CASES.values() if c.get("mode") == "tutor"]
    assert tutor and all(c["category"] == "tutor" for c in tutor)
    assert qe.messages_for(tutor[0])[0]["content"] == build_system_prompt("tutor")
    general = CASES["estilo-saludo"]
    assert qe.messages_for(general)[0]["content"] == build_system_prompt()


def test_unknown_mode_in_a_case_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "a", "category": "tutor", "prompt": "x", "mode": "x"}]))
    with pytest.raises(ValueError, match="modo"):
        qe.load_cases(path)


def test_python_checks_are_skipped_without_run_code() -> None:
    checks = qe.grade(CASES["py-nif"], "def letra_dni", run_code=False)
    assert "codigo_python" not in {c.name for c in checks}


class FakeOllama(BaseHTTPRequestHandler):
    seen: ClassVar[list[dict[str, Any]]] = []

    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.seen.append(body)
        good = body["model"] == "bueno"
        reply = (
            fenced(REFERENCE["py-nif"])
            if good
            else "The answer is the letter A for the number and it is not Spanish."
        )
        payload = json.dumps(
            {"message": {"content": reply}, "eval_count": 10, "eval_duration": 1_000_000_000}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def server() -> Any:
    FakeOllama.seen.clear()
    httpd = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_any_failed_case_exits_1_but_the_report_is_complete(server: str, tmp_path: Path) -> None:
    report, answers = tmp_path / "informe.md", tmp_path / "respuestas.json"
    code = qe.main(
        [
            "--base-url", server, "--models", "bueno,malo", "--only", "py-nif",
            "--report", str(report), "--save-answers", str(answers),
        ]
    )  # fmt: skip
    assert code == 1  # «malo» suspende
    sent = FakeOllama.seen[0]
    assert sent["messages"][0] == {"role": "system", "content": build_system_prompt()}
    assert sent["options"] == {"seed": 42, "num_ctx": 4096, "num_predict": 2048}
    text = report.read_text()
    assert "| bueno | 100 % (1/1)" in text and "| malo | 0 % (0/1)" in text
    assert "**malo** · `py-nif`" in text and "tok/s" in text
    assert {r["model"] for r in json.loads(answers.read_text())} == {"bueno", "malo"}


def test_all_cases_passing_exits_0(server: str, tmp_path: Path) -> None:
    report, answers = tmp_path / "informe.md", tmp_path / "respuestas.json"
    args = ["--base-url", server, "--models", "bueno", "--only", "py-nif"]
    assert qe.main([*args, "--report", str(report), "--save-answers", str(answers)]) == 0
    assert "| bueno | 100 % (1/1)" in report.read_text() and "Ninguno." in report.read_text()

    # Puntuar después sin Ollama (--grade-only) mantiene el mismo código de salida.
    assert qe.main(["--grade-only", str(answers), "--only", "py-nif"]) == 0


def test_grade_only_with_a_failed_answer_exits_1(server: str, tmp_path: Path) -> None:
    answers = tmp_path / "respuestas.json"
    qe.main(["--base-url", server, "--models", "bueno,malo", "--only", "py-nif",
             "--save-answers", str(answers)])  # fmt: skip
    assert qe.main(["--grade-only", str(answers), "--only", "py-nif"]) == 1


def test_no_selected_cases_exits_1(tmp_path: Path) -> None:
    assert qe.main(["--only", "no-existe", "--report", str(tmp_path / "informe.md")]) == 1


def test_run_code_without_docker_fails_the_case_instead_of_running_locally(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers, report = tmp_path / "respuestas.json", tmp_path / "informe.md"
    qe.main(["--base-url", server, "--models", "bueno", "--only", "py-nif",
             "--save-answers", str(answers)])  # fmt: skip
    monkeypatch.setattr(qe.shutil, "which", lambda name: None)
    args = ["--grade-only", str(answers), "--only", "py-nif", "--run-code"]
    assert qe.main([*args, "--report", str(report)]) == 1
    assert "codigo_python: no ejecutado: Docker no está instalado" in report.read_text()


@pytest.mark.usefixtures("sandbox")
def test_grade_only_runs_the_generated_code_in_the_sandbox(server: str, tmp_path: Path) -> None:
    answers, report = tmp_path / "respuestas.json", tmp_path / "informe.md"
    qe.main(["--base-url", server, "--models", "bueno,malo", "--only", "py-nif",
             "--save-answers", str(answers)])  # fmt: skip
    args = ["--grade-only", str(answers), "--only", "py-nif", "--run-code"]
    assert qe.main([*args, "--report", str(report)]) == 1
    text = report.read_text()
    assert "| bueno | 100 % (1/1)" in text and "| malo | 0 % (0/1)" in text


def test_unreachable_ollama_is_reported_as_error(tmp_path: Path) -> None:
    report = tmp_path / "informe.md"
    args = ["--base-url", "http://127.0.0.1:9", "--only", "estilo-saludo", "--timeout", "2"]
    assert qe.main([*args, "--report", str(report)]) == 1
    assert "URLError" in report.read_text()
