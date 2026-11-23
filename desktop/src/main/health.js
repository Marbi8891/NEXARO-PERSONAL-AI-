"use strict";
// Sondas HTTP con timeout y esperas con backoff exponencial y límite (Fase 4).

const http = require("node:http");

/**
 * GET con timeout. Solo http a 127.0.0.1/localhost: las sondas nunca salen de la máquina.
 * Resuelve siempre: {ok, status, body, error}.
 */
function httpGet(url, { timeoutMs = 3000, maxBytes = 1024 * 1024 } = {}) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return Promise.resolve({ ok: false, status: 0, body: "", error: "URL_INVALID" });
  }
  if (parsed.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(parsed.hostname)) {
    return Promise.resolve({ ok: false, status: 0, body: "", error: "URL_NOT_LOCAL" });
  }
  return new Promise((resolve) => {
    const req = http.get(parsed, { timeout: timeoutMs, headers: { accept: "application/json" } }, (res) => {
      const chunks = [];
      let size = 0;
      res.on("data", (chunk) => {
        size += chunk.length;
        if (size > maxBytes) {
          req.destroy(new Error("RESPONSE_TOO_LARGE"));
          return;
        }
        chunks.push(chunk);
      });
      res.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf8");
        resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, body, error: null });
      });
      res.on("error", (error) => resolve({ ok: false, status: res.statusCode ?? 0, body: "", error: error.message }));
    });
    req.on("timeout", () => req.destroy(new Error("TIMEOUT")));
    req.on("error", (error) => resolve({ ok: false, status: 0, body: "", error: error.code || error.message }));
  });
}

function parseJson(body) {
  try {
    return JSON.parse(body);
  } catch {
    return null;
  }
}

/** Retardo del intento n (0, 1, 2...): base·2^n con tope. */
function backoffDelay(attempt, { baseMs = 1000, maxMs = 10_000 } = {}) {
  return Math.min(maxMs, baseMs * 2 ** Math.max(0, attempt));
}

const realSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Repite `probe` hasta que devuelva un valor verdadero o se agote `timeoutMs`.
 * `probe` recibe el número de intento. Resuelve {ok, value, attempts, elapsedMs}.
 */
async function waitFor(
  probe,
  { timeoutMs = 60_000, baseMs = 1000, maxMs = 10_000, sleep = realSleep, now = () => Date.now(), signal } = {},
) {
  const start = now();
  let attempt = 0;
  let last;
  for (;;) {
    if (signal?.aborted) return { ok: false, value: last, attempts: attempt, elapsedMs: now() - start, aborted: true };
    last = await probe(attempt);
    attempt += 1;
    if (last) return { ok: true, value: last, attempts: attempt, elapsedMs: now() - start };
    const elapsed = now() - start;
    if (elapsed >= timeoutMs) return { ok: false, value: last, attempts: attempt, elapsedMs: elapsed };
    await sleep(Math.min(backoffDelay(attempt - 1, { baseMs, maxMs }), Math.max(0, timeoutMs - elapsed)));
  }
}

/** Estado del backend de NEXARO a partir de sus dos endpoints de salud. */
async function probeBackend(baseUrl, { get = httpGet } = {}) {
  const live = await get(`${baseUrl}/api/health/live`, { timeoutMs: 3000 });
  if (!live.ok) return { live: false, ai: "unknown", detail: live.error || `HTTP ${live.status}` };
  // /api/health puede tardar: sondea a Ollama desde el backend.
  const health = await get(`${baseUrl}/api/health`, { timeoutMs: 15_000 });
  if (health.ok) {
    const body = parseJson(health.body) || {};
    return { live: true, ai: body.model === "ready" ? "ready" : "connected", detail: null };
  }
  const body = parseJson(health.body) || {};
  // 503 con detalle genérico del backend: "Servicio de IA no disponible" o "Modelo de IA no disponible".
  const detail = typeof body.detail === "string" ? body.detail : health.error || `HTTP ${health.status}`;
  const ai = /modelo/i.test(detail) ? "model_missing" : "unreachable";
  return { live: true, ai, detail };
}

module.exports = { httpGet, parseJson, backoffDelay, waitFor, probeBackend };
