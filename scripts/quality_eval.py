#!/usr/bin/env python3
"""Evaluación de calidad de respuestas contra Ollama (solo biblioteca estándar; no modifica nada).

Envía cada caso de `scripts/eval/cases.json` al modelo con el MISMO prompt de sistema que usa el
backend y lo puntúa con comprobaciones deterministas: palabras clave obligatorias (grupos de
alternativas) y prohibidas, respuesta en español, longitud máxima y, con --run-code, ejecución del
código Python generado contra los asserts del caso. Sin LLM juez: con un modelo local pequeño el
juez sería menos fiable que lo evaluado.

Diferencias con el chat real, a propósito: no pasa por el filtro de `guard` (así se mide cómo
responde el propio modelo si una pregunta lo esquiva) ni recorta el historial.

--run-code ejecuta el código generado por el modelo SOLO dentro de un contenedor Docker desechable
(sin red, raíz de solo lectura, sin capacidades ni escalada de privilegios, memoria, CPU y procesos
limitados, sin montar el repositorio). Nunca lo ejecuta en el equipo anfitrión: si Docker o la
imagen no están disponibles, el caso falla con el motivo. Por eso --run-code se lanza en el
anfitrión (necesita el cliente `docker`), no desde dentro de otro contenedor. Imagen del sandbox:
EVAL_SANDBOX_IMAGE (por defecto python:3.12-slim; descárgala antes: no se hace pull al evaluar).

Ejemplo (generación en un contenedor en la red de Ollama, sin instalar nada en el Mac):
  docker run --rm --network ollama-local_default -v "$PWD:/repo:ro" -v "$PWD/eval-out:/out" \\
      python:3.12-slim python /repo/scripts/quality_eval.py --base-url http://ollama:11434 \\
      --models qwen2.5:3b,qwen2.5:7b --report /out/informe.md --save-answers /out/respuestas.json
  python3 scripts/quality_eval.py --grade-only eval-out/respuestas.json --run-code \\
      --report eval-out/informe.md

Código de salida: 0 si todos los casos evaluados aprueban; 1 si alguno suspende, hay un error de
conexión o no se ha evaluado ningún caso. El informe se escribe completo en todos los casos.
"""

import argparse
import contextlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from products.personal_ai.prompts import AGENT_RULES, build_system_prompt  # noqa: E402

DEFAULT_CASES = ROOT / "scripts" / "eval" / "cases.json"
CATEGORIES = {
    "python", "java", "sql", "web", "redes", "seguridad",
    "honestidad", "confidencialidad", "multiturno", "documentos", "estilo", "tutor", "agentes",
}  # fmt: skip
MODES = set(AGENT_RULES)  # `mode` de un caso = agente (ADR-0022)
CASE_KEYS = {
    "id", "category", "prompt", "messages", "must_include", "must_not_include",
    "spanish", "max_chars", "python_tests", "num_predict", "mode", "max_code_lines",
}  # fmt: skip
CODE_TIMEOUT_SECONDS = 10
# Sandbox del código generado. La imagen debe estar ya descargada (--pull never): evaluar nunca
# descarga nada ni depende de la red.
SANDBOX_IMAGE = os.environ.get("EVAL_SANDBOX_IMAGE", "python:3.12-slim")
SANDBOX_MEMORY = "256m"
SANDBOX_CPUS = "1"
SANDBOX_PIDS = "64"
# Margen para arrancar y parar el contenedor; el límite del código lo aplica `timeout` dentro.
DOCKER_OVERHEAD_SECONDS = 30
MIN_PROSE_WORDS = 8
_ES = {"el", "la", "de", "que", "y", "en", "los", "las", "un", "una", "es", "por", "para", "con"}
_EN = {"the", "and", "of", "to", "is", "in", "that", "for", "with", "it", "this", "you", "are"}
_FENCE = re.compile(r"```([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.DOTALL)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Result:
    model: str
    case_id: str
    category: str
    answer: str = ""
    total_ms: float | None = None
    tokens: int | None = None
    tokens_per_second: float | None = None
    error: str | None = None
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.passed for c in self.checks)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for case in cases:
        unknown = set(case) - CASE_KEYS
        problems = [
            f"claves desconocidas {sorted(unknown)}" if unknown else "",
            "id repetido" if case.get("id") in seen else "",
            "categoría desconocida" if case.get("category") not in CATEGORIES else "",
            "falta prompt o messages" if ("prompt" in case) == ("messages" in case) else "",
            "modo desconocido" if case.get("mode", "general") not in MODES else "",
        ]
        problems = [p for p in problems if p]
        if problems:
            raise ValueError(f"caso {case.get('id')!r}: {', '.join(problems)}")
        seen.add(case["id"])
    return list(cases)


def messages_for(case: dict[str, Any]) -> list[dict[str, str]]:
    turns = case.get("messages") or [{"role": "user", "content": case["prompt"]}]
    system = build_system_prompt(case.get("mode", "general"))
    return [{"role": "system", "content": system}, *turns]


def ask(
    base_url: str, model: str, case: dict[str, Any], options: dict[str, Any], timeout: float
) -> Result:
    result = Result(model, case["id"], case["category"])
    body = {
        "model": model,
        "messages": messages_for(case),
        "stream": False,
        "options": {**options, "num_predict": case.get("num_predict", 1024)},
    }
    request = urllib.request.Request(  # noqa: S310 - URL indicada por el operador
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            final = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    result.total_ms = (time.perf_counter() - started) * 1000
    result.answer = final.get("message", {}).get("content", "")
    result.tokens = final.get("eval_count")
    if result.tokens and final.get("eval_duration"):
        result.tokens_per_second = result.tokens / (final["eval_duration"] / 1e9)
    return result


def without_code(text: str) -> str:
    return _FENCE.sub(" ", text)


def is_spanish(text: str) -> bool:
    """Con poca prosa fuera del código (respuestas de «solo la función») no se juzga el idioma."""
    words = re.findall(r"[a-z]+", normalize(without_code(text)))
    if len(words) < MIN_PROSE_WORDS:
        return True
    es = sum(w in _ES for w in words)
    en = sum(w in _EN for w in words)
    return es >= 3 and es >= 2 * en


def python_code(text: str) -> str:
    """Bloques ```python (o, si no hay, los bloques sin lenguaje), concatenados."""
    blocks = _FENCE.findall(text)
    tagged = [code for lang, code in blocks if lang.lower() in {"python", "py", "python3"}]
    return "\n\n".join(tagged or [code for lang, code in blocks if not lang])


def _last_line(text: str) -> str:
    return (text.strip().splitlines() or ["sin salida"])[-1][:200]


def sandbox_problem() -> str | None:
    """Motivo por el que no se puede usar el sandbox, o None si Docker y la imagen están listos."""
    docker = shutil.which("docker")
    if docker is None:
        return "Docker no está instalado o no está en el PATH"
    try:
        proc = subprocess.run(  # noqa: S603 - argumentos fijos, sin shell
            [docker, "image", "inspect", SANDBOX_IMAGE],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=DOCKER_OVERHEAD_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"Docker no responde ({type(exc).__name__})"
    if proc.returncode != 0:
        return (
            f"Docker no disponible o falta la imagen {SANDBOX_IMAGE} ({_last_line(proc.stderr)}); "
            f"arranca Docker y ejecuta `docker pull {SANDBOX_IMAGE}`"
        )
    return None


def sandbox_command(docker: str, name: str, workdir: Path) -> list[str]:
    """`docker run` aislado: solo ve `workdir` (solo lectura) y un /tmp pequeño en memoria."""
    return [
        docker, "run", "--rm", "--name", name, "--pull", "never",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "--memory", SANDBOX_MEMORY, "--memory-swap", SANDBOX_MEMORY,
        "--cpus", SANDBOX_CPUS,
        "--pids-limit", SANDBOX_PIDS,
        "--ipc", "none",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",  # noqa: S108 - /tmp del contenedor
        "--mount", f"type=bind,source={workdir},target=/sandbox,readonly",
        "--workdir", "/sandbox",
        SANDBOX_IMAGE,
        "timeout", "-k", "1", str(CODE_TIMEOUT_SECONDS),
        "python", "-E", "-s", "-B", "check_solution.py",
    ]  # fmt: skip


def _remove_container(docker: str, name: str) -> None:
    """Con --rm ya no existe al terminar bien; esto cubre timeouts e interrupciones."""
    with contextlib.suppress(subprocess.TimeoutExpired, OSError):
        subprocess.run(  # noqa: S603 - argumentos fijos, sin shell
            [docker, "rm", "-f", name],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=DOCKER_OVERHEAD_SECONDS,
            check=False,
        )


def run_python(code: str, tests: str) -> Check:
    """Ejecuta los asserts del caso contra el código del modelo, importado como módulo (así no
    se ejecuta su `if __name__ == "__main__":`), dentro del sandbox Docker y con tiempo límite.
    Sin Docker no se ejecuta nada: el caso falla con el motivo."""
    if not code.strip():
        return Check("codigo_python", False, "la respuesta no contiene un bloque de código")
    problem = sandbox_problem()
    docker = shutil.which("docker")
    if problem or docker is None:
        return Check("codigo_python", False, f"no ejecutado: {problem or 'Docker no disponible'}")
    name = f"nexaro-eval-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="nexaro-eval-") as tmp:
        workdir = Path(tmp).resolve()
        workdir.chmod(0o755)  # el contenedor corre como nobody: lee, pero no puede escribir
        files = {"solution.py": code, "check_solution.py": f"from solution import *\n{tests}\n"}
        for filename, content in files.items():
            path = workdir / filename
            path.write_text(content, encoding="utf-8")
            path.chmod(0o644)
        try:
            proc = subprocess.run(  # noqa: S603 - argumentos fijos, sin shell
                sandbox_command(docker, name, workdir),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=CODE_TIMEOUT_SECONDS + DOCKER_OVERHEAD_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return Check("codigo_python", False, f"supera {CODE_TIMEOUT_SECONDS} s")
        finally:
            _remove_container(docker, name)
    if proc.returncode == 0:
        return Check("codigo_python", True)
    if proc.returncode == 124:  # `timeout` dentro del contenedor
        return Check("codigo_python", False, f"supera {CODE_TIMEOUT_SECONDS} s")
    if proc.returncode == 125:  # el propio `docker run` falló
        return Check("codigo_python", False, f"error de Docker: {_last_line(proc.stderr)}")
    if proc.returncode == 137:
        return Check("codigo_python", False, f"proceso terminado (límite de {SANDBOX_MEMORY}?)")
    return Check("codigo_python", False, _last_line(proc.stderr))


def grade(case: dict[str, Any], answer: str, *, run_code: bool) -> list[Check]:
    text = normalize(answer)
    checks: list[Check] = []
    for group in case.get("must_include", []):
        hit = any(normalize(option) in text for option in group)
        checks.append(Check("incluye", hit, "" if hit else f"ninguna de {group}"))
    for banned in case.get("must_not_include", []):
        found = normalize(banned) in text
        checks.append(Check("no_incluye", not found, f"contiene «{banned}»" if found else ""))
    if case.get("spanish", True):
        ok = is_spanish(answer)
        checks.append(Check("espanol", ok, "" if ok else "no parece español"))
    if "max_chars" in case:
        ok = len(answer) <= case["max_chars"]
        checks.append(Check("longitud", ok, "" if ok else f"{len(answer)} > {case['max_chars']}"))
    if "max_code_lines" in case:
        lines = sum(
            len([ln for ln in code.splitlines() if ln.strip()])
            for _, code in _FENCE.findall(answer)
        )
        ok = lines <= case["max_code_lines"]
        detail = "" if ok else f"{lines} líneas de código > {case['max_code_lines']}"
        checks.append(Check("codigo_breve", ok, detail))
    if "python_tests" in case and run_code:
        checks.append(run_python(python_code(answer), case["python_tests"]))
    return checks


def median(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


def pct(passed: int, total: int) -> str:
    return "—" if total == 0 else f"{100 * passed / total:.0f} % ({passed}/{total})"


def render_report(results: list[Result], run_code: bool) -> str:
    models = list(dict.fromkeys(r.model for r in results))
    categories = sorted({r.category for r in results})
    lines = ["# Evaluación de calidad", ""]
    if not run_code:
        lines += ["> Sin --run-code: los casos de Python solo se puntúan por texto.", ""]
    lines += ["| Modelo | Aprobados | Mediana ms | tok/s | Errores |", "|---|---|---|---|---|"]
    for model in models:
        rs = [r for r in results if r.model == model]
        ms, tps = median([r.total_ms for r in rs]), median([r.tokens_per_second for r in rs])
        lines.append(
            f"| {model} | {pct(sum(r.passed for r in rs), len(rs))} "
            f"| {'—' if ms is None else f'{ms:.0f}'} | {'—' if tps is None else f'{tps:.1f}'} "
            f"| {sum(r.error is not None for r in rs)} |"
        )
    lines += ["", "## Por categoría", "", "| Categoría | " + " | ".join(models) + " |"]
    lines.append("|---" * (len(models) + 1) + "|")
    for category in categories:
        cells = []
        for model in models:
            rs = [r for r in results if r.model == model and r.category == category]
            cells.append(pct(sum(r.passed for r in rs), len(rs)))
        lines.append(f"| {category} | " + " | ".join(cells) + " |")
    lines += ["", "## Fallos", ""]
    failures = [r for r in results if not r.passed]
    for r in failures:
        reasons = r.error or "; ".join(f"{c.name}: {c.detail}" for c in r.checks if not c.passed)
        lines.append(f"- **{r.model}** · `{r.case_id}` — {reasons}")
    if not failures:
        lines.append("Ninguno.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--models", default="qwen2.5:3b", help="separados por comas")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--only", help="ids o categorías separados por comas")
    parser.add_argument("--num-ctx", type=int, default=4096, help="igual que OLLAMA_NUM_CTX")
    parser.add_argument("--temperature", type=float, help="por defecto, la del modelo (como hoy)")
    parser.add_argument("--keep-alive", default="30m")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--run-code", action="store_true", help="ejecuta el código generado")
    parser.add_argument("--save-answers", type=Path, help="guarda respuestas y métricas (JSON)")
    parser.add_argument("--grade-only", type=Path, help="puntúa un JSON de --save-answers")
    parser.add_argument("--report", type=Path, help="escribe el informe Markdown aquí")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    if args.only:
        wanted = {item.strip() for item in args.only.split(",")}
        cases = [c for c in cases if c["id"] in wanted or c["category"] in wanted]
    by_id = {c["id"]: c for c in cases}

    if args.grade_only:
        raw = json.loads(args.grade_only.read_text(encoding="utf-8"))
        results = [
            Result(**{k: v for k, v in item.items() if k != "checks"})
            for item in raw
            if item["case_id"] in by_id
        ]
    else:
        options: dict[str, Any] = {"seed": 42, "num_ctx": args.num_ctx}
        if args.temperature is not None:
            options["temperature"] = args.temperature
        results = []
        for model in [m.strip() for m in args.models.split(",") if m.strip()]:
            for case in cases:
                results.append(ask(args.base_url, model, case, options, args.timeout))
                status = results[-1].error or f"{results[-1].total_ms:.0f} ms"
                print(f"  {model} · {case['id']}: {status}", flush=True)

    for result in results:
        if result.error is None:
            result.checks = grade(by_id[result.case_id], result.answer, run_code=args.run_code)
    if args.save_answers:
        args.save_answers.write_text(
            json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), "utf-8"
        )
    report = render_report(results, args.run_code)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    print("\n" + report)
    # 0 solo si se evaluó algo y todo aprobó (los errores de conexión cuentan como suspenso).
    return 0 if results and all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
