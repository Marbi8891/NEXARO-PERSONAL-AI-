"use strict";
// IPC, navegación, permisos y ejecución de procesos (Fase 10).
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const fs = require("node:fs");
const { registerIpc, CHANNELS, validateArgs } = require("../src/main/ipc");
const { webPreferences, makeNavigationPolicy, isSafeExternalUrl, isAllowedPermission } = require("../src/main/security");
const processes = require("../src/main/process");

const RENDERER = path.resolve(__dirname, "..", "src", "renderer");
const STARTUP = pathToFileURL(path.join(RENDERER, "startup.html")).href;
const policy = makeNavigationPolicy({ backendUrl: "http://127.0.0.1:8001", rendererDir: RENDERER });

function fakeIpcMain() {
  const handlers = new Map();
  return { handlers, handle: (ch, fn) => handlers.set(ch, fn) };
}

const allHandlers = () => Object.fromEntries(Object.keys(CHANNELS).map((c) => [c, async () => `ok:${c}`]));

test("ipc: solo se registran los canales de la lista blanca", () => {
  const ipcMain = fakeIpcMain();
  registerIpc({ ipcMain, handlers: allHandlers(), isAllowedSender: () => true });
  assert.deepEqual([...ipcMain.handlers.keys()].sort(), ["desktop:get-state", "desktop:open-app", "desktop:open-logs", "desktop:retry"]);
  assert.throws(() => registerIpc({ ipcMain: fakeIpcMain(), handlers: { ...allHandlers(), "desktop:exec": async () => {} }, isAllowedSender: () => true }), /lista blanca/);
  assert.ok(!Object.keys(CHANNELS).some((c) => /exec|shell|powershell|command|file|fs/i.test(c)));
});

test("ipc: rechaza remitentes que no son páginas propias", async () => {
  const ipcMain = fakeIpcMain();
  registerIpc({ ipcMain, handlers: allHandlers(), isAllowedSender: (u) => policy.isDesktopPage(u) });
  const call = (url, ...args) => ipcMain.handlers.get("desktop:retry")({ senderFrame: { url } }, ...args);
  assert.equal(await call(STARTUP), "ok:desktop:retry");
  await assert.rejects(call("http://127.0.0.1:8001/#/chat"), /remitente/); // el frontend web no controla servicios
  await assert.rejects(call("https://evil.example.com/"), /remitente/);
  await assert.rejects(call("file:///C:/Users/ana/Downloads/x.html"), /remitente/);
  await assert.rejects(call(""), /remitente/);
});

test("ipc: rechaza argumentos inesperados", async () => {
  const ipcMain = fakeIpcMain();
  registerIpc({ ipcMain, handlers: allHandlers(), isAllowedSender: () => true });
  await assert.rejects(ipcMain.handlers.get("desktop:open-logs")({ senderFrame: { url: STARTUP } }, "C:\\Windows\\System32"), /argumentos/);
  assert.equal(validateArgs("desktop:nope", []), false);
});

test("navegación: solo el backend local y las pantallas propias", () => {
  assert.ok(policy.isAllowed("http://127.0.0.1:8001/#/dashboard"));
  assert.ok(policy.isAllowed(STARTUP));
  assert.ok(!policy.isAllowed("http://localhost:8001/")); // otro origen
  assert.ok(!policy.isAllowed("http://127.0.0.1:11434/api/tags"));
  assert.ok(!policy.isAllowed("https://example.com/"));
  assert.ok(!policy.isAllowed(pathToFileURL(path.join(RENDERER, "..", "main", "main.js")).href));
  assert.ok(!policy.isAllowed("javascript:alert(1)"));
  assert.ok(!policy.isDesktopPage("http://127.0.0.1:8001/"));
});

test("navegación: enlaces externos solo https y no locales", () => {
  assert.ok(isSafeExternalUrl("https://ollama.com/download"));
  assert.ok(!isSafeExternalUrl("http://example.com"));
  assert.ok(!isSafeExternalUrl("file:///C:/Windows/System32/cmd.exe"));
  assert.ok(!isSafeExternalUrl("https://127.0.0.1/"));
  assert.ok(!isSafeExternalUrl("https://user:pass@example.com/"));
  assert.ok(!isSafeExternalUrl("ms-settings:"));
});

test("ventana: preferencias seguras", () => {
  const prefs = webPreferences("/x/preload.js");
  assert.equal(prefs.contextIsolation, true);
  assert.equal(prefs.nodeIntegration, false);
  assert.equal(prefs.sandbox, true);
  assert.equal(prefs.webSecurity, true);
  assert.equal(prefs.webviewTag, false);
  assert.equal(prefs.allowRunningInsecureContent, false);
});

test("permisos: solo notificaciones y escritura en portapapeles", () => {
  assert.ok(isAllowedPermission("notifications"));
  for (const p of ["media", "geolocation", "openExternal", "fileSystem", "hid", "serial", "usb"]) assert.ok(!isAllowedPermission(p));
});

test("procesos: lista blanca de ejecutables y argumentos como lista", async () => {
  assert.throws(() => processes.assertAllowed("powershell.exe", ["-c", "x"]), /no permitido/);
  assert.throws(() => processes.assertAllowed("cmd.exe", []), /no permitido/);
  assert.throws(() => processes.assertAllowed("/bin/sh", []), /no permitido/);
  assert.throws(() => processes.assertAllowed("docker", "ps -a"), TypeError);
  assert.doesNotThrow(() => processes.assertAllowed("C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe", ["ps"]));
  assert.doesNotThrow(() => processes.assertAllowed("C:\\Users\\a\\AppData\\Local\\Programs\\Ollama\\ollama app.exe", []));
  await assert.rejects(async () => processes.run("bash", ["-c", "echo hi"]), /no permitido/);
});

test("procesos: un binario inexistente no lanza, devuelve ENOENT", async () => {
  const res = await processes.run("/nonexistent/docker", ["--version"], { timeoutMs: 2000 });
  assert.equal(res.ok, false);
  assert.equal(res.error, "ENOENT");
});

test("procesos: ningún módulo usa shell: true ni exec()", () => {
  const dir = path.join(__dirname, "..", "src");
  const files = [];
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : files.push(path.join(d, e.name))));
  walk(dir);
  for (const f of files.filter((x) => x.endsWith(".js"))) {
    // Sin comentarios de línea; `.exec(` de expresiones regulares no cuenta.
    const src = fs.readFileSync(f, "utf8").split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
    assert.doesNotMatch(src, /shell:\s*true/, f);
    assert.doesNotMatch(src, /(?<![.\w])exec(Sync)?\s*\(|require\("node:child_process"\)\.exec\b/, f);
    assert.doesNotMatch(src, /nodeIntegration:\s*true/, f);
    assert.doesNotMatch(src, /\.innerHTML\s*=/, f);
  }
});

test("preload: expone solo funciones fijas", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "src", "preload", "preload.js"), "utf8");
  const invoked = [...src.matchAll(/ipcRenderer\.invoke\("([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(invoked, Object.keys(CHANNELS).sort());
  assert.doesNotMatch(src, /ipcRenderer\.(send|sendSync)\(/);
  assert.doesNotMatch(src, /exposeInMainWorld\([^)]*ipcRenderer\s*\)/);
});
