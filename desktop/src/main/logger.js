"use strict";
// Logging System: archivo con rotación por tamaño y redacción de secretos antes de escribir.

const fs = require("node:fs");
const path = require("node:path");

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

// Claves y patrones que nunca deben acabar en logs ni en diagnósticos exportados.
const SECRET_KEY_RE = /(pass(word)?|secret|token|api[_-]?key|authorization|cookie|session|credential|private[_-]?key)/i;
const SECRET_PATTERNS = [
  [/(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}/gi, "$1[REDACTED]"],
  [/((?:pass(?:word)?|secret|token|api[_-]?key|session)\s*[=:]\s*)("?)[^\s",;]+\2/gi, "$1[REDACTED]"],
  [/(nxr_[a-z]*_?)[A-Za-z0-9]{12,}/g, "$1[REDACTED]"], // claves de API de NEXARO
  [/(AKIA|ASIA)[A-Z0-9]{16}/g, "[REDACTED_AWS_KEY]"],
  [/(https?:\/\/)[^\s/:@]+:[^\s/@]+@/gi, "$1[REDACTED]@"], // credenciales en URLs
];

function redactString(text) {
  let out = String(text);
  for (const [re, replacement] of SECRET_PATTERNS) out = out.replace(re, replacement);
  return out;
}

/** Copia profunda con secretos ocultos (por nombre de clave y por patrón). */
function redact(value, depth = 0) {
  if (depth > 8) return "[…]";
  if (typeof value === "string") return redactString(value);
  if (Array.isArray(value)) return value.map((v) => redact(v, depth + 1));
  if (value instanceof Error) return redactString(`${value.name}: ${value.message}`);
  if (value && typeof value === "object") {
    const out = {};
    for (const [k, v] of Object.entries(value)) out[k] = SECRET_KEY_RE.test(k) ? "[REDACTED]" : redact(v, depth + 1);
    return out;
  }
  return value;
}

class Logger {
  constructor({ dir, file = "desktop.log", level = "info", maxBytes = 2 * 1024 * 1024, maxFiles = 5, mirror = false } = {}) {
    this.dir = dir;
    this.file = dir ? path.join(dir, file) : null;
    this.level = LEVELS[level] ?? LEVELS.info;
    this.maxBytes = maxBytes;
    this.maxFiles = maxFiles;
    this.mirror = mirror;
    if (dir) fs.mkdirSync(dir, { recursive: true });
  }

  _rotate() {
    if (!this.file) return;
    let size = 0;
    try {
      size = fs.statSync(this.file).size;
    } catch {
      return;
    }
    if (size < this.maxBytes) return;
    for (let i = this.maxFiles - 1; i >= 1; i -= 1) {
      const from = i === 1 ? this.file : `${this.file}.${i - 1}`;
      try {
        fs.renameSync(from, `${this.file}.${i}`);
      } catch {
        /* el archivo puede no existir todavía */
      }
    }
  }

  log(level, message, data) {
    if ((LEVELS[level] ?? 0) < this.level) return;
    const entry = { ts: new Date().toISOString(), level, msg: redactString(message) };
    if (data !== undefined) entry.data = redact(data);
    const line = `${JSON.stringify(entry)}\n`;
    if (this.mirror) process.stdout.write(line);
    if (!this.file) return;
    try {
      this._rotate();
      // Escritura síncrona: al salir no quedan líneas en memoria sin volcar (Fase 14).
      fs.appendFileSync(this.file, line, { encoding: "utf8", mode: 0o600 });
    } catch {
      /* un fallo de log nunca tumba la aplicación */
    }
  }

  debug(m, d) { this.log("debug", m, d); }
  info(m, d) { this.log("info", m, d); }
  warn(m, d) { this.log("warn", m, d); }
  error(m, d) { this.log("error", m, d); }
}

module.exports = { Logger, redact, redactString };
