"use strict";
// Máquina de estados del ciclo de vida del escritorio (Fase 3).
// Pura: sin Electron ni E/S, para poder probarla entera.

const { EventEmitter } = require("node:events");

const STATES = Object.freeze({
  INITIALIZING: "INITIALIZING",
  CHECKING_DEPENDENCIES: "CHECKING_DEPENDENCIES",
  DOCKER_STARTING: "DOCKER_STARTING",
  SERVICES_STARTING: "SERVICES_STARTING",
  HEALTH_CHECKS: "HEALTH_CHECKS",
  READY: "READY",
  DEGRADED: "DEGRADED",
  ERROR: "ERROR",
  STOPPING: "STOPPING",
  STOPPED: "STOPPED",
});

const S = STATES;

// Transiciones permitidas. ERROR y STOPPING son alcanzables desde cualquier estado activo.
const TRANSITIONS = Object.freeze({
  [S.INITIALIZING]: [S.CHECKING_DEPENDENCIES],
  [S.CHECKING_DEPENDENCIES]: [S.DOCKER_STARTING, S.SERVICES_STARTING, S.HEALTH_CHECKS],
  [S.DOCKER_STARTING]: [S.SERVICES_STARTING, S.HEALTH_CHECKS],
  [S.SERVICES_STARTING]: [S.HEALTH_CHECKS],
  [S.HEALTH_CHECKS]: [S.READY, S.DEGRADED],
  [S.READY]: [S.DEGRADED, S.SERVICES_STARTING, S.HEALTH_CHECKS],
  [S.DEGRADED]: [S.READY, S.SERVICES_STARTING, S.HEALTH_CHECKS],
  [S.ERROR]: [S.INITIALIZING],
  [S.STOPPING]: [S.STOPPED],
  [S.STOPPED]: [S.INITIALIZING],
});

const ALWAYS_REACHABLE = new Set([S.ERROR, S.STOPPING]);

const MESSAGES = Object.freeze({
  [S.INITIALIZING]: "Iniciando NEXARO AI…",
  [S.CHECKING_DEPENDENCIES]: "Comprobando Windows, Docker, Ollama y puertos…",
  [S.DOCKER_STARTING]: "Arrancando Docker Desktop…",
  [S.SERVICES_STARTING]: "Arrancando los servicios de NEXARO…",
  [S.HEALTH_CHECKS]: "Comprobando que los servicios responden…",
  [S.READY]: "NEXARO AI está listo.",
  [S.DEGRADED]: "NEXARO funciona con limitaciones.",
  [S.ERROR]: "No se pudo arrancar NEXARO AI.",
  [S.STOPPING]: "Deteniendo los servicios…",
  [S.STOPPED]: "Servicios detenidos.",
});

class InvalidTransitionError extends Error {
  constructor(from, to) {
    super(`Transición no válida: ${from} → ${to}`);
    this.name = "InvalidTransitionError";
    this.from = from;
    this.to = to;
  }
}

function canTransition(from, to) {
  if (!(to in TRANSITIONS) || !(from in TRANSITIONS)) return false;
  if (ALWAYS_REACHABLE.has(to)) {
    // Desde ERROR se puede salir (STOPPING) pero no volver a ERROR; parado no admite ninguno.
    return ![S.STOPPING, S.STOPPED].includes(from) && from !== to;
  }
  return TRANSITIONS[from].includes(to);
}

class StateMachine extends EventEmitter {
  constructor({ now = () => Date.now() } = {}) {
    super();
    this._now = now;
    this._snapshot = {
      state: S.INITIALIZING,
      message: MESSAGES[S.INITIALIZING],
      detail: null,
      errorCode: null,
      checks: {},
      since: now(),
    };
    this.history = [S.INITIALIZING];
  }

  get state() {
    return this._snapshot.state;
  }

  /** Copia inmutable para enviar al renderer. */
  snapshot() {
    return structuredClone(this._snapshot);
  }

  transition(to, { message, detail = null, errorCode = null } = {}) {
    const from = this._snapshot.state;
    if (!canTransition(from, to)) throw new InvalidTransitionError(from, to);
    const checks = to === S.INITIALIZING ? {} : this._snapshot.checks;
    this._snapshot = {
      state: to,
      message: message ?? MESSAGES[to],
      detail,
      errorCode: to === S.ERROR ? errorCode ?? "UNKNOWN" : null,
      checks,
      since: this._now(),
    };
    this.history.push(to);
    this.emit("change", this.snapshot(), from);
    return this.snapshot();
  }

  /** Actualiza el resultado de una comprobación sin cambiar de estado. */
  setCheck(name, status, message = "") {
    if (!["pending", "ok", "warn", "fail", "skip"].includes(status)) {
      throw new TypeError(`Estado de comprobación no válido: ${status}`);
    }
    this._snapshot = {
      ...this._snapshot,
      checks: { ...this._snapshot.checks, [name]: { status, message } },
    };
    this.emit("change", this.snapshot(), this._snapshot.state);
  }

  isActive() {
    return ![S.ERROR, S.STOPPING, S.STOPPED].includes(this.state);
  }
}

module.exports = { STATES, TRANSITIONS, MESSAGES, StateMachine, InvalidTransitionError, canTransition };
