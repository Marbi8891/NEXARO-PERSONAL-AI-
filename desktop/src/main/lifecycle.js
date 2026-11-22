"use strict";
// Desktop Lifecycle Manager: orquesta el arranque (Fase 3) y la parada (Fase 14) sobre la máquina
// de estados. Sin Electron: todas las dependencias se inyectan y se prueban con dobles.

const { STATES } = require("./states");
const { describeError } = require("./errors");
const { waitFor, probeBackend } = require("./health");
const { classifyPort } = require("./ports");

const S = STATES;

/** Espera `promise` como mucho `ms`; el temporizador se cancela siempre (no retiene el proceso). */
function withTimeout(promise, ms, fallback) {
  let timer;
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve(fallback), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
const COMPOSE_PORT = 8001; // fijo en compose.yaml (127.0.0.1:8001:8000)

class Lifecycle {
  /**
   * @param {object} deps
   * @param {import('./states').StateMachine} deps.machine
   * @param {string|null} deps.attachUrl  modo "conectar": backend ya arrancado, no se gestiona Docker
   */
  constructor({ machine, docker, ollama, getConfig, logger, systemInfo, attachUrl = null, probe = probeBackend, classify = classifyPort, wait = waitFor }) {
    this.machine = machine;
    this.docker = docker;
    this.ollama = ollama;
    this.getConfig = getConfig;
    this.logger = logger;
    this.systemInfo = systemInfo;
    this.attachUrl = attachUrl;
    this._probe = probe;
    this._classify = classify;
    this._wait = wait;
    this.startedByApp = false; // solo se detiene al salir lo que arrancó esta sesión
    this.managed = !attachUrl; // false = backend externo (modo desarrollo "conectar")
    this._running = null;
  }

  backendUrl() {
    return this.attachUrl ?? `http://127.0.0.1:${COMPOSE_PORT}`;
  }

  _fail(code, detail = null) {
    const { title, action } = describeError(code);
    this.logger.error(`Arranque fallido: ${code}`, { detail });
    if (this.machine.state !== S.ERROR) {
      this.machine.transition(S.ERROR, { message: title, detail: detail ? `${action}\n\n${detail}` : action, errorCode: code });
    }
    return this.machine.snapshot();
  }

  /** Arranque completo. Llamadas concurrentes comparten la misma ejecución. */
  start() {
    if (!this._running) {
      this._running = this._start().finally(() => {
        this._running = null;
      });
    }
    return this._running;
  }

  async _start() {
    const m = this.machine;
    if ([S.ERROR, S.STOPPED].includes(m.state)) m.transition(S.INITIALIZING);
    if (m.state !== S.INITIALIZING) return m.snapshot();
    try {
      m.transition(S.CHECKING_DEPENDENCIES);
      const sys = this.systemInfo();
      m.setCheck("windows", sys.supported ? "ok" : "warn", sys.isWindows ? `${sys.name} (build ${sys.build})` : `${sys.name} (solo desarrollo)`);

      if (!this.managed) {
        m.setCheck("docker", "skip", "Modo conectar: el backend lo gestiona otro proceso");
        m.transition(S.HEALTH_CHECKS);
        return await this._healthChecks();
      }

      const cfg = this.getConfig();
      const cli = await this.docker.detectCli();
      if (!cli.installed) {
        m.setCheck("docker", "fail", "No instalado");
        return this._fail("DOCKER_NOT_INSTALLED");
      }
      const compose = await this.docker.composeVersion();
      if (!compose.ok) {
        m.setCheck("compose", "fail", compose.version ?? "No disponible");
        return this._fail("COMPOSE_TOO_OLD", compose.version ? `Versión instalada: ${compose.version}` : null);
      }
      m.setCheck("compose", "ok", compose.version);

      let daemon = await this.docker.daemonStatus();
      if (!daemon.running) {
        if (!cfg.docker.autoStartDesktop) {
          m.setCheck("docker", "fail", "Detenido");
          return this._fail("DOCKER_NOT_RUNNING");
        }
        m.transition(S.DOCKER_STARTING);
        m.setCheck("docker", "pending", "Arrancando Docker Desktop…");
        const launched = await this.docker.startDesktop();
        if (!launched.ok) {
          m.setCheck("docker", "fail", "No se pudo abrir Docker Desktop");
          return this._fail(launched.error === "DOCKER_DESKTOP_NOT_FOUND" ? "DOCKER_NOT_INSTALLED" : "DOCKER_NOT_RUNNING", launched.error);
        }
        const waited = await this._wait(async () => (await this.docker.daemonStatus()).running, { timeoutMs: cfg.docker.startTimeoutSec * 1000, baseMs: 2000, maxMs: 10_000 });
        if (!waited.ok) {
          m.setCheck("docker", "fail", "Sin respuesta");
          return this._fail("DOCKER_START_TIMEOUT");
        }
        daemon = await this.docker.daemonStatus();
      }
      m.setCheck("docker", "ok", `Motor ${daemon.serverVersion ?? "en marcha"}`);

      await this._ensureOllama(cfg);

      // Puerto: libre, ocupado por un NEXARO que responde, u ocupado por otro programa.
      const portState = await this._classify(COMPOSE_PORT, {
        isNexaro: async () => (await this._probe(this.backendUrl())).live,
      });
      if (portState === "conflict") {
        m.setCheck("ports", "fail", `${COMPOSE_PORT} ocupado por otro programa`);
        return this._fail("PORT_CONFLICT", `Puerto ${COMPOSE_PORT} en 127.0.0.1.`);
      }
      m.setCheck("ports", "ok", portState === "nexaro" ? `${COMPOSE_PORT} (NEXARO ya en marcha)` : `${COMPOSE_PORT} libre`);

      const before = await this.docker.ps();
      const backendRunning = before.services.some((s) => s.service === "backend" && s.state === "running");
      if (portState === "nexaro" && !backendRunning) {
        // Lo sirve un proceso fuera de Compose (p. ej. `make run`): se usa tal cual, sin gestionarlo.
        this.managed = false;
        m.setCheck("services", "skip", "Backend externo detectado; no se gestiona");
        m.transition(S.HEALTH_CHECKS);
        return await this._healthChecks();
      }

      m.transition(S.SERVICES_STARTING);
      if (!cfg.services.autoStart && !backendRunning) {
        m.setCheck("services", "fail", "Detenidos");
        return this._fail("SERVICES_NOT_STARTED");
      }
      if (cfg.services.autoStart) {
        const network = await this.docker.ensureNetwork();
        if (!network.ok) return this._fail("NETWORK_FAILED", network.error);
        m.setCheck("services", "pending", backendRunning ? "Comprobando contenedores…" : "Arrancando contenedores (la primera vez puede tardar varios minutos)…");
        const up = await this.docker.up();
        if (!up.ok) {
          m.setCheck("services", "fail", up.timedOut ? "Tiempo agotado" : "Error de Compose");
          return this._fail("SERVICES_FAILED", up.error);
        }
        this.startedByApp = this.startedByApp || !backendRunning;
      }
      m.setCheck("services", "ok", "Contenedores en marcha");
      m.transition(S.HEALTH_CHECKS);
      return await this._healthChecks();
    } catch (error) {
      this.logger.error("Excepción en el arranque", { error });
      return this._fail("UNEXPECTED", error.message);
    }
  }

  /** Ollama nativo: si está instalado y parado, lo arranca. Nunca es un error fatal. */
  async _ensureOllama(cfg) {
    const m = this.machine;
    if (cfg.ollama.mode === "bundled") {
      m.setCheck("ollama", "skip", "Ollama en Docker (perfil incluido); se comprueba con el backend");
      return;
    }
    let status = await this.ollama.status();
    if (!status.running && cfg.ollama.autoStart) {
      const started = await this.ollama.start();
      if (started.ok) {
        m.setCheck("ollama", "pending", "Arrancando Ollama…");
        await this._wait(async () => (await this.ollama.status()).running, { timeoutMs: 45_000, baseMs: 1000, maxMs: 5000 });
        status = await this.ollama.status();
      } else if (started.error === "OLLAMA_NOT_INSTALLED") {
        m.setCheck("ollama", "warn", "No instalado: el chat no funcionará. Descárgalo de https://ollama.com/download");
        return;
      }
    }
    if (!status.running) {
      m.setCheck("ollama", "warn", "No responde en " + this.ollama.endpoint());
      return;
    }
    const wanted = cfg.ollama.defaultModel;
    const installed = status.models.some((x) => x.name === wanted || x.name === `${wanted}:latest`);
    m.setCheck("ollama", installed ? "ok" : "warn", installed ? `En marcha, modelo ${wanted} instalado` : `En marcha, falta el modelo ${wanted} (no se descarga sin tu confirmación)`);
  }

  async _healthChecks() {
    const m = this.machine;
    const url = this.backendUrl();
    const live = await this._wait(async () => {
      const r = await this._probe(url);
      return r.live ? r : null;
    }, { timeoutMs: 120_000, baseMs: 1000, maxMs: 5000 });
    if (!live.ok) {
      m.setCheck("backend", "fail", "Sin respuesta en " + url);
      return this._fail("BACKEND_UNHEALTHY");
    }
    m.setCheck("backend", "ok", "API en " + url);
    m.setCheck("agents", "ok", "Integrado en el backend");

    let dbOk = true;
    if (this.managed) {
      const db = await this.docker.checkDatabase();
      dbOk = db.ok;
      m.setCheck("database", db.ok ? "ok" : "warn", db.ok ? `SQLite, ${db.migrations} migraciones aplicadas` : "No se pudo verificar");
    } else {
      m.setCheck("database", "skip", "Backend externo");
    }

    return this.applyProbe(live.value, { dbOk });
  }

  /** Traduce el resultado de una sonda a READY o DEGRADED (lo usa también el monitor). */
  applyProbe(result, { dbOk = true } = {}) {
    const m = this.machine;
    const model = this.getConfig().ollama.defaultModel;
    const aiText = {
      ready: ["ok", "Ollama conectado y modelo listo"],
      connected: ["ok", "Ollama conectado"],
      model_missing: ["warn", `Falta el modelo ${model}. Instálalo desde Ollama; NEXARO no lo descarga sin tu confirmación.`],
      unreachable: ["warn", "El backend no alcanza a Ollama: el chat no funcionará hasta que responda."],
    }[result.ai] ?? ["warn", "Estado de la IA desconocido"];
    m.setCheck("ai", aiText[0], aiText[1]);
    const healthy = (result.ai === "ready" || result.ai === "connected") && dbOk;
    const target = healthy ? S.READY : S.DEGRADED;
    if (m.state !== target) {
      m.transition(target, healthy ? {} : { detail: result.ai === "ready" || result.ai === "connected" ? "La base de datos no se pudo verificar." : aiText[1] });
    }
    return m.snapshot();
  }

  /** Parada segura (Fase 14). Nunca borra volúmenes ni datos. */
  async shutdown({ stopServices } = {}) {
    const m = this.machine;
    if (this._running) await withTimeout(this._running, 5000);
    if (m.state === S.STOPPED || m.state === S.STOPPING) return { stopped: false };
    const shouldStop = stopServices ?? this.getConfig().services.onExit === "stop";
    m.transition(S.STOPPING);
    let stopped = false;
    if (shouldStop && this.managed && this.startedByApp) {
      const res = await withTimeout(this.docker.stop({ timeoutSec: 30 }), 75_000, { ok: false, error: "TIMEOUT" });
      stopped = res.ok;
      if (!res.ok) this.logger.warn("No se pudieron detener los servicios", { error: res.error });
      else this.startedByApp = false;
    }
    m.transition(S.STOPPED);
    return { stopped };
  }
}

module.exports = { Lifecycle, COMPOSE_PORT };
