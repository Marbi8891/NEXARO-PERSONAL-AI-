"use strict";
// Ejecución de procesos externos desde el proceso principal.
//
// Reglas (Fase 10): nunca `shell: true`, argumentos siempre como lista (las rutas con espacios de
// Windows no se interpretan), timeout obligatorio, sin ventanas de consola (`windowsHide`) y solo
// binarios de una lista blanca por nombre. El renderer no tiene acceso a este módulo.

const { execFile, spawn } = require("node:child_process");
const path = require("node:path");

// Nombres de ejecutable permitidos (sin extensión, en minúsculas).
const ALLOWED_BINARIES = new Set(["docker", "docker desktop", "ollama", "ollama app"]);

const MAX_OUTPUT_BYTES = 4 * 1024 * 1024;

function binaryName(file) {
  // path.win32 separa tanto "\\" como "/": funciona igual con rutas de Windows y POSIX.
  return path.win32.basename(String(file)).toLowerCase().replace(/\.exe$/, "");
}

function assertAllowed(file, args) {
  if (!ALLOWED_BINARIES.has(binaryName(file))) {
    throw new Error(`Ejecutable no permitido: ${path.win32.basename(String(file))}`);
  }
  if (!Array.isArray(args) || !args.every((a) => typeof a === "string")) {
    throw new TypeError("Los argumentos deben ser una lista de cadenas");
  }
}

/**
 * Ejecuta un binario permitido y resuelve siempre (no lanza por código de salida distinto de 0).
 * @returns {Promise<{ok: boolean, code: number|null, stdout: string, stderr: string, timedOut: boolean, error?: string}>}
 */
function run(file, args, { timeoutMs = 30_000, env, cwd } = {}) {
  assertAllowed(file, args);
  return new Promise((resolve) => {
    execFile(
      file,
      args,
      {
        timeout: timeoutMs,
        killSignal: "SIGTERM",
        windowsHide: true,
        shell: false,
        maxBuffer: MAX_OUTPUT_BYTES,
        env: env ?? process.env,
        cwd,
        encoding: "utf8",
      },
      (error, stdout, stderr) => {
        if (!error) {
          resolve({ ok: true, code: 0, stdout, stderr, timedOut: false });
          return;
        }
        const timedOut = Boolean(error.killed) && error.signal === "SIGTERM";
        resolve({
          ok: false,
          code: typeof error.code === "number" ? error.code : null,
          stdout: stdout ?? "",
          stderr: stderr ?? "",
          timedOut,
          // ENOENT = el ejecutable no existe.
          error: typeof error.code === "string" ? error.code : error.message,
        });
      },
    );
  });
}

/** Lanza una aplicación de escritorio (Docker Desktop, Ollama) desacoplada del proceso. */
function launchDetached(file, args = []) {
  assertAllowed(file, args);
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(file, args, { detached: true, stdio: "ignore", windowsHide: true, shell: false });
    } catch (error) {
      resolve({ ok: false, error: error.message });
      return;
    }
    child.once("error", (error) => resolve({ ok: false, error: error.code || error.message }));
    child.once("spawn", () => {
      child.unref();
      resolve({ ok: true });
    });
  });
}

module.exports = { run, launchDetached, assertAllowed, ALLOWED_BINARIES };
