"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { DockerManager, parseComposeVersion, composeVersionOk, parseComposePs, assertSafeComposeArgs } = require("../src/main/docker");
const { makeConfig, silentLogger, fakeRunner } = require("./helpers");

const PROJECT = path.join(path.sep, "opt", "nexaro project");
const OVERRIDE = path.join(PROJECT, "desktop", "compose", "compose.desktop.yaml");

function manager({ respond = () => ({}), cfg = {}, platform = "win32", exists = () => true, launch } = {}) {
  const runner = fakeRunner(respond);
  const launched = [];
  const config = makeConfig(cfg);
  const dm = new DockerManager({
    projectDir: PROJECT,
    overrideFile: OVERRIDE,
    getConfig: () => config,
    logger: silentLogger(),
    platform,
    run: runner.run,
    launch: launch ?? (async (file, args) => (launched.push({ file, args }), { ok: true })),
    exists,
    baseEnv: { PATH: "/bin", COMPOSE_PROFILES: "should-be-removed" },
  });
  return { dm, calls: runner.calls, launched };
}

test("docker: versiones de Compose", () => {
  assert.deepEqual(parseComposeVersion("v2.29.1"), [2, 29]);
  assert.deepEqual(parseComposeVersion("2.29.1-desktop.1\n"), [2, 29]);
  assert.deepEqual(parseComposeVersion("5.7.1"), [5, 7]);
  assert.equal(parseComposeVersion("garbage"), null);
  assert.ok(composeVersionOk([2, 20]));
  assert.ok(composeVersionOk([3, 0]));
  assert.ok(!composeVersionOk([2, 19]));
  assert.ok(!composeVersionOk(null));
});

test("docker: detecta el CLI en PATH y, si no, en la ruta estándar de Windows", async () => {
  const { dm, calls } = manager({ respond: (file) => (file === "docker.exe" ? { ok: false, error: "ENOENT" } : { stdout: "Docker version 27.0.3\n" }) });
  const res = await dm.detectCli();
  assert.equal(res.installed, true);
  assert.equal(res.path, "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe");
  assert.deepEqual(calls.map((c) => c.args), [["--version"], ["--version"]]);
});

test("docker: CLI no encontrado", async () => {
  const { dm } = manager({ respond: () => ({ ok: false, error: "ENOENT" }) });
  assert.deepEqual(await dm.detectCli(), { installed: false, path: null, version: null });
});

test("docker: la ruta configurada tiene prioridad", async () => {
  const { dm, calls } = manager({ cfg: { "docker.executablePath": "D:\\tools\\docker.exe" } });
  await dm.detectCli();
  assert.equal(calls[0].file, "D:\\tools\\docker.exe");
});

test("docker: estado del motor", async () => {
  const { dm } = manager({ respond: (_f, args) => (args[0] === "info" ? { ok: false, stderr: "error during connect" } : {}) });
  await dm.detectCli();
  const st = await dm.daemonStatus();
  assert.equal(st.running, false);
  assert.match(st.error, /error during connect/);
});

test("docker: up usa compose.yaml + override, espera healthchecks y NO pasa -v/down", async () => {
  const { dm, calls } = manager();
  await dm.detectCli();
  await dm.up({ timeoutSec: 300 });
  const { args, opts } = calls.at(-1);
  assert.deepEqual(args, ["compose", "--project-directory", PROJECT, "-f", path.join(PROJECT, "compose.yaml"), "-f", OVERRIDE, "up", "-d", "--wait", "--wait-timeout", "300"]);
  assert.equal(opts.timeoutMs, 360_000);
  for (const bad of ["down", "-v", "--volumes", "rm"]) assert.ok(!args.includes(bad));
});

test("docker: entorno de Compose en modo nativo (host.docker.internal) sin perfil", () => {
  const { dm } = manager({ cfg: { "ollama.endpoint": "http://127.0.0.1:11500" } });
  const env = dm.composeEnv();
  assert.equal(env.NEXARO_DESKTOP_OLLAMA_URL, "http://host.docker.internal:11500");
  assert.equal(env.OLLAMA_NETWORK, "nexaro_desktop");
  assert.equal(env.OLLAMA_MODEL, "qwen2.5:3b");
  assert.equal(env.COMPOSE_PROFILES, undefined);
  assert.equal(env.PATH, "/bin");
});

test("docker: entorno de Compose en modo bundled (perfil ollama, nombre de servicio)", () => {
  const { dm } = manager({ cfg: { "ollama.mode": "bundled" } });
  const env = dm.composeEnv();
  assert.equal(env.COMPOSE_PROFILES, "ollama");
  assert.equal(env.NEXARO_DESKTOP_OLLAMA_URL, "http://ollama:11434");
  assert.doesNotMatch(JSON.stringify(env), /\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/); // sin IPs fijas
});

test("docker: stop detiene sin borrar contenedores ni volúmenes", async () => {
  const { dm, calls } = manager();
  await dm.detectCli();
  await dm.stop({ timeoutSec: 20 });
  assert.deepEqual(calls.at(-1).args.slice(-3), ["stop", "--timeout", "20"]);
});

test("docker: operaciones destructivas bloqueadas", () => {
  for (const bad of [["down"], ["down", "-v"], ["rm", "-f"], ["up", "--volumes"], ["kill"]]) {
    assert.throws(() => assertSafeComposeArgs(bad), /no permitida/);
  }
  assert.doesNotThrow(() => assertSafeComposeArgs(["up", "-d", "--wait"]));
});

test("docker: restart y logs solo para servicios de la lista blanca", async () => {
  const { dm, calls } = manager();
  await dm.detectCli();
  await assert.rejects(dm.restartService("db; rm -rf /"), /Servicio desconocido/);
  await assert.rejects(dm.logs("../../etc"), /Servicio desconocido/);
  await dm.restartService("backend");
  assert.deepEqual(calls.at(-1).args.slice(-7), ["up", "-d", "--no-deps", "--wait", "--wait-timeout", "120", "backend"]);
  await dm.logs("backend", "99999");
  assert.deepEqual(calls.at(-1).args.slice(-5), ["logs", "--no-color", "--tail", "2000", "backend"]);
});

test("docker: red propia creada solo si falta", async () => {
  let exists = false;
  const { dm, calls } = manager({ respond: (_f, args) => (args[0] === "network" && args[1] === "inspect" ? { ok: exists } : {}) });
  await dm.detectCli();
  assert.deepEqual(await dm.ensureNetwork(), { ok: true, created: true, error: null });
  assert.deepEqual(calls.at(-1).args, ["network", "create", "nexaro_desktop"]);
  exists = true;
  const before = calls.length;
  assert.deepEqual(await dm.ensureNetwork(), { ok: true, created: false });
  assert.equal(calls.length, before + 1);
});

test("docker: compose ps en formato array y en líneas JSON", () => {
  const lines = '{"Service":"backend","Name":"nexaro-backend","State":"running","Health":"healthy"}\n{"Service":"ollama","Name":"nexaro-ollama","State":"exited","Health":""}';
  assert.deepEqual(parseComposePs(lines), [
    { service: "backend", name: "nexaro-backend", state: "running", health: "healthy" },
    { service: "ollama", name: "nexaro-ollama", state: "exited", health: null },
  ]);
  assert.equal(parseComposePs('[{"Service":"backend","State":"running"}]')[0].service, "backend");
  assert.deepEqual(parseComposePs(""), []);
});

test("docker: comprobación de base de datos en solo lectura dentro del backend", async () => {
  const { dm, calls } = manager({ respond: (_f, args) => (args.includes("exec") ? { stdout: "7\n" } : {}) });
  await dm.detectCli();
  assert.deepEqual(await dm.checkDatabase(), { ok: true, migrations: 7 });
  const args = calls.at(-1).args;
  assert.deepEqual(args.slice(7, 11), ["exec", "-T", "backend", "python"]);
  assert.match(args.at(-1), /mode=ro/);
});

test("docker: abre Docker Desktop solo si existe y no en otras plataformas", async () => {
  const a = manager();
  assert.deepEqual(await a.dm.startDesktop(), { ok: true });
  assert.equal(a.launched[0].file, "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe");
  const b = manager({ exists: () => false });
  assert.deepEqual(await b.dm.startDesktop(), { ok: false, error: "DOCKER_DESKTOP_NOT_FOUND" });
  const c = manager({ platform: "linux" });
  assert.deepEqual(await c.dm.startDesktop(), { ok: false, error: "UNSUPPORTED_PLATFORM" });
});
