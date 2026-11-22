#!/usr/bin/env python3
"""Benchmark de inferencia contra Ollama (solo biblioteca estándar; no modifica nada).

Mide, por escenario y por estado del modelo (frío = descargado antes de la petición, caliente =
ya residente): TTFT, tiempo total y los contadores que devuelve el propio Ollama (carga, evaluación
del prompt, generación, tokens y tokens/s). No inventa nada: cada cifra sale de una petición real.

Dos perfiles:
  --profile actual     replica lo que hace hoy el backend: sin streaming, sin keep_alive ni num_ctx,
                       num_predict=2048. El usuario no ve nada hasta el final, así que su «primer
                       contenido» es el tiempo total.
  --profile optimizado streaming real y los parámetros que se pasan (--num-ctx, --num-predict,
                       --keep-alive, --num-thread).

Ejemplo desde un contenedor de la misma red que Ollama (no hace falta instalar nada en el Mac):
  docker run --rm --network ollama-local_default -v "$PWD/scripts:/s:ro" python:3.12-slim \\
      python /s/ollama_benchmark.py --base-url http://ollama:11434 --model qwen2.5:3b --runs 3
"""

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

SCENARIOS: dict[str, str] = {
    "corta": "Explica en dos frases qué es Docker.",
    "programacion": (
        "Escribe en Python una función que valide un IBAN español (24 caracteres, empieza por ES) "
        "calculando el dígito de control módulo 97, con docstring y dos pruebas con pytest."
    ),
    "contexto_largo": "",  # se construye con --long-chars
}
FILLER = (
    "El proyecto NEXARO organiza sus módulos en paquetes independientes y cada módulo expone una "
    "interfaz pequeña. La documentación describe decisiones de arquitectura, límites conocidos y "
    "pruebas asociadas a cada cambio. "
)


@dataclass
class Sample:
    scenario: str
    state: str  # "frio" | "caliente"
    profile: str
    model: str
    ttft_ms: float | None = None
    total_ms: float = 0.0
    load_ms: float | None = None
    prompt_eval_ms: float | None = None
    generation_ms: float | None = None
    prompt_tokens: int | None = None
    tokens: int | None = None
    tokens_per_second: float | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _ms(nanoseconds: int | None) -> float | None:
    return None if nanoseconds is None else nanoseconds / 1e6


def post(base_url: str, path: str, body: dict[str, Any], timeout: float) -> Any:
    request = urllib.request.Request(  # noqa: S310 - URL indicada por el operador
        base_url.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - URL del operador


def get_json(base_url: str, path: str, timeout: float = 10.0) -> Any:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


def unload(base_url: str, model: str) -> None:
    """Descarga el modelo de memoria (keep_alive=0) y espera a que deje de estar residente."""
    post(base_url, "/api/generate", {"model": model, "keep_alive": 0}, 60).read()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if all(m.get("name") != model for m in get_json(base_url, "/api/ps").get("models", [])):
            return
        time.sleep(0.5)


def build_prompt(scenario: str, long_chars: int) -> str:
    if scenario != "contexto_largo":
        return SCENARIOS[scenario]
    body = (FILLER * (long_chars // len(FILLER) + 1))[:long_chars]
    question = "Con el texto anterior: ¿qué describe la documentación? Responde en tres frases."
    return f"{body}\n\n{question}"


def run_once(
    base_url: str,
    model: str,
    prompt: str,
    *,
    scenario: str,
    state: str,
    profile: str,
    options: dict[str, Any],
    keep_alive: str | None,
    timeout: float,
) -> Sample:
    sample = Sample(scenario, state, profile, model)
    stream = profile == "optimizado"
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
        "options": {"temperature": 0, "seed": 42, **options},
    }
    if keep_alive is not None:
        body["keep_alive"] = keep_alive
    started = time.perf_counter()
    final: dict[str, Any] = {}
    try:
        with post(base_url, "/api/chat", body, timeout) as response:
            if stream:
                for line in response:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if sample.ttft_ms is None and chunk.get("message", {}).get("content"):
                        sample.ttft_ms = (time.perf_counter() - started) * 1000
                    if chunk.get("done"):
                        final = chunk
            else:
                final = json.load(response)
                sample.ttft_ms = None  # sin streaming no hay primer token observable
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        sample.error = f"{type(exc).__name__}: {exc}"
        return sample
    sample.total_ms = (time.perf_counter() - started) * 1000
    if not stream:
        sample.ttft_ms = sample.total_ms  # lo que espera el usuario hoy: la respuesta entera
        sample.extra["nota"] = "ttft = total (sin streaming)"
    sample.load_ms = _ms(final.get("load_duration"))
    sample.prompt_eval_ms = _ms(final.get("prompt_eval_duration"))
    sample.generation_ms = _ms(final.get("eval_duration"))
    sample.prompt_tokens = final.get("prompt_eval_count")
    sample.tokens = final.get("eval_count")
    if sample.tokens and final.get("eval_duration"):
        sample.tokens_per_second = sample.tokens / (final["eval_duration"] / 1e9)
    return sample


def median(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


def fmt(value: float | None, digits: int = 0) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def render_table(samples: list[Sample]) -> str:
    header = (
        "| Escenario | Estado | Perfil | n | TTFT ms | Total ms | Carga ms | Eval. prompt ms | "
        "Generación ms | Tokens prompt | Tokens | tok/s |\n" + "|---" * 12 + "|"
    )
    groups: dict[tuple[str, str, str], list[Sample]] = {}
    for s in samples:
        groups.setdefault((s.scenario, s.state, s.profile), []).append(s)
    rows = []
    for (scenario, state, profile), group in groups.items():
        ok = [s for s in group if s.error is None]
        errors = f" (+{len(group) - len(ok)} error)" if len(ok) < len(group) else ""
        rows.append(
            f"| {scenario} | {state} | {profile} | {len(ok)}{errors} "
            f"| {fmt(median([s.ttft_ms for s in ok]))} "
            f"| {fmt(median([s.total_ms for s in ok]))} "
            f"| {fmt(median([s.load_ms for s in ok]))} "
            f"| {fmt(median([s.prompt_eval_ms for s in ok]))} "
            f"| {fmt(median([s.generation_ms for s in ok]))} "
            f"| {fmt(median([float(s.prompt_tokens) if s.prompt_tokens else None for s in ok]))} "
            f"| {fmt(median([float(s.tokens) if s.tokens else None for s in ok]))} "
            f"| {fmt(median([s.tokens_per_second for s in ok]), 1)} |"
        )
    return (
        header
        + "\n"
        + "\n".join(rows)
        + "\n\n(medianas; TTFT del perfil «actual» = total, porque no hay streaming)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--profile", choices=("actual", "optimizado"), default="actual")
    parser.add_argument("--scenarios", default="corta,programacion,contexto_largo")
    parser.add_argument("--runs", type=int, default=3, help="repeticiones calientes por escenario")
    parser.add_argument("--long-chars", type=int, default=12000, help="tamaño del contexto largo")
    parser.add_argument("--num-ctx", type=int, help="solo perfil optimizado")
    parser.add_argument(
        "--num-predict", type=int, help="solo perfil optimizado (por defecto 2048 en «actual»)"
    )
    parser.add_argument("--num-thread", type=int, help="solo perfil optimizado")
    parser.add_argument("--keep-alive", default="30m", help="solo perfil optimizado")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--json", help="guarda las muestras en este archivo")
    args = parser.parse_args(argv)

    options: dict[str, Any] = {"num_predict": 2048}
    keep_alive: str | None = None
    if args.profile == "optimizado":
        options = {}
        for key, value in (
            ("num_ctx", args.num_ctx),
            ("num_predict", args.num_predict),
            ("num_thread", args.num_thread),
        ):
            if value is not None:
                options[key] = value
        keep_alive = args.keep_alive

    try:
        print(
            "Modelos residentes antes:",
            json.dumps(get_json(args.base_url, "/api/ps").get("models", [])),
        )
    except (urllib.error.URLError, OSError) as exc:
        print(f"No se puede contactar con Ollama en {args.base_url}: {exc}", file=sys.stderr)
        return 2

    samples: list[Sample] = []
    for scenario in args.scenarios.split(","):
        prompt = build_prompt(scenario.strip(), args.long_chars)
        common = {
            "scenario": scenario.strip(),
            "profile": args.profile,
            "options": options,
            "keep_alive": keep_alive,
            "timeout": args.timeout,
        }
        unload(args.base_url, args.model)
        samples.append(run_once(args.base_url, args.model, prompt, state="frio", **common))
        for _ in range(args.runs):
            samples.append(run_once(args.base_url, args.model, prompt, state="caliente", **common))
        print(f"  {scenario}: hecho", flush=True)

    print(
        "\nModelos residentes después:",
        json.dumps(get_json(args.base_url, "/api/ps").get("models", [])),
    )
    print("\n" + render_table(samples))
    for sample in samples:
        if sample.error:
            print(f"ERROR {sample.scenario}/{sample.state}: {sample.error}", file=sys.stderr)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump([asdict(s) for s in samples], handle, ensure_ascii=False, indent=2)
    return 1 if any(s.error for s in samples) else 0


if __name__ == "__main__":
    sys.exit(main())
