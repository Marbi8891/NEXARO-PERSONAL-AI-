"""Comprueba, descarga y prueba un modelo de Ollama. Solo biblioteca estándar.

Pensado para ejecutarse dentro del contenedor del backend (misma red que Ollama), sin copiarlo
en la imagen:

    docker compose exec -T backend python - ensure qwen2.5:3b < scripts/ollama_model.py

Subcomandos:
    check MODEL     ¿responde Ollama y está el modelo instalado?
    ensure MODEL    descarga el modelo solo si falta (idempotente)
    generate MODEL  genera una respuesta corta real

Códigos de salida: 0 bien, 1 error, 2 Ollama no responde, 3 el modelo no está instalado.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

OK, ERROR, UNREACHABLE, MISSING = 0, 1, 2, 3
# Dentro del backend, la misma URL que usa la aplicación.
DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")


class Unreachable(Exception):
    """Ollama no acepta conexiones o no contesta a tiempo."""


def canonical(name: str) -> str:
    """Ollama guarda `modelo` como `modelo:latest`."""
    return name if ":" in name else f"{name}:latest"


def _open(url: str, payload: dict[str, Any] | None, timeout: float) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(  # noqa: S310 - URL de Ollama de la configuración
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise Unreachable(str(getattr(exc, "reason", exc))) from exc


def installed_models(base_url: str, timeout: float) -> list[str]:
    with _open(f"{base_url}/api/tags", None, timeout) as response:
        return [str(m["name"]) for m in json.load(response)["models"]]


def has_model(base_url: str, model: str, timeout: float) -> bool:
    wanted = canonical(model)
    return any(canonical(name) == wanted for name in installed_models(base_url, timeout))


def _lines(response: Any) -> Iterator[dict[str, Any]]:
    try:
        for raw in response:
            if raw.strip():
                yield json.loads(raw)
    except (TimeoutError, ConnectionError) as exc:  # sin progreso o conexión cortada
        raise Unreachable(f"sin respuesta durante la descarga ({exc})") from exc


def pull(base_url: str, model: str, stall_timeout: float, out: Any) -> None:
    """Descarga en streaming. `stall_timeout` corta si Ollama deja de enviar progreso."""
    last_status = ""
    with _open(f"{base_url}/api/pull", {"model": model, "stream": True}, stall_timeout) as response:
        for event in _lines(response):
            if "error" in event:
                raise RuntimeError(f"Ollama rechazó la descarga: {event['error']}")
            status = str(event.get("status", ""))
            total, done = event.get("total"), event.get("completed")
            if total and done is not None:
                print(f"  {status}: {100 * done // total}%", end="\r", file=out, flush=True)
            elif status != last_status:
                print(f"  {status}", file=out, flush=True)
            last_status = status
    if last_status != "success":
        raise RuntimeError("la descarga terminó sin confirmar «success»")


def generate(base_url: str, model: str, timeout: float) -> str:
    payload = {
        "model": model,
        "prompt": "Responde únicamente con la palabra: listo",
        "stream": False,
        "options": {"num_predict": 16, "temperature": 0},
    }
    with _open(f"{base_url}/api/generate", payload, timeout) as response:
        try:
            body = json.load(response)
        except (TimeoutError, ConnectionError) as exc:
            raise Unreachable(f"sin respuesta del modelo ({exc})") from exc
    if "error" in body:
        raise RuntimeError(f"Ollama devolvió un error: {body['error']}")
    return str(body.get("response", "")).strip()


def main(argv: list[str] | None = None, out: Any = sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("check", "ensure", "generate"))
    parser.add_argument("model")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=10.0, help="consultas cortas (s)")
    parser.add_argument("--stall-timeout", type=float, default=120.0, help="descarga sin progreso")
    parser.add_argument(
        "--generate-timeout", type=float, default=300.0, help="primera carga en CPU"
    )
    parser.add_argument("--retries", type=int, default=3, help="reintentos si Ollama no responde")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")

    for attempt in range(1, args.retries + 2):
        try:
            return _run(args, base_url, out)
        except Unreachable as exc:
            if attempt > args.retries:
                print(f"ERROR: Ollama no responde en {base_url} ({exc})", file=out)
                return UNREACHABLE
            wait = 2 ** (attempt - 1)
            print(f"Ollama no responde; reintento {attempt}/{args.retries} en {wait} s", file=out)
            time.sleep(wait)
        except (urllib.error.HTTPError, RuntimeError, ValueError, KeyError) as exc:
            print(f"ERROR: {exc}", file=out)
            return ERROR
    return ERROR  # inalcanzable


def _run(args: argparse.Namespace, base_url: str, out: Any) -> int:
    model = args.model
    if args.command == "check":
        if has_model(base_url, model, args.timeout):
            print(f"OK: Ollama responde y {model} está instalado", file=out)
            return OK
        print(f"FALTA: Ollama responde pero {model} no está instalado", file=out)
        return MISSING

    if args.command == "ensure":
        if has_model(base_url, model, args.timeout):
            print(f"OK: {model} ya estaba instalado; no se descarga nada", file=out)
            return OK
        print(f"Descargando {model}...", file=out)
        pull(base_url, model, args.stall_timeout, out)
        if not has_model(base_url, model, args.timeout):
            print(f"ERROR: tras la descarga, {model} no aparece instalado", file=out)
            return ERROR
        print(f"OK: {model} descargado e instalado", file=out)
        return OK

    if not has_model(base_url, model, args.timeout):
        print(f"FALTA: {model} no está instalado (make model)", file=out)
        return MISSING
    started = time.perf_counter()
    text = generate(base_url, model, args.generate_timeout)
    if not text:
        print("ERROR: el modelo devolvió una respuesta vacía", file=out)
        return ERROR
    elapsed = time.perf_counter() - started
    print(f"OK: respuesta en {elapsed:.1f} s: {text[:80]!r}", file=out)
    return OK


if __name__ == "__main__":
    sys.exit(main())
