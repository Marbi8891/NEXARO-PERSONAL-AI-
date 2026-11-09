"""El script de benchmark mide con un Ollama falso: parsea streaming y no streaming."""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

SPEC = importlib.util.spec_from_file_location(
    "ollama_benchmark", Path(__file__).resolve().parents[2] / "scripts/ollama_benchmark.py"
)
assert SPEC and SPEC.loader
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)

FINAL = {
    "done": True,
    "load_duration": 2_000_000_000,
    "prompt_eval_count": 30,
    "prompt_eval_duration": 500_000_000,
    "eval_count": 20,
    "eval_duration": 2_000_000_000,
}


class FakeOllama(BaseHTTPRequestHandler):
    resident = True
    seen: ClassVar[list[dict]] = []

    def log_message(self, *args: object) -> None:
        pass

    def _send(self, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        models = [{"name": "m"}] if FakeOllama.resident else []
        self._send(json.dumps({"models": models}).encode())

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.seen.append({"path": self.path, **body})
        if self.path == "/api/generate":
            FakeOllama.resident = False
            return self._send(b"{}")
        FakeOllama.resident = True
        if body["stream"]:
            lines = [{"message": {"content": ""}}, {"message": {"content": "Hola"}}, FINAL]
            return self._send(("\n".join(json.dumps(x) for x in lines) + "\n").encode())
        self._send(json.dumps({**FINAL, "message": {"content": "Hola"}}).encode())


@pytest.fixture
def server():
    FakeOllama.seen.clear()
    httpd = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_streaming_profile_reports_ttft_and_ollama_counters(server: str) -> None:
    sample = bench.run_once(
        server, "m", "hola", scenario="corta", state="caliente", profile="optimizado",
        options={"num_ctx": 4096}, keep_alive="30m", timeout=5,
    )  # fmt: skip
    assert sample.error is None and sample.ttft_ms is not None
    assert sample.ttft_ms <= sample.total_ms
    assert sample.load_ms == 2000 and sample.prompt_eval_ms == 500 and sample.generation_ms == 2000
    assert sample.tokens == 20 and sample.tokens_per_second == pytest.approx(10.0)
    sent = FakeOllama.seen[-1]
    assert sent["stream"] is True and sent["keep_alive"] == "30m"
    assert sent["options"]["num_ctx"] == 4096 and sent["options"]["seed"] == 42


def test_current_profile_replicates_the_backend_and_has_no_ttft(server: str) -> None:
    sample = bench.run_once(
        server, "m", "hola", scenario="corta", state="frio", profile="actual",
        options={"num_predict": 2048}, keep_alive=None, timeout=5,
    )  # fmt: skip
    sent = FakeOllama.seen[-1]
    assert sent["stream"] is False and "keep_alive" not in sent
    assert sample.ttft_ms == sample.total_ms  # el usuario espera la respuesta entera
    assert sample.extra["nota"]


def test_main_runs_cold_then_warm_and_prints_a_table(server: str, capsys, tmp_path) -> None:
    out = tmp_path / "r.json"
    code = bench.main(
        ["--base-url", server, "--model", "m", "--profile", "optimizado", "--scenarios", "corta",
         "--runs", "2", "--json", str(out)]
    )  # fmt: skip
    assert code == 0
    text = capsys.readouterr().out
    assert "| corta | frio |" in text and "| corta | caliente |" in text
    assert any(c["path"] == "/api/generate" and c["keep_alive"] == 0 for c in FakeOllama.seen)
    assert len(json.loads(out.read_text())) == 3


def test_unreachable_ollama_fails_clearly(capsys) -> None:
    assert bench.main(["--base-url", "http://127.0.0.1:9", "--scenarios", "corta"]) == 2
    assert "No se puede contactar" in capsys.readouterr().err


def test_long_context_scenario_has_the_requested_size() -> None:
    prompt = bench.build_prompt("contexto_largo", 5000)
    assert 5000 <= len(prompt) < 5300 and prompt.endswith("tres frases.")
