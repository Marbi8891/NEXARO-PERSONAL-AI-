"use strict";
// Escenarios del arranque y la parada con dobles de Docker, Ollama y sondas (sin E/S real).
const test = require("node:test");
const assert = require("node:assert/strict");
const { Lifecycle } = require("../src/main/lifecycle");
const { StateMachine, STATES: S } = require("../src/main/states");
const { makeConfig, silentLogger, instantWait } = require("./helpers");

const WIN11 = () => ({ platform: "win32", isWindows: true, name: "Windows 11", build: 22631, supported: true });

function fakeDocker(o = {}) {
  const calls = [];
  const rec = (name, value) => async (...args) => {
    calls.push(name);
    return typeof value === "function" ? value(...args) : value;
  };
  let daemonCalls = 0;
  return {
    calls,
    detectCli: rec("detectCli", { installed: o.installed ?? true, path: "docker.exe" }),
    composeVersion: rec("composeVersion", { available: true, version: o.compose ?? "2.29.1", ok: o.composeOk ?? true }),
    daemonStatus: rec("daemonStatus", () => {
      daemonCalls += 1;
      const running = typeof o.daemon === "function" ? o.daemon(daemonCalls) : o.daemon ?? true;
      return { running, serverVersion: running ? "27.0" : null };
    }),
    startDesktop: rec("startDesktop", o.startDesktop ?? { ok: true }),
    ensureNetwork: rec("ensureNetwork", { ok: true }),
    ps: rec("ps", { ok: true, services: o.backendRunning ? [{ service: "backend", state: "running" }] : [] }),
    up: rec("up", o.up ?? { ok: true }),
    stop: rec("stop", o.stop ?? { ok: true }),
    restartService: rec("restartService", { ok: true }),
    checkDatabase: rec("checkDatabase", o.db ?? { ok: true, migrations: 7 }),
  };
}

function fakeOllama(o = {}) {
  const calls = [];
  let statusCalls = 0;
  return {
    calls,
    endpoint: () => "http://127.0.0.1:11434",
    status: async () => {
      statusCalls += 1;
      const running = typeof o.running === "function" ? o.running(statusCalls) : o.running ?? true;
      return { running, models: running ? o.models ?? [{ name: "qwen2.5:3b" }] : [] };
    },
    start: async () => {
      calls.push("start");
      return o.start ?? { ok: true };
    },
  };
}

function build({ docker = fakeDocker(), ollama = fakeOllama(), cfg = {}, probe, port = "free", attachUrl = null } = {}) {
  const machine = new StateMachine();
  const config = makeConfig(cfg);
  const lc = new Lifecycle({
    machine,
    docker,
    ollama,
    getConfig: () => config,
    logger: silentLogger(),
    systemInfo: WIN11,
    attachUrl,
    probe: probe ?? (async () => ({ live: true, ai: "ready" })),
    classify: async () => port,
    wait: instantWait(),
  });
  return { lc, machine, docker, ollama };
}

test("arranque: todo bien → READY y comprobaciones visibles", async () => {
  const { lc, machine, docker } = build();
  const snap = await lc.start();
  assert.equal(snap.state, S.READY);
  assert.deepEqual(machine.history, [S.INITIALIZING, S.CHECKING_DEPENDENCIES, S.SERVICES_STARTING, S.HEALTH_CHECKS, S.READY]);
  for (const name of ["windows", "compose", "docker", "ollama", "ports", "services", "backend", "database", "agents", "ai"]) {
    assert.ok(snap.checks[name], `falta la comprobación ${name}`);
  }
  assert.equal(snap.checks.database.status, "ok");
  assert.ok(docker.calls.includes("ensureNetwork") && docker.calls.includes("up"));
  assert.equal(lc.startedByApp, true);
});

test("arranque: Docker no instalado → ERROR DOCKER_NOT_INSTALLED sin tocar Compose", async () => {
  const { lc, docker } = build({ docker: fakeDocker({ installed: false }) });
  const snap = await lc.start();
  assert.equal(snap.state, S.ERROR);
  assert.equal(snap.errorCode, "DOCKER_NOT_INSTALLED");
  assert.ok(!docker.calls.includes("up"));
  assert.match(snap.detail, /docker\.com/);
});

test("arranque: Compose antiguo → ERROR COMPOSE_TOO_OLD", async () => {
  const { lc } = build({ docker: fakeDocker({ compose: "2.17.0", composeOk: false }) });
  const snap = await lc.start();
  assert.equal(snap.errorCode, "COMPOSE_TOO_OLD");
  assert.match(snap.detail, /2\.17\.0/);
});

test("arranque: Docker parado → abre Docker Desktop, espera y continúa", async () => {
  const docker = fakeDocker({ daemon: (n) => n >= 3 });
  const { lc, machine } = build({ docker });
  const snap = await lc.start();
  assert.equal(snap.state, S.READY);
  assert.ok(machine.history.includes(S.DOCKER_STARTING));
  assert.ok(docker.calls.includes("startDesktop"));
});

test("arranque: Docker parado y arranque automático desactivado → ERROR DOCKER_NOT_RUNNING", async () => {
  const docker = fakeDocker({ daemon: false });
  const { lc } = build({ docker, cfg: { "docker.autoStartDesktop": false } });
  const snap = await lc.start();
  assert.equal(snap.errorCode, "DOCKER_NOT_RUNNING");
  assert.ok(!docker.calls.includes("startDesktop"));
});

test("arranque: Docker Desktop no arranca a tiempo → ERROR DOCKER_START_TIMEOUT", async () => {
  const { lc } = build({ docker: fakeDocker({ daemon: false }) });
  const snap = await lc.start();
  assert.equal(snap.errorCode, "DOCKER_START_TIMEOUT");
});

test("arranque: puerto ocupado por otro programa → ERROR PORT_CONFLICT", async () => {
  const { lc, docker } = build({ port: "conflict" });
  const snap = await lc.start();
  assert.equal(snap.errorCode, "PORT_CONFLICT");
  assert.ok(!docker.calls.includes("up"));
});

test("arranque: puerto ocupado por un NEXARO fuera de Compose → se adopta sin gestionarlo", async () => {
  const { lc, docker } = build({ port: "nexaro" });
  const snap = await lc.start();
  assert.equal(snap.state, S.READY);
  assert.equal(lc.managed, false);
  assert.ok(!docker.calls.includes("up"));
  assert.equal(snap.checks.database.status, "skip");
});

test("arranque: stack ya en marcha → compose up idempotente y no se marca como arrancado por la app", async () => {
  const { lc } = build({ port: "nexaro", docker: fakeDocker({ backendRunning: true }) });
  await lc.start();
  assert.equal(lc.managed, true);
  assert.equal(lc.startedByApp, false);
});

test("arranque: falla compose up → ERROR SERVICES_FAILED con el error de Compose", async () => {
  const { lc } = build({ docker: fakeDocker({ up: { ok: false, error: "pull access denied" } }) });
  const snap = await lc.start();
  assert.equal(snap.errorCode, "SERVICES_FAILED");
  assert.match(snap.detail, /pull access denied/);
});

test("arranque: backend no responde → ERROR BACKEND_UNHEALTHY", async () => {
  const { lc } = build({ probe: async () => ({ live: false, ai: "unknown" }) });
  const snap = await lc.start();
  assert.equal(snap.errorCode, "BACKEND_UNHEALTHY");
});

test("arranque: falta el modelo → DEGRADED, sin descargar nada", async () => {
  const ollama = fakeOllama({ models: [{ name: "llama3:latest" }] });
  const { lc } = build({ ollama, probe: async () => ({ live: true, ai: "model_missing" }) });
  const snap = await lc.start();
  assert.equal(snap.state, S.DEGRADED);
  assert.equal(snap.checks.ollama.status, "warn");
  assert.match(snap.checks.ai.message, /no lo descarga sin tu confirmación/);
  assert.deepEqual(ollama.calls, []); // ni arrancar ni descargar
});

test("arranque: Ollama instalado y parado → se arranca", async () => {
  const ollama = fakeOllama({ running: (n) => n >= 2 });
  const { lc } = build({ ollama });
  const snap = await lc.start();
  assert.deepEqual(ollama.calls, ["start"]);
  assert.equal(snap.checks.ollama.status, "ok");
});

test("arranque: Ollama no instalado → aviso y DEGRADED, no ERROR", async () => {
  const ollama = fakeOllama({ running: false, start: { ok: false, error: "OLLAMA_NOT_INSTALLED" } });
  const { lc } = build({ ollama, probe: async () => ({ live: true, ai: "unreachable" }) });
  const snap = await lc.start();
  assert.equal(snap.state, S.DEGRADED);
  assert.match(snap.checks.ollama.message, /ollama\.com/);
});

test("arranque: modo bundled no consulta Ollama en el host", async () => {
  const ollama = fakeOllama();
  ollama.status = async () => assert.fail("no debe consultar el host");
  const { lc } = build({ ollama, cfg: { "ollama.mode": "bundled" } });
  const snap = await lc.start();
  assert.equal(snap.checks.ollama.status, "skip");
});

test("arranque: base de datos no verificable → DEGRADED", async () => {
  const { lc } = build({ docker: fakeDocker({ db: { ok: false, error: "x" } }) });
  const snap = await lc.start();
  assert.equal(snap.state, S.DEGRADED);
  assert.equal(snap.checks.database.status, "warn");
});

test("arranque: modo conectar no usa Docker", async () => {
  const docker = fakeDocker();
  const { lc } = build({ docker, attachUrl: "http://127.0.0.1:8001" });
  const snap = await lc.start();
  assert.equal(snap.state, S.READY);
  assert.deepEqual(docker.calls, []);
});

test("arranque: excepción inesperada → ERROR UNEXPECTED (nunca queda colgado)", async () => {
  const docker = fakeDocker();
  docker.detectCli = async () => {
    throw new Error("boom");
  };
  const { lc } = build({ docker });
  const snap = await lc.start();
  assert.equal(snap.errorCode, "UNEXPECTED");
});

test("arranque: reintentar tras ERROR vuelve a empezar y puede llegar a READY", async () => {
  let installed = false;
  const docker = fakeDocker();
  docker.detectCli = async () => ({ installed });
  const { lc } = build({ docker });
  assert.equal((await lc.start()).state, S.ERROR);
  installed = true;
  assert.equal((await lc.start()).state, S.READY);
});

test("arranque: llamadas simultáneas comparten una sola ejecución", async () => {
  const { lc, docker } = build();
  const [a, b] = await Promise.all([lc.start(), lc.start()]);
  assert.equal(a.state, S.READY);
  assert.equal(b.state, S.READY);
  assert.equal(docker.calls.filter((c) => c === "up").length, 1);
});

test("parada: detiene solo lo que arrancó la app y nunca con borrado", async () => {
  const { lc, docker, machine } = build();
  await lc.start();
  const res = await lc.shutdown();
  assert.equal(res.stopped, true);
  assert.equal(machine.state, S.STOPPED);
  assert.ok(docker.calls.includes("stop"));
});

test("parada: con onExit=keep no detiene los servicios", async () => {
  const { lc, docker } = build({ cfg: { "services.onExit": "keep" } });
  await lc.start();
  await lc.shutdown();
  assert.ok(!docker.calls.includes("stop"));
});

test("parada: servicios que ya estaban en marcha no se detienen", async () => {
  const { lc, docker } = build({ port: "nexaro", docker: fakeDocker({ backendRunning: true }) });
  await lc.start();
  await lc.shutdown();
  assert.ok(!docker.calls.includes("stop"));
});

test("parada: desde ERROR también se puede salir", async () => {
  const { lc, machine } = build({ docker: fakeDocker({ installed: false }) });
  await lc.start();
  await lc.shutdown();
  assert.equal(machine.state, S.STOPPED);
});
