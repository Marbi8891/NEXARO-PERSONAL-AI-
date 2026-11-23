"use strict";
// Proceso principal de Electron: une configuración, logs, gestores, máquina de estados y ventana.
//
// Modos (Fase 15):
// - Producción (app empaquetada): gestiona Docker Compose y Ollama; sin DevTools.
// - Desarrollo (`npm run dev` o `--dev`): igual, con DevTools y logs de depuración en consola.
// - Conectar (desarrollo): NEXARO_DESKTOP_BACKEND_URL=http://127.0.0.1:8001 usa un backend ya
//   arrancado (p. ej. `make run`) sin tocar Docker.

const path = require("node:path");
const { app, BrowserWindow, Notification, ipcMain, shell, dialog, Menu } = require("electron");

const { ConfigManager } = require("./config");
const { Logger } = require("./logger");
const { appDirs, composeProjectDir, overrideFile } = require("./paths");
const { StateMachine, STATES } = require("./states");
const { DockerManager } = require("./docker");
const { OllamaManager } = require("./ollama");
const { Lifecycle } = require("./lifecycle");
const { HealthMonitor } = require("./monitor");
const { describeSystem } = require("./system");
const { registerIpc, EVENTS } = require("./ipc");
const { webPreferences, makeNavigationPolicy, hardenWindow } = require("./security");
const { isLocalHttpUrl } = require("./config");

const S = STATES;
const APP_ID = "ai.nexaro.desktop";
const RENDERER_DIR = path.join(__dirname, "..", "renderer");
const isDev = !app.isPackaged || process.argv.includes("--dev");

function attachUrlFromEnv() {
  const raw = process.env.NEXARO_DESKTOP_BACKEND_URL;
  if (!raw || app.isPackaged) return null; // solo en desarrollo
  const normalized = raw.replace(/\/$/, "");
  return isLocalHttpUrl(`${normalized}/`) ? normalized : null;
}

// Instancia única: un segundo doble clic enfoca la ventana existente.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  main();
}

function main() {
  app.setAppUserModelId(APP_ID);
  let dirs;
  let logger;
  let config;
  let machine;
  let lifecycle;
  let monitor;
  let win = null;
  let showingApp = false;
  let quitting = false;
  let degradedNotified = false;

  const send = (snapshot) => {
    if (win && !win.isDestroyed()) win.webContents.send(EVENTS[0], snapshot);
  };

  function showStartupPage() {
    showingApp = false;
    return win.loadFile(path.join(RENDERER_DIR, "startup.html"));
  }

  function showApp() {
    if (!win || win.isDestroyed()) return;
    showingApp = true;
    win.loadURL(`${lifecycle.backendUrl()}/#/dashboard`).catch((error) => {
      logger.error("No se pudo cargar el frontend", { error });
      showStartupPage();
    });
  }

  function notify(title, body) {
    if (Notification.isSupported()) new Notification({ title, body }).show();
  }

  function onStateChange(snapshot, from) {
    send(snapshot);
    if (snapshot.state === from) return; // solo cambió una comprobación
    logger.info(`Estado ${from} → ${snapshot.state}`, { message: snapshot.message, errorCode: snapshot.errorCode });
    if (snapshot.state === S.READY) {
      degradedNotified = false;
      if (!showingApp) showApp();
      monitor.start();
    } else if (snapshot.state === S.DEGRADED) {
      monitor.start();
      if (showingApp && !degradedNotified) {
        degradedNotified = true;
        notify("NEXARO funciona con limitaciones", snapshot.detail ?? snapshot.message);
      }
    } else if (snapshot.state === S.ERROR && !quitting) {
      monitor.stop();
      if (showingApp) showStartupPage();
      if (win && !win.isVisible()) notify(snapshot.message, "Abre NEXARO AI para ver qué hacer.");
    }
  }

  function createWindow() {
    const policy = makeNavigationPolicy({ backendUrl: lifecycle.backendUrl(), rendererDir: RENDERER_DIR });
    win = new BrowserWindow({
      width: 1280,
      height: 820,
      minWidth: 900,
      minHeight: 600,
      title: "NEXARO AI",
      icon: path.join(__dirname, "..", "..", "build", "icon.png"),
      backgroundColor: "#0a1424",
      show: false,
      autoHideMenuBar: true,
      webPreferences: { ...webPreferences(path.join(__dirname, "..", "preload", "preload.js")), devTools: isDev },
    });
    hardenWindow(win, { policy, shell, logger });
    win.once("ready-to-show", () => {
      if (!config.get().window.startMinimized) win.show();
    });
    win.on("closed", () => {
      win = null;
    });
    // Hito 2: "Minimizar a la bandeja" (window.closeBehavior = "tray"). Por ahora cerrar = salir.
    return { policy, ready: showStartupPage() };
  }

  async function quitSafely() {
    if (quitting) return;
    quitting = true;
    monitor?.stop();
    try {
      const stopping = config.get().services.onExit === "stop" && lifecycle.startedByApp;
      if (stopping && win && !win.isDestroyed()) showStartupPage();
      await lifecycle.shutdown();
    } catch (error) {
      logger.error("Error al detener", { error });
    }
    logger.info("Salida de NEXARO AI");
    app.exit(0);
  }

  app.on("second-instance", () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
  });

  app.on("before-quit", (event) => {
    if (!quitting) {
      event.preventDefault();
      quitSafely();
    }
  });
  app.on("window-all-closed", () => quitSafely());

  app.whenReady().then(async () => {
    if (!isDev) Menu.setApplicationMenu(null);
    dirs = appDirs(app.getPath("userData"));
    logger = new Logger({ dir: dirs.logs, level: isDev ? "debug" : "info", mirror: isDev });
    config = new ConfigManager(dirs.configFile);
    config.load();
    if (config.warnings.length) logger.warn("Configuración corregida", { warnings: config.warnings });
    config.save(); // crea el archivo con los valores por defecto la primera vez
    logger.info("Inicio de NEXARO AI", { version: app.getVersion(), packaged: app.isPackaged, dev: isDev, platform: process.platform });

    const getConfig = () => config.get();
    const layout = { isPackaged: app.isPackaged, resourcesPath: process.resourcesPath, appPath: app.getAppPath() };
    const docker = new DockerManager({
      projectDir: composeProjectDir({ ...layout, configured: getConfig().services.composeProjectDir }),
      overrideFile: overrideFile(layout),
      getConfig,
      logger,
    });
    const ollama = new OllamaManager({ getConfig, logger });
    machine = new StateMachine();
    lifecycle = new Lifecycle({ machine, docker, ollama, getConfig, logger, systemInfo: describeSystem, attachUrl: attachUrlFromEnv() });
    monitor = new HealthMonitor({ lifecycle });
    machine.on("change", onStateChange);

    const { policy, ready } = createWindow();
    registerIpc({
      ipcMain,
      logger,
      isAllowedSender: (url) => policy.isDesktopPage(url),
      handlers: {
        "desktop:get-state": () => ({ ...machine.snapshot(), version: app.getVersion() }),
        "desktop:retry": () => {
          lifecycle.start();
          return true;
        },
        "desktop:open-logs": () => shell.openPath(dirs.logs).then((err) => err === ""),
        "desktop:open-app": () => {
          if ([S.READY, S.DEGRADED].includes(machine.state)) showApp();
          return true;
        },
      },
    });

    await ready;
    lifecycle.start();
  }).catch((error) => {
    dialog.showErrorBox("NEXARO AI", `No se pudo iniciar la aplicación: ${error.message}`);
    app.exit(1);
  });
}
