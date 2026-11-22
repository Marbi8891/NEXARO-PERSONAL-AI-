"use strict";
// Persistencia de configuración y logs en una carpeta temporal real.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { ConfigManager, DEFAULTS, normalize } = require("../src/main/config");
const { Logger, redact, redactString } = require("../src/main/logger");
const { appDirs, composeProjectDir, overrideFile } = require("../src/main/paths");

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "nexaro-desktop-"));
}

test("config: primera ejecución crea el archivo con los valores por defecto", (t) => {
  const dir = tmp();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "config", "desktop-config.json");
  const cm = new ConfigManager(file);
  assert.deepEqual(cm.load(), DEFAULTS);
  cm.save();
  assert.deepEqual(JSON.parse(fs.readFileSync(file, "utf8")), DEFAULTS);
});

test("config: los cambios persisten entre instancias y dejan copia .bak", (t) => {
  const dir = tmp();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "desktop-config.json");
  const a = new ConfigManager(file);
  a.load();
  a.save();
  a.update({ "ollama.defaultModel": "llama3.2:3b", "window.closeBehavior": "tray", "services.onExit": "keep" });
  const b = new ConfigManager(file);
  const cfg = b.load();
  assert.equal(cfg.ollama.defaultModel, "llama3.2:3b");
  assert.equal(cfg.window.closeBehavior, "tray");
  assert.equal(cfg.services.onExit, "keep");
  assert.ok(fs.existsSync(`${file}.bak`));
});

test("config: update rechaza claves desconocidas y valores no válidos sin guardar", (t) => {
  const dir = tmp();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const cm = new ConfigManager(path.join(dir, "c.json"));
  cm.load();
  assert.throws(() => cm.update({ "docker.command": "rm -rf /" }), /desconocido/);
  assert.throws(() => cm.update({ "ollama.endpoint": "http://evil.example.com:11434" }), /no válido/);
  assert.throws(() => cm.update({ "ollama.defaultModel": "qwen; calc.exe" }), /no válido/);
  assert.throws(() => cm.update({ "backend.port": 80 }), /no válido/);
  assert.throws(() => cm.update({ "docker.executablePath": "relative\\docker.exe" }), /no válido/);
  assert.equal(cm.get().ollama.endpoint, DEFAULTS.ollama.endpoint);
});

test("config: archivo dañado → valores por defecto, aviso y copia .corrupt", (t) => {
  const dir = tmp();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "c.json");
  fs.writeFileSync(file, "{ esto no es json");
  const cm = new ConfigManager(file);
  assert.deepEqual(cm.load(), DEFAULTS);
  assert.equal(cm.warnings.length, 1);
  assert.ok(fs.existsSync(`${file}.corrupt`));
});

test("config: valores no válidos sueltos se sustituyen campo a campo", () => {
  const { config, warnings } = normalize({ ollama: { mode: "cloud", defaultModel: "phi3" }, services: { upTimeoutSec: -1 }, extra: { x: 1 } });
  assert.equal(config.ollama.mode, "native");
  assert.equal(config.ollama.defaultModel, "phi3");
  assert.equal(config.services.upTimeoutSec, DEFAULTS.services.upTimeoutSec);
  assert.equal(warnings.length, 2);
  assert.equal(config.extra, undefined);
});

test("config: copia de seguridad y restauración", (t) => {
  const dir = tmp();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const cm = new ConfigManager(path.join(dir, "c.json"));
  cm.load();
  cm.update({ "ollama.defaultModel": "mistral:7b" });
  const backup = cm.backup(path.join(dir, "backups"), new Date("2026-11-22T10:00:00Z"));
  assert.match(path.basename(backup), /^desktop-config-2026-11-22T10-00-00-000Z\.json$/);
  cm.update({ "ollama.defaultModel": "phi3" });
  cm.restore(backup);
  assert.equal(cm.get().ollama.defaultModel, "mistral:7b");
});

test("paths: carpetas separadas fuera de la instalación", (t) => {
  const dir = tmp();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const dirs = appDirs(dir);
  for (const key of ["config", "logs", "backups", "diagnostics"]) assert.ok(fs.statSync(dirs[key]).isDirectory());
  assert.equal(dirs.configFile, path.join(dir, "config", "desktop-config.json"));
  const res = path.join(path.sep, "app", "resources");
  assert.equal(composeProjectDir({ isPackaged: true, resourcesPath: res, appPath: "/x" }), path.join(res, "nexaro"));
  assert.equal(composeProjectDir({ isPackaged: false, resourcesPath: res, appPath: path.join(path.sep, "repo", "desktop") }), path.resolve(path.sep, "repo"));
  assert.equal(composeProjectDir({ isPackaged: true, resourcesPath: res, configured: "/custom", exists: () => true }), "/custom");
  assert.equal(overrideFile({ isPackaged: true, resourcesPath: res }), path.join(res, "compose", "compose.desktop.yaml"));
});

test("logger: redacta secretos por clave y por patrón", () => {
  const out = redact({ password: "hunter2", nested: { apiKey: "abc", ok: "visible" }, msg: "Authorization: Bearer abcdefghijklmnop" });
  assert.equal(out.password, "[REDACTED]");
  assert.equal(out.nested.apiKey, "[REDACTED]");
  assert.equal(out.nested.ok, "visible");
  assert.doesNotMatch(out.msg, /abcdefghijklmnop/);
  assert.doesNotMatch(redactString("token=s3cr3tvalue other"), /s3cr3tvalue/);
  assert.doesNotMatch(redactString("http://user:pa55@127.0.0.1:8001/"), /pa55/);
  assert.doesNotMatch(redactString("clave nxr_live_ABCDEFGHIJKLMNOP"), /ABCDEFGHIJKLMNOP/);
  // Clave ficticia construida en tiempo de ejecución para que gitleaks no la confunda con una real.
  const fakeAwsKey = ["AKIA", "ABCDEFGHIJKLMNOP"].join("");
  assert.ok(!redactString(fakeAwsKey).includes(fakeAwsKey));
});

test("logger: escribe JSON por línea, redacta y rota por tamaño", (t) => {
  const dir = tmp();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const log = new Logger({ dir, maxBytes: 300, maxFiles: 3 });
  for (let i = 0; i < 20; i += 1) log.info(`línea ${i}`, { token: "secreto", i });
  log.debug("no se escribe (nivel info)");
  const files = fs.readdirSync(dir).sort();
  assert.deepEqual(files, ["desktop.log", "desktop.log.1", "desktop.log.2"]);
  const all = files.map((f) => fs.readFileSync(path.join(dir, f), "utf8")).join("");
  assert.doesNotMatch(all, /secreto/);
  assert.doesNotMatch(all, /no se escribe/);
  const last = fs.readFileSync(path.join(dir, "desktop.log"), "utf8").trim().split("\n").at(-1);
  assert.equal(JSON.parse(last).msg, "línea 19");
});
