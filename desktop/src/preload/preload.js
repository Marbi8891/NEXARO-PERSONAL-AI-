"use strict";
// Puente mínimo entre la pantalla de arranque y el proceso principal (contextIsolation + sandbox).
// Solo expone funciones fijas sin argumentos; el proceso principal vuelve a validar remitente y
// argumentos. El frontend web de NEXARO no usa este puente y el proceso principal lo rechaza.
// En sandbox el preload no puede hacer require de módulos locales: los nombres van aquí.

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nexaroDesktop", Object.freeze({
  getState: () => ipcRenderer.invoke("desktop:get-state"),
  retry: () => ipcRenderer.invoke("desktop:retry"),
  openLogs: () => ipcRenderer.invoke("desktop:open-logs"),
  openApp: () => ipcRenderer.invoke("desktop:open-app"),
  onState: (callback) => {
    if (typeof callback !== "function") return () => {};
    const listener = (_event, snapshot) => callback(snapshot);
    ipcRenderer.on("desktop:state", listener);
    return () => ipcRenderer.removeListener("desktop:state", listener);
  },
}));
