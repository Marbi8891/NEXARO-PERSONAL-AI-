# Arquitectura de NEXARO AI para escritorio

Resumen técnico de lo implementado en el hito 1. El porqué de cada decisión está en
[DESKTOP_IMPLEMENTATION_PLAN.md](DESKTOP_IMPLEMENTATION_PLAN.md).

```
NEXARO AI.exe ─ Electron (proceso principal, Node)
│
├─ main.js ............ ciclo de vida de Electron, instancia única, ventana, cableado
├─ lifecycle.js ....... Desktop Lifecycle Manager: arranque y parada sobre la máquina de estados
├─ states.js .......... máquina de estados (10 estados, transiciones validadas)
├─ monitor.js ......... Health Monitor: vigilancia cada 15 s y recuperación limitada
├─ docker.js .......... Docker Manager: CLI, Docker Desktop, Compose, red, base de datos
├─ ollama.js .......... Ollama Manager: ejecutable, /api/tags, arranque, modelos (sin descargas)
├─ health.js .......... sondas HTTP locales, backoff exponencial, espera con timeout
├─ ports.js ........... conflicto de puertos
├─ system.js .......... Windows 10/11, RAM, disco
├─ config.js .......... Configuration Manager (JSON validado, .bak, copia y restauración)
├─ logger.js .......... logs JSON con rotación y redacción de secretos
├─ paths.js ........... carpetas en %APPDATA%\NEXARO AI y rutas de Compose
├─ process.js ......... ejecución sin shell y con lista blanca de ejecutables
├─ ipc.js ............. canales IPC permitidos y validación de remitente/argumentos
├─ security.js ........ preferencias seguras, navegación, ventanas emergentes y permisos
├─ errors.js .......... códigos de error y texto para el usuario
│
├─ preload/preload.js . puente `window.nexaroDesktop` (4 funciones fijas)
├─ renderer/startup.* . pantalla de arranque, error y "funciona con limitaciones"
└─ http://127.0.0.1:8001  frontend existente de NEXARO (servido por el backend, sin cambios)
```

## Flujo de arranque

1. `main.js` crea la configuración y los logs, construye los gestores y abre la ventana con la
   pantalla de arranque.
2. `Lifecycle.start()`:
   - `CHECKING_DEPENDENCIES`: Windows, CLI de Docker, Compose ≥ 2.20, motor de Docker.
   - `DOCKER_STARTING` (solo si el motor no responde): abre Docker Desktop y espera hasta
     `docker.startTimeoutSec` con backoff.
   - Ollama nativo: si no responde y está instalado, lo abre; si falta el modelo, avisa (no descarga).
   - Puerto 8001: libre / ya es NEXARO / conflicto.
   - `SERVICES_STARTING`: crea la red `nexaro_desktop` si falta y ejecuta
     `docker compose -f compose.yaml -f compose/compose.desktop.yaml up -d --wait`.
   - `HEALTH_CHECKS`: `/api/health/live`, base de datos (consulta de solo lectura dentro del backend),
     agentes (integrados en el backend) y `/api/health` (Ollama y modelo).
   - `READY` → la ventana carga el frontend. `DEGRADED` → la pantalla explica qué falta y ofrece
     "Abrir NEXARO". `ERROR` → código, explicación, "Reintentar" y "Abrir registros".
3. `HealthMonitor` vigila mientras la app está abierta: READY ⇄ DEGRADED, y tras 3 fallos seguidos
   del backend lo recrea (`compose up -d --no-deps backend`), como mucho 3 veces cada 10 minutos y con
   espera creciente entre intentos. Después pasa a ERROR y no insiste más.

## Parada

Al cerrar: monitor detenido → `STOPPING` → `docker compose stop` (solo si `services.onExit` es
`stop` **y** los servicios los arrancó esta sesión) → `STOPPED` → salida. Tiempo máximo 75 s. Nunca
`down`, `rm`, `-v` ni `--volumes`: lo impide `assertSafeComposeArgs` (y hay tests).

## Modos

| Modo | Cómo | Qué hace |
|---|---|---|
| Producción | app instalada | Gestiona Docker/Ollama; sin menú ni DevTools; logs nivel info. |
| Desarrollo | `npm start` / `npm run dev` | Igual, con DevTools, logs debug en consola, y Compose desde la raíz del repo. |
| Conectar | `NEXARO_DESKTOP_BACKEND_URL=http://127.0.0.1:8001 npm start` | Usa un backend ya arrancado (`make run`) sin tocar Docker. Ignorado en la app instalada. |

Si en el arranque el puerto 8001 ya lo ocupa un NEXARO que no es el contenedor de Compose, la app lo
adopta en modo conectar en lugar de fallar.

## Seguridad

- Ventana: `contextIsolation`, `sandbox`, sin `nodeIntegration`, sin `webview`, `webSecurity`.
- Navegación: solo `http://127.0.0.1:8001` y `file://` dentro de `src/renderer`. Enlaces `https`
  externos se abren en el navegador del sistema; el resto se bloquea y se registra.
- Permisos web: solo notificaciones y escritura en portapapeles.
- IPC: 4 canales sin argumentos (`get-state`, `retry`, `open-logs`, `open-app`); el remitente
  tiene que ser la pantalla de arranque. El frontend web recibe el puente pero el proceso principal
  rechaza sus llamadas (verificado con Electron real).
- Procesos: solo `docker`, `Docker Desktop`, `ollama` y `ollama app`, con `execFile` sin shell.

## Datos

| Qué | Dónde |
|---|---|
| Configuración | `%APPDATA%\NEXARO AI\config\desktop-config.json` (+ `.bak`) |
| Logs | `%APPDATA%\NEXARO AI\logs\desktop.log` (5 × 2 MB) |
| Copias de configuración | `%APPDATA%\NEXARO AI\backups\` |
| Diagnósticos (hito 6) | `%APPDATA%\NEXARO AI\diagnostics\` |
| Base de datos | volumen Docker `nexaro-personal-ai_nexaro_data` |
| Modelos | Ollama (`%USERPROFILE%\.ollama`) o volumen `ollama_models` |
| Código del backend (para construir la imagen) | `<instalación>\resources\nexaro` |

## Configuración (`desktop-config.json`)

| Clave | Por defecto | Notas |
|---|---|---|
| `services.autoStart` | `true` | Arrancar los contenedores al abrir. |
| `services.onExit` | `stop` | `stop` o `keep`. |
| `services.upTimeoutSec` | `600` | La primera vez se construye la imagen. |
| `services.composeProjectDir` | vacío | Otra carpeta con `compose.yaml`. |
| `docker.autoStartDesktop` | `true` | |
| `docker.executablePath` / `docker.desktopPath` | vacío | Rutas absolutas si no están en el sitio estándar. |
| `docker.startTimeoutSec` | `180` | |
| `ollama.mode` | `native` | `native` (Ollama para Windows) o `bundled` (contenedor). |
| `ollama.endpoint` | `http://127.0.0.1:11434` | Solo http local. |
| `ollama.executablePath` | vacío | |
| `ollama.autoStart` | `true` | |
| `ollama.defaultModel` | `qwen2.5:3b` | Se pasa al backend como `OLLAMA_MODEL`. |
| `window.closeBehavior` | `exit` | `tray` llegará con la bandeja (hito 2). |
| `backend.port` | `8001` | Informativo: `compose.yaml` fija 8001 (ver plan §3). |

Un valor no válido se sustituye por el predeterminado y se registra un aviso; un archivo dañado se
guarda como `.corrupt` y la app arranca con los valores por defecto.
