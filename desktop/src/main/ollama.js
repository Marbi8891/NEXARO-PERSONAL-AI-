"use strict";
// Ollama Manager (Fase 5): detecta el ejecutable, comprueba la API, lo arranca si está instalado
// y parado, y lista modelos. NUNCA descarga modelos por su cuenta: eso exige confirmación explícita
// del usuario (hito 4, interfaz de instalación de modelos).

const fs = require("node:fs");
const path = require("node:path");
const processes = require("./process");
const { httpGet, parseJson } = require("./health");

function windowsCandidates(env) {
  const local = env.LOCALAPPDATA;
  const list = [];
  if (local) {
    // El instalador oficial de Ollama para Windows instala por usuario aquí.
    list.push(path.win32.join(local, "Programs", "Ollama", "ollama app.exe"));
    list.push(path.win32.join(local, "Programs", "Ollama", "ollama.exe"));
  }
  return list;
}

/** Normaliza la respuesta de /api/tags a [{name, sizeGb, parameterSize, quantization}]. */
function parseTags(body) {
  const data = parseJson(body);
  if (!data || !Array.isArray(data.models)) return null;
  return data.models
    .filter((m) => m && typeof m.name === "string")
    .map((m) => ({
      name: m.name,
      sizeGb: typeof m.size === "number" ? Math.round((m.size / 1024 ** 3) * 10) / 10 : null,
      parameterSize: m.details?.parameter_size ?? null,
      quantization: m.details?.quantization_level ?? null,
    }));
}

/** ¿Está instalado `wanted`? "qwen2.5:3b" coincide exacto; "llama3" equivale a "llama3:latest". */
function hasModel(models, wanted) {
  const target = wanted.includes(":") ? wanted : `${wanted}:latest`;
  return models.some((m) => m.name === wanted || m.name === target);
}

/**
 * Estimación orientativa de RAM necesaria: tamaño del modelo en disco + ~20 % de contexto.
 * Solo informa al usuario; no bloquea nada.
 */
function estimateRamGb(model) {
  return model.sizeGb == null ? null : Math.round(model.sizeGb * 1.2 * 10) / 10;
}

class OllamaManager {
  constructor({ getConfig, logger, platform = process.platform, env = process.env, get = httpGet, exists = fs.existsSync, launch = processes.launchDetached }) {
    this.getConfig = getConfig;
    this.logger = logger;
    this.platform = platform;
    this.env = env;
    this._get = get;
    this._exists = exists;
    this._launch = launch;
  }

  endpoint() {
    return this.getConfig().ollama.endpoint.replace(/\/$/, "");
  }

  /** Ruta del ejecutable si está instalado (configurada o estándar). */
  detectExecutable() {
    const configured = this.getConfig().ollama.executablePath;
    const candidates = configured ? [configured] : this.platform === "win32" ? windowsCandidates(this.env) : [];
    const found = candidates.find((p) => this._exists(p));
    return { installed: Boolean(found), path: found ?? null };
  }

  /** Estado de la API: {running, models, error}. */
  async status() {
    const res = await this._get(`${this.endpoint()}/api/tags`, { timeoutMs: 3000 });
    if (!res.ok) return { running: false, models: [], error: res.error || `HTTP ${res.status}` };
    const models = parseTags(res.body);
    if (!models) return { running: false, models: [], error: "RESPUESTA_NO_RECONOCIDA" };
    return { running: true, models: models.map((m) => ({ ...m, ramGb: estimateRamGb(m) })), error: null };
  }

  /** Arranca Ollama si está instalado. Prefiere "ollama app.exe" (bandeja, levanta el servidor). */
  async start() {
    const exe = this.detectExecutable();
    if (!exe.installed) return { ok: false, error: "OLLAMA_NOT_INSTALLED" };
    const isServerBinary = /(^|[\\/])ollama(\.exe)?$/i.test(exe.path);
    return this._launch(exe.path, isServerBinary ? ["serve"] : []);
  }

  /** Comprueba el modelo por defecto sin descargar nada. */
  async modelStatus() {
    const wanted = this.getConfig().ollama.defaultModel;
    const st = await this.status();
    if (!st.running) return { running: false, model: wanted, installed: false };
    return { running: true, model: wanted, installed: hasModel(st.models, wanted), models: st.models };
  }
}

module.exports = { OllamaManager, parseTags, hasModel, estimateRamGb, windowsCandidates };
