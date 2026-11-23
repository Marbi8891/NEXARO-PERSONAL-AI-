"use strict";
// Dobles de prueba compartidos.

const { DEFAULTS, normalize } = require("../src/main/config");

function makeConfig(overrides = {}) {
  const cfg = structuredClone(DEFAULTS);
  for (const [k, v] of Object.entries(overrides)) {
    const keys = k.split(".");
    let cur = cfg;
    for (const key of keys.slice(0, -1)) cur = cur[key];
    cur[keys.at(-1)] = v;
  }
  return normalize(cfg).config;
}

function silentLogger() {
  const entries = [];
  const log = (level) => (msg, data) => entries.push({ level, msg, data });
  return { entries, debug: log("debug"), info: log("info"), warn: log("warn"), error: log("error") };
}

/** Ejecutor de comandos falso: responde según una función y registra las llamadas. */
function fakeRunner(respond) {
  const calls = [];
  const run = async (file, args, opts = {}) => {
    calls.push({ file, args, opts });
    const res = await respond(file, args, opts);
    return { ok: true, code: 0, stdout: "", stderr: "", timedOut: false, ...res };
  };
  return { run, calls };
}

/** Espera instantánea: waitFor sin dormir, con un número de intentos limitado. */
function instantWait(maxAttempts = 5) {
  return async (probe) => {
    for (let i = 0; i < maxAttempts; i += 1) {
      const value = await probe(i);
      if (value) return { ok: true, value, attempts: i + 1, elapsedMs: 0 };
    }
    return { ok: false, value: null, attempts: maxAttempts, elapsedMs: 0 };
  };
}

module.exports = { makeConfig, silentLogger, fakeRunner, instantWait };
