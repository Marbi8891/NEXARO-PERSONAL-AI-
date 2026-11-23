"use strict";
// Endurecimiento de Electron (Fase 10). Las funciones de decisión son puras y se prueban sin Electron.

const { pathToFileURL } = require("node:url");

const ALLOWED_PERMISSIONS = new Set(["notifications", "clipboard-sanitized-write"]);

function webPreferences(preloadPath) {
  return {
    preload: preloadPath,
    contextIsolation: true,
    nodeIntegration: false,
    nodeIntegrationInWorker: false,
    nodeIntegrationInSubFrames: false,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
    webviewTag: false,
    spellcheck: false,
    navigateOnDragDrop: false,
    safeDialogs: true,
  };
}

/** Páginas que pueden mostrarse en la ventana: el backend local y las pantallas propias. */
function makeNavigationPolicy({ backendUrl, rendererDir }) {
  const backendOrigin = new URL(backendUrl).origin;
  const rendererPrefix = pathToFileURL(rendererDir).href.replace(/\/?$/, "/");
  return {
    backendOrigin,
    rendererPrefix,
    isAllowed(url) {
      let parsed;
      try {
        parsed = new URL(url);
      } catch {
        return false;
      }
      if (parsed.origin === backendOrigin && parsed.protocol === "http:") return true;
      // file:// solo dentro de la carpeta del renderer propio (sin "..": URL ya normaliza).
      return parsed.protocol === "file:" && parsed.href.startsWith(rendererPrefix);
    },
    /** ¿Es una página propia con acceso a los controles del escritorio (no el frontend web)? */
    isDesktopPage(url) {
      try {
        return new URL(url).protocol === "file:" && url.startsWith(rendererPrefix);
      } catch {
        return false;
      }
    },
  };
}

/** Enlaces que se pueden abrir en el navegador del sistema: solo https a hosts que no son locales. */
function isSafeExternalUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname) && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

function isAllowedPermission(permission) {
  return ALLOWED_PERMISSIONS.has(permission);
}

/** Aplica la política a una ventana y su sesión. `shell` = shell de Electron (openExternal). */
function hardenWindow(win, { policy, shell, logger }) {
  const contents = win.webContents;
  const blockNavigation = (event, url) => {
    if (policy.isAllowed(url)) return;
    event.preventDefault();
    if (isSafeExternalUrl(url)) shell.openExternal(url);
    else logger?.warn("Navegación bloqueada", { url: String(url).slice(0, 200) });
  };
  contents.on("will-navigate", blockNavigation);
  contents.on("will-redirect", blockNavigation);
  contents.on("will-frame-navigate", (event) => {
    if (!event.isMainFrame && !policy.isAllowed(event.url)) event.preventDefault();
  });
  contents.on("will-attach-webview", (event) => event.preventDefault());
  contents.setWindowOpenHandler(({ url }) => {
    if (isSafeExternalUrl(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  const ses = contents.session;
  ses.setPermissionRequestHandler((_wc, permission, callback) => callback(isAllowedPermission(permission)));
  ses.setPermissionCheckHandler((_wc, permission) => isAllowedPermission(permission));
}

module.exports = { webPreferences, makeNavigationPolicy, isSafeExternalUrl, isAllowedPermission, hardenWindow };
