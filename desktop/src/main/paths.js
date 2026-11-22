"use strict";
// Carpetas de datos (Fase 12). En Windows `userData` es %APPDATA%\NEXARO AI. Nada se guarda en la
// carpeta de instalación. La base de datos vive en el volumen Docker `nexaro-personal-ai_nexaro_data`.

const fs = require("node:fs");
const path = require("node:path");

function appDirs(userData) {
  const dirs = {
    root: userData,
    config: path.join(userData, "config"),
    logs: path.join(userData, "logs"),
    backups: path.join(userData, "backups"),
    diagnostics: path.join(userData, "diagnostics"),
  };
  for (const dir of Object.values(dirs)) fs.mkdirSync(dir, { recursive: true });
  return { ...dirs, configFile: path.join(dirs.config, "desktop-config.json") };
}

/**
 * Carpeta del proyecto Compose.
 * - Empaquetada: <recursos>/nexaro (copiada por electron-builder, ver package.json "extraResources").
 * - Desarrollo: la raíz del repositorio (desktop/..).
 * - `configured` (ajuste services.composeProjectDir) tiene prioridad si existe compose.yaml allí.
 */
function composeProjectDir({ isPackaged, resourcesPath, appPath, configured, exists = fs.existsSync }) {
  if (configured && exists(path.join(configured, "compose.yaml"))) return configured;
  return isPackaged ? path.join(resourcesPath, "nexaro") : path.resolve(appPath, "..");
}

function overrideFile({ isPackaged, resourcesPath, appPath }) {
  return isPackaged
    ? path.join(resourcesPath, "compose", "compose.desktop.yaml")
    : path.join(appPath, "compose", "compose.desktop.yaml");
}

module.exports = { appDirs, composeProjectDir, overrideFile };
