# Pruebas del escritorio (hito 1)

## Automáticas: `npm test` (81 tests, `node:test`)

| Archivo | Cubre |
|---|---|
| `states.test.js` | Máquina de estados: camino feliz, los 10 estados, transiciones inválidas, ERROR/STOPPING desde cualquier estado activo, reintento, eventos. |
| `lifecycle.test.js` | Arranque y parada con dobles: Docker no instalado, Compose antiguo, Docker parado (se abre / desactivado / timeout), conflicto de puerto, NEXARO ya en marcha (adoptado o idempotente), fallo de Compose, backend sin respuesta, modelo ausente sin descarga, Ollama parado (se abre) o no instalado, modo bundled, base de datos no verificable, modo conectar, excepción inesperada, reintento, llamadas simultáneas, parada (solo lo arrancado, `keep`, desde ERROR). |
| `docker.test.js` | Detección del CLI (PATH, ruta estándar de Windows, ruta configurada), estado del motor, argumentos exactos de `compose up`, entorno por modo de Ollama sin IPs, `stop` sin borrado, bloqueo de `down`/`-v`/`rm`/`kill`, servicios en lista blanca, red, `compose ps`, consulta de base de datos en solo lectura, Docker Desktop. |
| `ollama-health.test.js` | Ollama contra un servidor HTTP real: en marcha, parado, respuesta ajena, modelos y RAM, rutas de Windows y arranque. Sondas: solo http local, timeout, `/api/health` real simulado (ready / modelo / sin IA), backoff y `waitFor`. |
| `config-logger.test.js` | Configuración en disco: valores por defecto, persistencia entre instancias, `.bak`, validación (claves desconocidas, endpoint remoto, modelo con caracteres peligrosos, puerto, rutas relativas), archivo dañado, copia y restauración, carpetas de datos. Logs: redacción de secretos y rotación. |
| `security.test.js` | IPC: lista blanca, remitentes rechazados (frontend web, web externa, archivo local ajeno), argumentos. Navegación, enlaces externos, preferencias de la ventana, permisos. Procesos: lista blanca, sin shell, ENOENT. Análisis estático: ningún `shell: true`, `exec`, `nodeIntegration: true` ni `innerHTML`. Preload con canales fijos. |
| `monitor-system-ports.test.js` | Monitor: READY ⇄ DEGRADED, recuperación tras 3 fallos, límite de 3 con backoff y ERROR final sin bucle, backend externo. Versiones de Windows 10/11/8.1. Puertos con sockets reales. |

El workflow `.github/workflows/desktop.yml` ejecuta estos tests en **Ubuntu y Windows** y genera
el instalador en Windows.

## Ejecutadas a mano en la nube (Linux, 2026-11-22)

Con Electron 45.2.3 real bajo Xvfb, controlado con Playwright:

1. **Modo conectar** contra el backend real (`uvicorn`, mismo código) y un Ollama simulado:
   pantalla de arranque → READY → la ventana carga `http://127.0.0.1:8001/#/login`.
   En la página del frontend: `require` y `process` no existen; `window.open` devuelve `null`;
   llamar a `nexaroDesktop.retry()` desde el frontend es **rechazado** por el proceso principal;
   navegar a `http://localhost:9/evil` se bloquea (sigue en 127.0.0.1:8001). Preferencias reales:
   `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`. Se crearon
   `config/desktop-config.json` y `logs/desktop.log`.
2. **DEGRADED**: sin Ollama, la pantalla muestra "NEXARO funciona con limitaciones" con el motivo
   y el botón "Abrir NEXARO", que carga el frontend.
3. **Modo gestionado con Docker real** (Docker 29.10, Compose 5.7.1): la app ejecutó
   `compose up --wait` con el override, el backend en contenedor alcanzó al Ollama simulado del host
   por `host.docker.internal` (estado READY, que exige IA y base de datos verificadas) en 7 s con la
   imagen ya construida. Al cerrar la app el contenedor quedó `Exited (0)` y el volumen
   `nexaro-personal-ai_nexaro_data` intacto.
4. **Recuperación**: con la app abierta se detuvo `nexaro-backend` desde fuera; el monitor lo
   detectó (3 fallos), lo recreó y la API volvió a responder en 48 s.

La imagen de esa prueba se construyó con una copia temporal del Dockerfile que solo añadía el
certificado del proxy del entorno de la nube (no está en el repositorio).

## Sin probar (requiere Windows real)

| Qué | Por qué no |
|---|---|
| Instalador NSIS: instalar, accesos directos, icono, desinstalar conservando datos | En Linux `electron-builder` necesita Wine; lo genera el workflow en `windows-latest`, pero nadie lo ha ejecutado aún. |
| Abrir Docker Desktop (`Docker Desktop.exe`) y esperar a su motor | No hay Docker Desktop en la nube. Probado solo con dobles. |
| Abrir Ollama para Windows (`ollama app.exe`) | Probado solo con dobles. |
| `host.docker.internal` → Ollama nativo escuchando solo en 127.0.0.1 con Docker Desktop (WSL 2) | En Linux se probó con Ollama simulado escuchando en 0.0.0.0. **Es el punto de mayor riesgo.** |
| Rutas con espacios (`C:\Program Files\...`) y `windowsHide` | Se pasan como argumentos sin shell; sin prueba real. |
| Detección de la versión de Windows 10/11 en una máquina real | Probado con cadenas de `os.release()`. |
| Notificaciones nativas, `AppUserModelId`, instancia única en Windows | Sin escritorio Windows. |
| Primera construcción de la imagen en un PC limpio (tiempo, Internet) | En la nube la imagen ya estaba construida. |
| Rendimiento con modelos reales | No se descargan modelos en la nube. |

Lista de comprobación manual para la primera prueba en Windows:

1. Instalar Docker Desktop y Ollama; descargar `qwen2.5:3b` en Ollama.
2. Descargar el artefacto `nexaro-ai-setup` del PR, instalar y abrir desde el Escritorio.
3. Esperar READY (la primera vez varios minutos) y comprobar que se ve el inicio de sesión.
4. Cerrar Docker Desktop y abrir NEXARO: debe abrir Docker Desktop solo y llegar a READY.
5. Cerrar Ollama: en ≤ 15 s la app debe avisar de "funciona con limitaciones".
6. Cerrar NEXARO: en Docker Desktop `nexaro-backend` debe quedar detenido y el volumen seguir ahí.
7. Ocupar el puerto 8001 con otro programa y abrir NEXARO: error PORT_CONFLICT.
8. Revisar `%APPDATA%\NEXARO AI\logs\desktop.log`.
