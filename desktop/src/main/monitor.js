"use strict";
// Health Monitor (Fase 4): vigila el backend tras READY/DEGRADED y recupera fallos con límites.
//
// - Sondea cada `intervalMs`.
// - Tras `failThreshold` fallos seguidos de /api/health/live recrea el backend con Compose.
// - Como mucho `maxRecoveries` recuperaciones por `windowMs`; agotadas, pasa a ERROR y se detiene.
//   Nunca reinicia en bucle.

const { STATES } = require("./states");
const { backoffDelay } = require("./health");

const S = STATES;

class HealthMonitor {
  constructor({ lifecycle, intervalMs = 15_000, failThreshold = 3, maxRecoveries = 3, windowMs = 10 * 60_000, now = () => Date.now(), timers = { setInterval, clearInterval } }) {
    this.lifecycle = lifecycle;
    this.machine = lifecycle.machine;
    this.intervalMs = intervalMs;
    this.failThreshold = failThreshold;
    this.maxRecoveries = maxRecoveries;
    this.windowMs = windowMs;
    this._now = now;
    this._timers = timers;
    this.failures = 0;
    this.recoveries = [];
    this._handle = null;
    this._busy = false;
    this._nextRecoveryAt = 0;
  }

  start() {
    if (this._handle) return;
    this._handle = this._timers.setInterval(() => {
      this.tick().catch((error) => this.lifecycle.logger.error("Fallo del monitor", { error }));
    }, this.intervalMs);
    this._handle?.unref?.();
  }

  stop() {
    if (this._handle) this._timers.clearInterval(this._handle);
    this._handle = null;
  }

  /** Un ciclo de vigilancia. Público para poder probarlo sin temporizadores. */
  async tick() {
    if (this._busy || ![S.READY, S.DEGRADED].includes(this.machine.state)) return "skipped";
    this._busy = true;
    try {
      const result = await this.lifecycle._probe(this.lifecycle.backendUrl());
      if (result.live) {
        this.failures = 0;
        this.lifecycle.applyProbe(result);
        return "healthy";
      }
      this.failures += 1;
      this.lifecycle.logger.warn("El backend no responde", { failures: this.failures, detail: result.detail });
      if (this.failures < this.failThreshold) return "failing";
      // Backoff exponencial entre recuperaciones: intervalo, 2×, 4×… (tope 5 minutos).
      if (this._now() < this._nextRecoveryAt) return "waiting";
      return await this._recover();
    } finally {
      this._busy = false;
    }
  }

  async _recover() {
    const m = this.machine;
    const lc = this.lifecycle;
    const now = this._now();
    this.recoveries = this.recoveries.filter((t) => now - t < this.windowMs);
    if (!lc.managed || this.recoveries.length >= this.maxRecoveries) {
      this.stop();
      lc._fail("BACKEND_RECOVERY_FAILED", lc.managed ? `${this.maxRecoveries} intentos de recuperación en ${Math.round(this.windowMs / 60_000)} minutos.` : "El backend externo no responde.");
      return "gave_up";
    }
    this.recoveries.push(now);
    const attempt = this.recoveries.length;
    this._nextRecoveryAt = now + backoffDelay(attempt, { baseMs: this.intervalMs, maxMs: 5 * 60_000 });
    m.transition(S.SERVICES_STARTING, { message: `Recuperando el backend (intento ${attempt} de ${this.maxRecoveries})…` });
    const res = await lc.docker.restartService("backend");
    if (!res.ok) {
      lc.logger.error("La recuperación del backend falló", { error: res.error });
    }
    m.transition(S.HEALTH_CHECKS);
    const probe = await lc._probe(lc.backendUrl());
    if (probe.live) {
      this.failures = 0;
      this._nextRecoveryAt = 0;
      lc.applyProbe(probe);
      return "recovered";
    }
    // Sigue caído: se vuelve a DEGRADED y el siguiente ciclo decidirá (con el contador de intentos).
    m.transition(S.DEGRADED, { message: "El backend no responde; se reintentará.", detail: res.error });
    return "still_down";
  }
}

module.exports = { HealthMonitor };
