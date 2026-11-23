"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");
const { HealthMonitor } = require("../src/main/monitor");
const { Lifecycle } = require("../src/main/lifecycle");
const { StateMachine, STATES: S } = require("../src/main/states");
const { parseWindowsRelease, describeSystem } = require("../src/main/system");
const { isPortFree, classifyPort } = require("../src/main/ports");
const { makeConfig, silentLogger } = require("./helpers");

function readyLifecycle({ probe, restart = async () => ({ ok: true }), managed = true }) {
  const machine = new StateMachine();
  for (const s of [S.CHECKING_DEPENDENCIES, S.SERVICES_STARTING, S.HEALTH_CHECKS, S.READY]) machine.transition(s);
  const config = makeConfig();
  const restarts = [];
  const lc = new Lifecycle({
    machine,
    docker: { restartService: async (name) => (restarts.push(name), restart()) },
    ollama: {},
    getConfig: () => config,
    logger: silentLogger(),
    systemInfo: () => ({}),
    attachUrl: managed ? null : "http://127.0.0.1:8001",
    probe,
  });
  return { lc, machine, restarts };
}

test("monitor: READY ⇄ DEGRADED según la IA", async () => {
  let ai = "ready";
  const { lc, machine } = readyLifecycle({ probe: async () => ({ live: true, ai }) });
  const mon = new HealthMonitor({ lifecycle: lc });
  ai = "model_missing";
  assert.equal(await mon.tick(), "healthy");
  assert.equal(machine.state, S.DEGRADED);
  ai = "ready";
  await mon.tick();
  assert.equal(machine.state, S.READY);
});

test("monitor: recupera el backend tras 3 fallos seguidos", async () => {
  let live = false;
  const { lc, machine, restarts } = readyLifecycle({
    probe: async () => ({ live, ai: "ready" }),
    restart: async () => {
      live = true;
      return { ok: true };
    },
  });
  const mon = new HealthMonitor({ lifecycle: lc });
  assert.equal(await mon.tick(), "failing");
  assert.equal(await mon.tick(), "failing");
  assert.equal(await mon.tick(), "recovered");
  assert.deepEqual(restarts, ["backend"]);
  assert.equal(machine.state, S.READY);
});

test("monitor: límite de recuperaciones y backoff entre ellas; luego ERROR sin bucle", async () => {
  let clock = 0;
  const { lc, machine, restarts } = readyLifecycle({ probe: async () => ({ live: false }) });
  const timers = { setInterval: () => 1, clearInterval: () => {} };
  const mon = new HealthMonitor({ lifecycle: lc, intervalMs: 15_000, now: () => clock, timers });
  const results = [];
  for (let i = 0; i < 40 && machine.state !== S.ERROR; i += 1) {
    results.push(await mon.tick());
    clock += 15_000;
  }
  assert.equal(machine.state, S.ERROR);
  assert.equal(machine.snapshot().errorCode, "BACKEND_RECOVERY_FAILED");
  assert.equal(restarts.length, 3);
  assert.ok(results.includes("waiting"), "debe esperar entre recuperaciones");
  assert.equal(await mon.tick(), "skipped"); // en ERROR no hace nada más
});

test("monitor: backend externo caído → ERROR sin intentar Docker", async () => {
  const { lc, machine, restarts } = readyLifecycle({ probe: async () => ({ live: false }), managed: false });
  const mon = new HealthMonitor({ lifecycle: lc, failThreshold: 1 });
  assert.equal(await mon.tick(), "gave_up");
  assert.equal(machine.state, S.ERROR);
  assert.deepEqual(restarts, []);
});

test("sistema: versiones de Windows", () => {
  assert.deepEqual(parseWindowsRelease("10.0.22631"), { name: "Windows 11", build: 22631, supported: true });
  assert.deepEqual(parseWindowsRelease("10.0.19045"), { name: "Windows 10", build: 19045, supported: true });
  assert.equal(parseWindowsRelease("6.3.9600").supported, false); // Windows 8.1
  assert.equal(parseWindowsRelease("x").supported, false);
  const sys = describeSystem({ platform: "win32", release: "10.0.26100", totalmem: 16 * 1024 ** 3, arch: "x64" });
  assert.equal(sys.name, "Windows 11");
  assert.equal(sys.ramGb, 16);
  assert.equal(describeSystem({ platform: "linux", release: "6.1" }).isWindows, false);
});

test("puertos: libre, ocupado por NEXARO y conflicto (sockets reales)", async (t) => {
  const server = net.createServer();
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  t.after(() => server.close());
  const busy = server.address().port;
  assert.equal(await isPortFree(busy), false);
  assert.equal(await classifyPort(busy, { isNexaro: async () => false }), "conflict");
  assert.equal(await classifyPort(busy, { isNexaro: async () => true }), "nexaro");
  const free = await new Promise((resolve) => {
    const s = net.createServer().listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
  assert.equal(await classifyPort(free), "free");
  assert.equal(await classifyPort(0), "invalid");
});
