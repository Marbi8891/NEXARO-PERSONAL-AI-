"use strict";
// Docker Manager: detección de Docker y Compose, arranque de Docker Desktop y ciclo de vida del
// stack de Compose (Fases 3 y 4).
//
// Garantías: nunca `down`, `rm`, `-v` ni `--volumes` (los volúmenes guardan la base de datos y los
// modelos); solo nombres de servicio de Compose, nunca IPs de contenedor; servicios en lista blanca.

const fs = require("node:fs");
const path = require("node:path");
const processes = require("./process");

const MIN_COMPOSE = [2, 20]; // `depends_on.required` (igual que scripts/stack.sh)
const SERVICES = Object.freeze(["backend", "ollama"]);
const NETWORK_RE = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$/;
const FORBIDDEN_ARGS = new Set(["down", "rm", "-v", "--volumes", "--rmi", "prune", "kill"]);

const WIN_DOCKER_CLI = "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe";
const WIN_DOCKER_DESKTOP = "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe";

// Consulta de solo lectura (mode=ro): comprueba que la base abre y tiene migraciones aplicadas.
const DB_CHECK_CODE = [
  "import sqlite3, os",
  "db = sqlite3.connect('file:' + os.environ.get('DATABASE_PATH', '/data/nexaro.db') + '?mode=ro', uri=True)",
  "print(db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0])",
].join("\n");

/** "v2.29.1", "2.29.1-desktop.1", "5.7.1" → [major, minor] o null. */
function parseComposeVersion(text) {
  const match = /^v?(\d+)\.(\d+)/.exec(String(text).trim());
  return match ? [Number(match[1]), Number(match[2])] : null;
}

function composeVersionOk(version) {
  if (!version) return false;
  const [major, minor] = version;
  return major > MIN_COMPOSE[0] || (major === MIN_COMPOSE[0] && minor >= MIN_COMPOSE[1]);
}

function assertSafeComposeArgs(args) {
  for (const arg of args) {
    if (FORBIDDEN_ARGS.has(arg)) throw new Error(`Operación de Compose no permitida: ${arg}`);
  }
}

/** `docker compose ps --format json`: un array (Compose antiguo) o una línea JSON por servicio. */
function parseComposePs(stdout) {
  const text = String(stdout).trim();
  if (!text) return [];
  let rows;
  try {
    const parsed = JSON.parse(text);
    rows = Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    rows = text
      .split(/\r?\n/)
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }
  return rows.map((row) => ({
    service: row.Service ?? null,
    name: row.Name ?? null,
    state: row.State ?? "unknown",
    health: row.Health || null,
  }));
}

class DockerManager {
  /**
   * @param {object} opts
   * @param {string} opts.projectDir  carpeta con compose.yaml (raíz del repo o recursos de la app)
   * @param {string} opts.overrideFile  desktop/compose/compose.desktop.yaml
   * @param {() => object} opts.getConfig
   */
  constructor({ projectDir, overrideFile, getConfig, logger, platform = process.platform, run = processes.run, launch = processes.launchDetached, exists = fs.existsSync, baseEnv = process.env }) {
    this.projectDir = projectDir;
    this.overrideFile = overrideFile;
    this.getConfig = getConfig;
    this.logger = logger;
    this.platform = platform;
    this._run = run;
    this._launch = launch;
    this._exists = exists;
    this.baseEnv = baseEnv;
    this.cli = null;
  }

  _candidates() {
    const configured = this.getConfig().docker.executablePath;
    const list = [];
    if (configured) list.push(configured);
    list.push(this.platform === "win32" ? "docker.exe" : "docker");
    if (this.platform === "win32") list.push(WIN_DOCKER_CLI);
    return [...new Set(list)];
  }

  /** ¿Está instalado el cliente de Docker? Recuerda la ruta que funciona. */
  async detectCli() {
    for (const candidate of this._candidates()) {
      const res = await this._run(candidate, ["--version"], { timeoutMs: 10_000 });
      if (res.ok) {
        this.cli = candidate;
        return { installed: true, path: candidate, version: res.stdout.trim() };
      }
    }
    this.cli = null;
    return { installed: false, path: null, version: null };
  }

  _docker(args, opts = {}) {
    if (!this.cli) throw new Error("Docker no detectado: llama antes a detectCli()");
    return this._run(this.cli, args, { timeoutMs: 30_000, ...opts });
  }

  /** ¿Responde el motor de Docker? */
  async daemonStatus() {
    const res = await this._docker(["info", "--format", "{{.ServerVersion}}"], { timeoutMs: 20_000 });
    return { running: res.ok && res.stdout.trim().length > 0, serverVersion: res.ok ? res.stdout.trim() : null, error: res.ok ? null : (res.stderr || res.error || "").trim().slice(0, 300) };
  }

  async composeVersion() {
    const res = await this._docker(["compose", "version", "--short"], { timeoutMs: 15_000 });
    const version = res.ok ? parseComposeVersion(res.stdout) : null;
    return { available: res.ok, version: res.ok ? res.stdout.trim() : null, ok: composeVersionOk(version) };
  }

  desktopPath() {
    return this.getConfig().docker.desktopPath || (this.platform === "win32" ? WIN_DOCKER_DESKTOP : null);
  }

  /** Abre Docker Desktop si está instalado. No pide permisos de administrador. */
  async startDesktop() {
    const exe = this.desktopPath();
    if (!exe) return { ok: false, error: "UNSUPPORTED_PLATFORM" };
    if (!this._exists(exe)) return { ok: false, error: "DOCKER_DESKTOP_NOT_FOUND" };
    return this._launch(exe, []);
  }

  /** Entorno para Compose según el modo de Ollama. No escribe ningún .env. */
  composeEnv() {
    const cfg = this.getConfig();
    const env = { ...this.baseEnv, OLLAMA_MODEL: cfg.ollama.defaultModel, OLLAMA_NETWORK: this.networkName() };
    if (cfg.ollama.mode === "bundled") {
      env.COMPOSE_PROFILES = "ollama";
      env.NEXARO_DESKTOP_OLLAMA_URL = "http://ollama:11434";
    } else {
      // Ollama nativo en el host. El puerto sale del endpoint configurado.
      const port = new URL(cfg.ollama.endpoint).port || "11434";
      env.NEXARO_DESKTOP_OLLAMA_URL = `http://host.docker.internal:${port}`;
      delete env.COMPOSE_PROFILES;
    }
    return env;
  }

  networkName() {
    return "nexaro_desktop";
  }

  composeBaseArgs() {
    return ["compose", "--project-directory", this.projectDir, "-f", path.join(this.projectDir, "compose.yaml"), "-f", this.overrideFile];
  }

  async _compose(args, opts = {}) {
    assertSafeComposeArgs(args);
    return this._docker([...this.composeBaseArgs(), ...args], { env: this.composeEnv(), ...opts });
  }

  async ensureNetwork() {
    const name = this.networkName();
    if (!NETWORK_RE.test(name)) throw new Error("Nombre de red no válido");
    const inspect = await this._docker(["network", "inspect", name, "--format", "{{.Name}}"]);
    if (inspect.ok) return { ok: true, created: false };
    const created = await this._docker(["network", "create", name]);
    return { ok: created.ok, created: created.ok, error: created.ok ? null : created.stderr.trim().slice(0, 300) };
  }

  /** `compose up -d --wait`: construye la imagen si falta y espera a los healthchecks. */
  async up({ timeoutSec } = {}) {
    const seconds = timeoutSec ?? this.getConfig().services.upTimeoutSec;
    const res = await this._compose(["up", "-d", "--wait", "--wait-timeout", String(seconds)], { timeoutMs: (seconds + 60) * 1000 });
    return { ok: res.ok, timedOut: res.timedOut, error: res.ok ? null : tail(res.stderr || res.error) };
  }

  /** Recrea un servicio concreto sin tocar los demás ni los volúmenes. */
  async restartService(service) {
    if (!SERVICES.includes(service)) throw new Error(`Servicio desconocido: ${service}`);
    const res = await this._compose(["up", "-d", "--no-deps", "--wait", "--wait-timeout", "120", service], { timeoutMs: 180_000 });
    return { ok: res.ok, error: res.ok ? null : tail(res.stderr || res.error) };
  }

  /** Detiene los contenedores (equivale a `make down` sin borrar nada: ni contenedores ni volúmenes). */
  async stop({ timeoutSec = 30 } = {}) {
    const res = await this._compose(["stop", "--timeout", String(timeoutSec)], { timeoutMs: (timeoutSec + 30) * 1000 });
    return { ok: res.ok, error: res.ok ? null : tail(res.stderr || res.error) };
  }

  async ps() {
    const res = await this._compose(["ps", "--all", "--format", "json"]);
    return res.ok ? { ok: true, services: parseComposePs(res.stdout) } : { ok: false, services: [], error: tail(res.stderr || res.error) };
  }

  async logs(service, lines = 200) {
    if (!SERVICES.includes(service)) throw new Error(`Servicio desconocido: ${service}`);
    const n = Math.max(1, Math.min(2000, Number.parseInt(lines, 10) || 200));
    const res = await this._compose(["logs", "--no-color", "--tail", String(n), service]);
    return { ok: res.ok, text: res.ok ? res.stdout : tail(res.stderr || res.error) };
  }

  /** Base de datos accesible desde el backend (consulta fija de solo lectura). */
  async checkDatabase() {
    const res = await this._compose(["exec", "-T", "backend", "python", "-c", DB_CHECK_CODE], { timeoutMs: 20_000 });
    const migrations = Number.parseInt(res.stdout, 10);
    return res.ok && Number.isFinite(migrations) ? { ok: true, migrations } : { ok: false, error: tail(res.stderr || res.error) };
  }
}

function tail(text, max = 600) {
  const value = String(text ?? "").trim();
  return value.length > max ? `…${value.slice(-max)}` : value;
}

module.exports = { DockerManager, parseComposeVersion, composeVersionOk, parseComposePs, assertSafeComposeArgs, SERVICES, FORBIDDEN_ARGS, DB_CHECK_CODE };
