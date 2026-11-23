"use strict";
// Configuration Manager (Fases 8 y 12): JSON en la carpeta de datos del usuario, validado campo a
// campo. Un valor no válido se sustituye por el predeterminado y se informa; nunca rompe el arranque.

const fs = require("node:fs");
const path = require("node:path");

const CONFIG_VERSION = 1;

const DEFAULTS = Object.freeze({
  version: CONFIG_VERSION,
  firstRunCompleted: false,
  backend: { port: 8001 },
  services: {
    autoStart: true, // arrancar los servicios al abrir la app
    onExit: "stop", // "stop": detener los servicios que arrancó la app; "keep": dejarlos en marcha
    composeProjectDir: "", // vacío = el que trae la app (o la raíz del repo en desarrollo)
    upTimeoutSec: 600, // la primera vez construye la imagen
  },
  docker: {
    executablePath: "", // vacío = buscar docker en PATH y rutas estándar
    desktopPath: "", // vacío = ruta estándar de Docker Desktop
    autoStartDesktop: true,
    startTimeoutSec: 180,
  },
  ollama: {
    mode: "native", // "native": Ollama para Windows; "bundled": contenedor del perfil `ollama`
    endpoint: "http://127.0.0.1:11434",
    executablePath: "",
    autoStart: true,
    defaultModel: "qwen2.5:3b",
  },
  window: { closeBehavior: "exit", startMinimized: false },
  startup: { launchOnLogin: false },
});

const ENUMS = {
  "services.onExit": ["stop", "keep"],
  "ollama.mode": ["native", "bundled"],
  "window.closeBehavior": ["exit", "tray"],
};

const MODEL_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;

function isLocalHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname) && url.pathname === "/" && !url.search;
  } catch {
    return false;
  }
}

function isSafePath(value) {
  return value === "" || (value.length <= 1024 && !value.includes("\0") && (path.isAbsolute(value) || path.win32.isAbsolute(value)));
}

// Validador por campo: devuelve true si el valor es aceptable.
const VALIDATORS = {
  "firstRunCompleted": (v) => typeof v === "boolean",
  "backend.port": (v) => Number.isInteger(v) && v >= 1024 && v <= 65535,
  "services.autoStart": (v) => typeof v === "boolean",
  "services.composeProjectDir": (v) => typeof v === "string" && isSafePath(v),
  "services.upTimeoutSec": (v) => Number.isInteger(v) && v >= 30 && v <= 3600,
  "docker.executablePath": (v) => typeof v === "string" && isSafePath(v),
  "docker.desktopPath": (v) => typeof v === "string" && isSafePath(v),
  "docker.autoStartDesktop": (v) => typeof v === "boolean",
  "docker.startTimeoutSec": (v) => Number.isInteger(v) && v >= 10 && v <= 900,
  "ollama.endpoint": (v) => typeof v === "string" && isLocalHttpUrl(v.endsWith("/") ? v : `${v}/`),
  "ollama.executablePath": (v) => typeof v === "string" && isSafePath(v),
  "ollama.autoStart": (v) => typeof v === "boolean",
  "ollama.defaultModel": (v) => typeof v === "string" && MODEL_RE.test(v),
  "window.startMinimized": (v) => typeof v === "boolean",
  "startup.launchOnLogin": (v) => typeof v === "boolean",
};
for (const [key, values] of Object.entries(ENUMS)) VALIDATORS[key] = (v) => values.includes(v);

function getPath(obj, dotted) {
  return dotted.split(".").reduce((acc, k) => (acc && typeof acc === "object" ? acc[k] : undefined), obj);
}

function setPath(obj, dotted, value) {
  const keys = dotted.split(".");
  let cur = obj;
  for (const k of keys.slice(0, -1)) cur = cur[k];
  cur[keys.at(-1)] = value;
}

/** Fusiona `raw` con los valores por defecto. Devuelve {config, warnings}. Ignora claves desconocidas. */
function normalize(raw) {
  const config = structuredClone(DEFAULTS);
  const warnings = [];
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  for (const [key, valid] of Object.entries(VALIDATORS)) {
    const value = getPath(source, key);
    if (value === undefined) continue;
    if (valid(value)) setPath(config, key, value);
    else warnings.push(`Valor no válido en ${key}; se usa el predeterminado`);
  }
  if (config.ollama.endpoint.endsWith("/")) config.ollama.endpoint = config.ollama.endpoint.slice(0, -1);
  return { config, warnings };
}

function writeAtomic(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, text, { encoding: "utf8", mode: 0o600 });
  fs.renameSync(tmp, file);
}

class ConfigManager {
  constructor(file) {
    this.file = file;
    this.config = structuredClone(DEFAULTS);
    this.warnings = [];
  }

  load() {
    let raw = null;
    try {
      raw = JSON.parse(fs.readFileSync(this.file, "utf8"));
    } catch (error) {
      if (error.code !== "ENOENT") {
        this.warnings = ["La configuración estaba dañada; se usan los valores predeterminados (copia en .corrupt)"];
        try {
          fs.copyFileSync(this.file, `${this.file}.corrupt`);
        } catch {
          /* sin copia posible: se sigue con los valores por defecto */
        }
        ({ config: this.config } = normalize(null));
        return this.config;
      }
    }
    const { config, warnings } = normalize(raw);
    this.config = config;
    this.warnings = warnings;
    return this.config;
  }

  get() {
    return structuredClone(this.config);
  }

  /** Aplica cambios parciales {"ollama.defaultModel": "..."} validados. Lanza si alguno no es válido. */
  update(changes) {
    const next = structuredClone(this.config);
    for (const [key, value] of Object.entries(changes)) {
      const valid = VALIDATORS[key];
      if (!valid) throw new Error(`Ajuste desconocido: ${key}`);
      if (!valid(value)) throw new Error(`Valor no válido para ${key}`);
      setPath(next, key, value);
    }
    this.config = normalize(next).config;
    this.save();
    return this.get();
  }

  save() {
    if (fs.existsSync(this.file)) fs.copyFileSync(this.file, `${this.file}.bak`);
    writeAtomic(this.file, `${JSON.stringify(this.config, null, 2)}\n`);
  }

  /** Copia de seguridad con fecha en `dir`. Devuelve la ruta. */
  backup(dir, now = new Date()) {
    const stamp = now.toISOString().replace(/[:.]/g, "-");
    const target = path.join(dir, `desktop-config-${stamp}.json`);
    writeAtomic(target, `${JSON.stringify(this.config, null, 2)}\n`);
    return target;
  }

  /** Restaura desde una copia; los valores no válidos se descartan igual que al cargar. */
  restore(file) {
    const raw = JSON.parse(fs.readFileSync(file, "utf8"));
    const { config, warnings } = normalize(raw);
    this.config = config;
    this.save();
    return warnings;
  }
}

module.exports = { ConfigManager, DEFAULTS, normalize, isLocalHttpUrl, VALIDATORS };
