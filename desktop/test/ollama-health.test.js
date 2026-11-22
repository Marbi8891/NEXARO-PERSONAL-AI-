"use strict";
// Ollama y sondas HTTP contra servidores HTTP reales en 127.0.0.1 (puertos efímeros).
const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { OllamaManager, parseTags, hasModel, estimateRamGb, windowsCandidates } = require("../src/main/ollama");
const { httpGet, waitFor, backoffDelay, probeBackend } = require("../src/main/health");
const { makeConfig, silentLogger } = require("./helpers");

function serve(handler) {
  return new Promise((resolve) => {
    const server = http.createServer(handler);
    server.listen(0, "127.0.0.1", () => resolve({ server, url: `http://127.0.0.1:${server.address().port}` }));
  });
}

const TAGS = { models: [{ name: "qwen2.5:3b", size: 1929912432, details: { parameter_size: "3.1B", quantization_level: "Q4_K_M" } }, { name: "llama3:latest", size: 4661224676 }] };

test("ollama: detecta Ollama en marcha y sus modelos (servidor real)", async (t) => {
  const { server, url } = await serve((req, res) => {
    assert.equal(req.url, "/api/tags");
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify(TAGS));
  });
  t.after(() => server.close());
  const config = makeConfig({ "ollama.endpoint": url });
  const om = new OllamaManager({ getConfig: () => config, logger: silentLogger() });
  const st = await om.status();
  assert.equal(st.running, true);
  assert.deepEqual(st.models.map((m) => m.name), ["qwen2.5:3b", "llama3:latest"]);
  assert.equal(st.models[0].parameterSize, "3.1B");
  assert.equal(st.models[0].sizeGb, 1.8);
  assert.equal(st.models[0].ramGb, 2.2);
  const ms = await om.modelStatus();
  assert.equal(ms.installed, true);
});

test("ollama: no está en marcha (puerto cerrado)", async () => {
  const { server, url } = await serve(() => {});
  await new Promise((r) => server.close(r));
  const config = makeConfig({ "ollama.endpoint": url });
  const om = new OllamaManager({ getConfig: () => config, logger: silentLogger() });
  const st = await om.status();
  assert.equal(st.running, false);
  assert.equal(st.error, "ECONNREFUSED");
});

test("ollama: respuesta que no es de Ollama no cuenta como en marcha", async (t) => {
  const { server, url } = await serve((_req, res) => res.end("<html>otro servicio</html>"));
  t.after(() => server.close());
  const config = makeConfig({ "ollama.endpoint": url });
  const om = new OllamaManager({ getConfig: () => config, logger: silentLogger() });
  assert.equal((await om.status()).running, false);
});

test("ollama: coincidencia de modelos y estimación de RAM", () => {
  const models = parseTags(JSON.stringify(TAGS));
  assert.ok(hasModel(models, "qwen2.5:3b"));
  assert.ok(hasModel(models, "llama3"));
  assert.ok(!hasModel(models, "qwen2.5:7b"));
  assert.equal(parseTags("no json"), null);
  assert.equal(estimateRamGb({ sizeGb: null }), null);
});

test("ollama: ejecutable en las rutas estándar de Windows y arranque", async () => {
  const env = { LOCALAPPDATA: "C:\\Users\\ana\\AppData\\Local" };
  assert.deepEqual(windowsCandidates(env), [
    "C:\\Users\\ana\\AppData\\Local\\Programs\\Ollama\\ollama app.exe",
    "C:\\Users\\ana\\AppData\\Local\\Programs\\Ollama\\ollama.exe",
  ]);
  const launched = [];
  const config = makeConfig();
  const om = new OllamaManager({
    getConfig: () => config,
    logger: silentLogger(),
    platform: "win32",
    env,
    exists: (p) => p.endsWith("ollama.exe"),
    launch: async (file, args) => (launched.push([file, args]), { ok: true }),
  });
  assert.equal(om.detectExecutable().installed, true);
  assert.deepEqual(await om.start(), { ok: true });
  assert.deepEqual(launched, [["C:\\Users\\ana\\AppData\\Local\\Programs\\Ollama\\ollama.exe", ["serve"]]]);
  const none = new OllamaManager({ getConfig: () => config, logger: silentLogger(), platform: "win32", env, exists: () => false });
  assert.deepEqual(await none.start(), { ok: false, error: "OLLAMA_NOT_INSTALLED" });
});

test("health: httpGet solo permite http local", async () => {
  assert.equal((await httpGet("https://example.com/")).error, "URL_NOT_LOCAL");
  assert.equal((await httpGet("http://192.168.1.10:8001/")).error, "URL_NOT_LOCAL");
  assert.equal((await httpGet("not a url")).error, "URL_INVALID");
});

test("health: httpGet respeta el timeout", async (t) => {
  const { server, url } = await serve(() => {}); // nunca responde
  t.after(() => server.close());
  const started = Date.now();
  const res = await httpGet(url, { timeoutMs: 200 });
  assert.equal(res.ok, false);
  assert.ok(Date.now() - started < 2000);
  server.closeAllConnections();
});

test("health: sonda del backend con los endpoints reales simulados", async (t) => {
  let mode = "ready";
  const { server, url } = await serve((req, res) => {
    res.setHeader("content-type", "application/json");
    if (req.url === "/api/health/live") return res.end('{"status":"ok"}');
    if (mode === "ready") return res.end('{"status":"ok","ollama":"connected","model":"ready"}');
    res.statusCode = 503;
    return res.end(JSON.stringify({ detail: mode === "model" ? "Modelo de IA no disponible" : "Servicio de IA no disponible" }));
  });
  t.after(() => server.close());
  assert.deepEqual(await probeBackend(url), { live: true, ai: "ready", detail: null });
  mode = "model";
  assert.equal((await probeBackend(url)).ai, "model_missing");
  mode = "down";
  assert.equal((await probeBackend(url)).ai, "unreachable");
});

test("health: backoff exponencial con tope", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5].map((n) => backoffDelay(n)), [1000, 2000, 4000, 8000, 10000, 10000]);
});

test("health: waitFor reintenta con backoff y respeta el timeout total", async () => {
  let clock = 0;
  const sleeps = [];
  const sleep = async (ms) => {
    sleeps.push(ms);
    clock += ms;
  };
  const res = await waitFor(async () => false, { timeoutMs: 20_000, sleep, now: () => clock });
  assert.equal(res.ok, false);
  assert.deepEqual(sleeps, [1000, 2000, 4000, 8000, 5000]);
  assert.ok(clock <= 20_000);

  clock = 0;
  const ok = await waitFor(async (n) => (n === 2 ? "listo" : null), { timeoutMs: 20_000, sleep: async () => {}, now: () => clock });
  assert.deepEqual([ok.ok, ok.value, ok.attempts], [true, "listo", 3]);
});
