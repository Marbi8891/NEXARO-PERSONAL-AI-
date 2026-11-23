"use strict";
// Información del sistema: versión de Windows, memoria y disco (Fases 3, 9 y 13).

const os = require("node:os");
const fs = require("node:fs");

/**
 * Interpreta la versión de Windows a partir de os.release() ("10.0.22631").
 * Windows 11 comparte "10.0" con Windows 10: se distingue por el build (>= 22000).
 */
function parseWindowsRelease(release) {
  const match = /^(\d+)\.(\d+)\.(\d+)/.exec(String(release));
  if (!match) return { name: "Windows (versión desconocida)", build: null, supported: false };
  const [major, minor, build] = match.slice(1).map(Number);
  if (major === 10 && minor === 0 && build >= 22000) return { name: "Windows 11", build, supported: true };
  if (major === 10 && minor === 0 && build >= 10240) return { name: "Windows 10", build, supported: true };
  return { name: `Windows ${major}.${minor}`, build, supported: false };
}

function describeSystem({ platform = process.platform, release = os.release(), totalmem = os.totalmem(), arch = os.arch() } = {}) {
  const ramGb = Math.round((totalmem / 1024 ** 3) * 10) / 10;
  if (platform === "win32") {
    return { platform, arch, ramGb, ...parseWindowsRelease(release), isWindows: true };
  }
  // macOS/Linux: solo para desarrollo; el producto objetivo es Windows 10/11.
  return { platform, arch, ramGb, name: `${platform} ${release}`, build: null, supported: true, isWindows: false };
}

/** Espacio libre en GB de la unidad que contiene `dir` (null si no se puede saber). */
function freeDiskGb(dir) {
  try {
    const stats = fs.statfsSync(dir);
    return Math.round(((stats.bavail * stats.bsize) / 1024 ** 3) * 10) / 10;
  } catch {
    return null;
  }
}

module.exports = { parseWindowsRelease, describeSystem, freeDiskGb };
