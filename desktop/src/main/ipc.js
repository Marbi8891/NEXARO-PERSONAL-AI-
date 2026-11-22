"use strict";
// IPC con lista blanca (Fase 10). Cada canal declara sus argumentos; el remitente debe ser una
// página propia del escritorio (no el frontend web ni otra página). No hay ningún canal que ejecute
// comandos, abra rutas arbitrarias o lea archivos: solo acciones fijas del proceso principal.

const CHANNELS = Object.freeze({
  "desktop:get-state": { args: [] },
  "desktop:retry": { args: [] },
  "desktop:open-logs": { args: [] },
  "desktop:open-app": { args: [] },
});

// Eventos que el proceso principal puede enviar al renderer.
const EVENTS = Object.freeze(["desktop:state"]);

class IpcRejectedError extends Error {
  constructor(reason) {
    super(`IPC rechazado: ${reason}`);
    this.name = "IpcRejectedError";
  }
}

function validateArgs(channel, args) {
  const spec = CHANNELS[channel];
  if (!spec) return false;
  if (args.length !== spec.args.length) return false;
  return spec.args.every((check, i) => check(args[i]));
}

/**
 * Registra los manejadores. `handlers` debe cubrir exactamente los canales de la lista blanca.
 * @param {{handle: Function}} ipcMain
 * @param {(url: string) => boolean} isAllowedSender
 */
function registerIpc({ ipcMain, handlers, isAllowedSender, logger }) {
  const names = Object.keys(handlers).sort();
  const expected = Object.keys(CHANNELS).sort();
  if (JSON.stringify(names) !== JSON.stringify(expected)) {
    throw new Error("Los manejadores IPC no coinciden con la lista blanca");
  }
  for (const channel of expected) {
    ipcMain.handle(channel, async (event, ...args) => {
      const url = event?.senderFrame?.url ?? "";
      if (!isAllowedSender(url)) {
        logger?.warn("IPC rechazado por remitente", { channel, url: url.slice(0, 200) });
        throw new IpcRejectedError("remitente no autorizado");
      }
      if (!validateArgs(channel, args)) {
        logger?.warn("IPC rechazado por argumentos", { channel });
        throw new IpcRejectedError("argumentos no válidos");
      }
      return handlers[channel](...args);
    });
  }
}

module.exports = { CHANNELS, EVENTS, registerIpc, validateArgs, IpcRejectedError };
