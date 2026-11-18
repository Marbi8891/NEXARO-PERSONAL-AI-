"""scripts/ollama_model.py con un Ollama falso: comprobación, descarga idempotente y generación."""

import importlib.util
import io
import json
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

SPEC = importlib.util.spec_from_file_location(
    "ollama_model", Path(__file__).resolve().parents[2] / "scripts/ollama_model.py"
)
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)

MODEL = "qwen2.5:3b"


class FakeOllama(BaseHTTPRequestHandler):
    installed: ClassVar[list[str]] = []
    pull_events: ClassVar[list[dict[str, Any]]] = []
    pull_installs: ClassVar[bool] = True
    pull_stall: ClassVar[float] = 0.0
    answer: ClassVar[str] = "listo"
    calls: ClassVar[list[str]] = []

    def _json(self, body: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self.calls.append(f"GET {self.path}")
        self._json({"models": [{"name": name} for name in self.installed]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(f"POST {self.path}")
        if self.path == "/api/pull":
            self.send_response(200)
            self.end_headers()
            for event in self.pull_events:
                self.wfile.write((json.dumps(event) + "\n").encode())
                self.wfile.flush()
                time.sleep(self.pull_stall)
            if self.pull_installs:
                type(self).installed = [*self.installed, body["model"]]
            return
        self._json({"response": self.answer, "done": True})

    def log_message(self, *args: object) -> None:
        pass


SUCCESS = [
    {"status": "pulling manifest"},
    {"status": "pulling 1a2b", "total": 100, "completed": 40},
    {"status": "pulling 1a2b", "total": 100, "completed": 100},
    {"status": "success"},
]


@pytest.fixture
def server() -> Iterator[str]:
    FakeOllama.installed = []
    FakeOllama.pull_events = SUCCESS
    FakeOllama.pull_installs = True
    FakeOllama.pull_stall = 0.0
    FakeOllama.answer = "listo"
    FakeOllama.calls = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def run(base_url: str, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    code = script.main([*args, "--base-url", base_url, "--retries", "0"], out=out)
    return code, out.getvalue()


def test_check_reports_installed_and_missing_models(server: str) -> None:
    assert run(server, "check", MODEL)[0] == script.MISSING
    FakeOllama.installed = [MODEL]
    code, out = run(server, "check", MODEL)
    assert code == script.OK and "instalado" in out


def test_untagged_model_matches_latest(server: str) -> None:
    FakeOllama.installed = ["llama3.2:latest"]
    assert run(server, "check", "llama3.2")[0] == script.OK
    assert run(server, "check", "llama3.2:1b")[0] == script.MISSING


def test_ensure_is_idempotent_and_does_not_pull_an_installed_model(server: str) -> None:
    FakeOllama.installed = [MODEL]
    code, out = run(server, "ensure", MODEL)
    assert code == script.OK and "no se descarga nada" in out
    assert "POST /api/pull" not in FakeOllama.calls


def test_ensure_pulls_a_missing_model_once(server: str) -> None:
    code, out = run(server, "ensure", MODEL)
    assert code == script.OK and "descargado e instalado" in out
    assert FakeOllama.calls.count("POST /api/pull") == 1
    assert run(server, "ensure", MODEL)[0] == script.OK
    assert FakeOllama.calls.count("POST /api/pull") == 1  # la segunda vez no descarga


def test_pull_error_is_reported(server: str) -> None:
    FakeOllama.pull_events = [{"status": "pulling manifest"}, {"error": "file does not exist"}]
    FakeOllama.pull_installs = False
    code, out = run(server, "ensure", "no-existe:1b")
    assert code == script.ERROR and "file does not exist" in out


def test_pull_without_success_is_an_error(server: str) -> None:
    FakeOllama.pull_events = [{"status": "pulling manifest"}]
    FakeOllama.pull_installs = False
    code, out = run(server, "ensure", MODEL)
    assert code == script.ERROR and "success" in out


def test_stalled_pull_times_out(server: str) -> None:
    FakeOllama.pull_events = [{"status": "pulling manifest"}, {"status": "success"}]
    FakeOllama.pull_stall = 1.0
    code, out = run(server, "ensure", MODEL, "--stall-timeout", "0.3")
    assert code == script.UNREACHABLE and "no responde" in out


def test_generate_requires_the_model_and_a_non_empty_answer(server: str) -> None:
    assert run(server, "generate", MODEL)[0] == script.MISSING
    FakeOllama.installed = [MODEL]
    code, out = run(server, "generate", MODEL)
    assert code == script.OK and "listo" in out
    FakeOllama.answer = "   "
    code, out = run(server, "generate", MODEL)
    assert code == script.ERROR and "vacía" in out


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_unreachable_ollama_is_retried_then_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(script.time, "sleep", waits.append)
    out = io.StringIO()
    url = f"http://127.0.0.1:{_free_port()}"
    code = script.main(["check", MODEL, "--base-url", url, "--retries", "2"], out=out)
    assert code == script.UNREACHABLE
    assert waits == [1, 2]  # espera exponencial entre reintentos
    assert "no responde" in out.getvalue()
