"use strict";
// Detección de conflictos de puertos (Fase 8). Solo comprueba 127.0.0.1, que es donde publica NEXARO.

const net = require("node:net");

/** true si el puerto está libre en `host` (intenta escuchar y cierra enseguida). */
function isPortFree(port, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen({ port, host, exclusive: true }, () => {
      server.close(() => resolve(true));
    });
  });
}

function validPort(port) {
  return Number.isInteger(port) && port >= 1 && port <= 65535;
}

/**
 * Clasifica un puerto: "free", "nexaro" (lo ocupa un NEXARO que responde) o "conflict".
 * `isNexaro` es una sonda inyectable (p. ej. GET /api/health/live).
 */
async function classifyPort(port, { isNexaro, isFree = isPortFree } = {}) {
  if (!validPort(port)) return "invalid";
  if (await isFree(port)) return "free";
  if (isNexaro && (await isNexaro(port))) return "nexaro";
  return "conflict";
}

module.exports = { isPortFree, classifyPort, validPort };
