# Plan de implementación: NEXARO AI como aplicación de escritorio para Windows

Fecha de la auditoría: 2026-11-22. Base auditada: rama `claude/project-thread-17a30v` (PR #4, la
aplicación canónica que se está consolidando en `main`). `main` todavía solo contiene documentos de
diseño, así que el código real se tomó de esa rama.

Objetivo final: el usuario hace doble clic en "NEXARO AI", la aplicación arranca y vigila la
infraestructura que necesita, comprueba que los servicios de IA responden y abre el Command Center
en una ventana nativa, sin abrir terminales ni el navegador.

---

## 1. Auditoría del repositorio

### 1.1 Tecnologías

| Pieza | Lo que hay | Dónde |
|---|---|---|
| Frontend | HTML + CSS + ES Modules **sin paso de compilación** (ADR-0007). Router por hash (`#/dashboard`, `#/chat`...). PWA con service worker mínimo que nunca cachea `/api`. CSP estricta, sin scripts ni estilos en línea. | `frontend/` |
| Backend | Python 3.12, FastAPI 0.160 + Uvicorn, monolito modular (`apps/api` → `products/*` → `packages/*`). | `apps/api/nexaro_api`, `packages/`, `products/` |
| Quién sirve el frontend | **El propio backend** (`StaticFiles` montado en `/`). No hay servidor de frontend aparte ni puerto propio. | `apps/api/nexaro_api/main.py:189` |
| Base de datos | SQLite (WAL) en `/data/nexaro.db`, dentro del volumen Docker `nexaro-personal-ai_nexaro_data`. Migraciones versionadas aplicadas al arrancar. PostgreSQL solo validado a nivel de DDL. | `packages/nexaro_core/database` |
| IA | Ollama vía `ai_gateway` (proveedor `ollama`). Bedrock/SageMaker desactivados por defecto. | `packages/ai_gateway` |
| Agentes | Se ejecutan **dentro del proceso del backend** (`products/`). No existe un "Agent Runtime" separado. | ADR-0022 |
| Redis / colas / "NEXARO Core" como servicio | **No existen.** `nexaro_core` es un paquete Python dentro del backend, no un contenedor. | — |

### 1.2 Docker Compose (`compose.yaml`)

- Proyecto con nombre fijo `nexaro-personal-ai`, así el volumen de datos es siempre el mismo.
- Servicio `backend` (`container_name: nexaro-backend`): publica **`127.0.0.1:8001 → 8000`**,
  `read_only`, `cap_drop: ALL`, `no-new-privileges`, 1 GB de memoria, healthcheck contra
  `/api/health/live`. Monta `./frontend` en solo lectura.
- Servicio `ollama` solo con el perfil `ollama` (modo "incluido", ADR-0021); nunca publica puertos.
- El backend busca a Ollama como `http://ollama:11434` en una red externa `${OLLAMA_NETWORK}`
  (por defecto `ollama-local_default`, la del Ollama del Mac del propietario en `~/Docker/ollama-local`).
- Volúmenes: `nexaro_data` (base de datos) y `ollama_models` (modelos del modo incluido).
- No usa IPs de contenedor: solo nombres de servicio y alias. Bien para nosotros.

### 1.3 Endpoints relevantes para el escritorio

| Endpoint | Qué indica | Uso en escritorio |
|---|---|---|
| `GET /api/health/live` | El proceso del backend vive (no depende de Ollama). | "Backend arrancado" |
| `GET /api/health` | 200 si Ollama responde y el modelo configurado está instalado; 503 si no. Sin detalles que revelen el modelo. | "IA lista" / estado DEGRADED |
| `GET http://localhost:11434/api/tags` | Ollama nativo responde y lista modelos. | Gestor de Ollama |

No hay endpoint de salud de la base de datos. La base es SQLite **dentro** del backend: si
`/api/health/live` responde, el backend ya abrió la base y aplicó las migraciones (el arranque
aborta si fallan). Para dar un estado explícito, el escritorio hace una consulta de solo lectura con
`docker exec` (como ya hace `scripts/stack.sh smoke`). No hace falta tocar el backend.

### 1.4 Configuración y puertos

- Configuración por variables de entorno (`packages/nexaro_core/config/settings.py`, `.env.example`).
- `NEXARO_ENV=production` exige `COOKIE_SECURE=true` y orígenes https: **no sirve para un backend
  local en http**. El escritorio mantiene el modo por defecto del compose (desarrollo con docs
  cerrados), que es el que ya se usa en local.
- `ALLOWED_ORIGINS` = `http://127.0.0.1:8001,http://localhost:8001`. Electron carga exactamente
  `http://127.0.0.1:8001`, así que la validación de origen del backend sigue funcionando sin cambios.
- Puertos: 8001 (API + frontend, solo en 127.0.0.1) y 11434 (Ollama nativo). Base de datos sin puerto.

### 1.5 Scripts de arranque existentes

`Makefile` (`make up/down/model/smoke`) y `scripts/stack.sh` (preflight y smoke). Son **bash**: no
funcionan en Windows sin WSL/Git Bash. Su lógica (Compose ≥ 2.20, red, modo de Ollama, esperar a
salud, nunca `down -v`) se reimplementa en Node dentro del escritorio, sin modificar los scripts.

### 1.6 Compatibilidad con Windows

| Tema | Situación | Consecuencia |
|---|---|---|
| Backend | Corre en Linux dentro de Docker | Funciona igual con Docker Desktop (backend WSL2). |
| Scripts bash | No portables | El escritorio no los usa. |
| Red externa `ollama-local_default` | Específica del Mac del propietario | En Windows el escritorio usa su propia red `nexaro_desktop` y la crea si falta. |
| Ollama | En Windows lo normal es **Ollama para Windows** (nativo, usa la GPU), en `localhost:11434` | El backend en Docker lo alcanza por `host.docker.internal:11434` (override de compose, ver §2.3). |
| Rutas con espacios (`C:\Program Files\...`) | Compose las admite si se pasan como argumentos, no por shell | El escritorio nunca usa `shell: true`. |
| Base SQLite | En un volumen Docker con nombre | Rápida y sin problemas de bloqueos. Un bind mount a `%APPDATA%` sería lento y arriesgado para SQLite bajo WSL2 (ver §4). |
| Primer administrador | `docker exec -it ... bootstrap_admin` (pide la contraseña con `getpass`) | Requiere terminal: el asistente de primera ejecución (Fase 9) lo hará por IPC aprobado. |

### 1.7 Requisitos actuales de instalación

Docker Desktop con Compose ≥ 2.20, Ollama (externo o perfil incluido), `make`, bash y `curl` para
los scripts, y una terminal para crear el administrador. Con el escritorio quedarán solo **Docker
Desktop** y **Ollama** como dependencias externas.

### 1.8 Compatibilidad con Electron

Sin bloqueos serios:

- El frontend no usa `window.open` ni enlaces `_blank`; no hay URLs externas en `frontend/js`.
- `X-Frame-Options: DENY` y `frame-ancestors 'none'` no afectan: Electron carga la página como
  documento principal, no en un iframe.
- El service worker funciona en `http://127.0.0.1` (origen considerado seguro).
- Cookies `SameSite`/no `Secure` en http local: funcionan igual que en Chrome.
- La CSP del backend no permite scripts en línea: el preload de Electron no inyecta nada en la página.

Lo que **no** tiene el frontend y pide el enunciado (Agents, Prompt Library, Tasks, Memory,
Knowledge Base, Workspaces...) son pantallas del producto, no del escritorio. Prompt Library y
Agentes los están construyendo otras sesiones (PR #10, #11). El escritorio muestra lo que el
frontend tenga en cada momento y no duplica pantallas.

---

## 2. Arquitectura propuesta

### 2.1 Elección de tecnología

**Electron.** No hay motivo para otra opción: el frontend ya es web y lo sirve el backend, Electron
gestiona bien procesos hijos, bandeja, notificaciones e instalador NSIS (`electron-builder`).
Tauri obligaría a Rust y a WebView2 con menos control del ciclo de vida.

Alternativa considerada y **no elegida ahora**: empaquetar el backend como ejecutable nativo
(PyInstaller) y prescindir de Docker. Quitaría el requisito de Docker Desktop (WSL2, virtualización,
licencia en empresas grandes), pero cambia el modelo de despliegue del proyecto y el enunciado pide
Docker Compose. Queda como opción futura (ver §6, Fase 9 bis).

### 2.2 Componentes

```
NEXARO AI.exe (Electron)
│
├── Proceso principal (src/main)
│   ├── main.js            ciclo de vida de Electron, instancia única, ventana
│   ├── lifecycle.js       máquina de estados del arranque + orquestador de arranque/parada
│   ├── docker.js          Docker Manager: CLI, Docker Desktop, Compose (up/stop/ps), red
│   ├── ollama.js          Ollama Manager: ejecutable, /api/tags, arranque, modelos
│   ├── health.js          sondas HTTP con timeout, espera con backoff exponencial
│   ├── monitor.js         Health Monitor: vigilancia tras READY y recuperación con límites
│   ├── ports.js           conflicto de puertos (¿libre?, ¿es ya NEXARO?)
│   ├── system.js          versión de Windows (build 10240+ = Win10, 22000+ = Win11), RAM, disco
│   ├── config.js          Configuration Manager: JSON validado en %APPDATA%
│   ├── logger.js          logs a archivo con rotación y redacción de secretos
│   ├── paths.js           carpetas de datos de la aplicación
│   ├── process.js         ejecución de comandos SIN shell, con timeout y lista blanca de binarios
│   ├── ipc.js             IPC con lista blanca, validación de argumentos y del remitente
│   └── security.js        endurecimiento de ventanas, navegación y permisos
├── Preload (src/preload/preload.js)   puente mínimo con contextBridge
└── Renderer
    ├── src/renderer/startup.html      pantalla de arranque / error (local, CSP propia)
    └── http://127.0.0.1:8001          el frontend existente de NEXARO, sin cambios
```

### 2.3 Cómo arranca el stack sin tocar `compose.yaml`

El escritorio llama a Compose con un archivo adicional, `desktop/compose/compose.desktop.yaml`:

```
docker compose --project-directory <raíz> -f <raíz>/compose.yaml -f desktop/compose/compose.desktop.yaml up -d --wait
```

El override solo cambia `OLLAMA_BASE_URL` del backend a
`${NEXARO_DESKTOP_OLLAMA_URL:-http://host.docker.internal:11434}` y añade
`host.docker.internal:host-gateway`. Las variables se pasan en el entorno del proceso (no se
escribe ningún `.env`):

| Modo de Ollama (configurable) | Variables que pone el escritorio |
|---|---|
| `native` (por defecto en Windows) | `OLLAMA_NETWORK=nexaro_desktop`, `NEXARO_DESKTOP_OLLAMA_URL=http://host.docker.internal:11434` |
| `bundled` (Ollama en Docker, perfil) | `COMPOSE_PROFILES=ollama`, `OLLAMA_NETWORK=nexaro_desktop`, `NEXARO_DESKTOP_OLLAMA_URL=http://ollama:11434` |

La red `nexaro_desktop` se crea con `docker network create` si no existe (igual que hace
`stack.sh preflight` en el modo incluido). El nombre de proyecto fijo hace que el escritorio use
**el mismo volumen de datos** que `make up`.

### 2.4 Máquina de estados del arranque

```
INITIALIZING ─► CHECKING_DEPENDENCIES ─┬─► DOCKER_STARTING ─┐
                                       └────────────────────┴─► SERVICES_STARTING ─► HEALTH_CHECKS ─┬─► READY
                                                                                                    └─► DEGRADED
READY ⇄ DEGRADED (monitor)      cualquiera ─► ERROR      ERROR ─► INITIALIZING (Reintentar)
cualquiera ─► STOPPING ─► STOPPED
```

Las transiciones no válidas lanzan excepción (se prueban). Cada estado lleva un mensaje en español,
una lista de comprobaciones con su resultado y, en ERROR, un código estable (`DOCKER_NOT_INSTALLED`,
`DOCKER_NOT_RUNNING`, `COMPOSE_TOO_OLD`, `PORT_CONFLICT`, `SERVICES_FAILED`, `BACKEND_UNHEALTHY`...)
con el texto de qué hacer.

READY = backend vivo + Ollama responde + modelo instalado. DEGRADED = el backend funciona pero Ollama
no responde o falta el modelo: se abre la app igualmente (login, documentos, finanzas funcionan) y se
avisa de que el chat no estará disponible.

### 2.5 Recuperación y límites

- Esperas con backoff exponencial (1 s, 2 s, 4 s... tope 10 s) y un timeout total por paso.
- Docker Desktop: hasta 180 s para que el motor responda.
- `compose up --wait`: hasta 300 s (la primera vez construye la imagen).
- Monitor tras READY: sondea cada 15 s. Tras 3 fallos seguidos de `/api/health/live` hace
  `compose up -d backend` (como mucho 3 recuperaciones en 10 minutos). Si se agotan, pasa a ERROR y
  deja de reintentar: nunca reinicia en bucle.

### 2.6 Seguridad (Fase 10, aplicada ya en la Fase 1)

- `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, `webSecurity: true`,
  sin `webviewTag`.
- Navegación permitida solo a `http://127.0.0.1:<puerto>` y a la pantalla de arranque local.
  `window.open` denegado; enlaces `https:` externos se abren en el navegador del sistema.
- Permisos del navegador denegados salvo notificaciones y escritura en portapapeles.
- IPC: lista cerrada de canales; cada uno valida remitente (solo páginas propias) y argumentos.
  **No existe ningún canal que ejecute comandos arbitrarios**; Docker y Ollama se invocan desde el
  proceso principal con argumentos fijos y `execFile` sin shell. El renderer nunca puede lanzar
  PowerShell.
- Logs y diagnósticos pasan por un redactor de secretos (tokens, contraseñas, claves, cookies).
- DevTools solo en modo desarrollo.

### 2.7 Datos de la aplicación (Fase 12)

`app.getPath('userData')` → en Windows `%APPDATA%\NEXARO AI\`:

```
%APPDATA%\NEXARO AI\
├── config\desktop-config.json   configuración del escritorio (validada; copia .bak al guardar)
├── logs\desktop.log (+ .1 ... .5) logs rotados
├── backups\                     copias de configuración y exportaciones de la base
└── diagnostics\                 informes exportados (sin secretos)
```

La base de datos **se queda en el volumen Docker** (decisión deliberada, ver riesgos). Las copias de
seguridad de la base se exportan a `backups\` desde la app (Fase 12). Los modelos los guarda Ollama
en su sitio (`%USERPROFILE%\.ollama`) o en el volumen `ollama_models`; nunca dentro del instalador.

---

## 3. Cambios necesarios

**Nuevo (todo dentro de `desktop/`):** proyecto Electron, override de Compose, pantalla de arranque,
tests, documentación e instalador.

**Sin cambios:** backend, migraciones, frontend, `compose.yaml`, `Makefile`, scripts. Mínimo
imprescindible y nada que choque con el trabajo de las otras sesiones.

**Cambios futuros que sí podrían tocar el resto (cada uno en su propio PR y con aviso):**

1. Endpoint de salud de base de datos en el backend (opcional; hoy se cubre con `docker exec`).
2. Publicar la imagen del backend en un registro (GHCR) para no construirla en el PC del usuario.
   Requiere decisión del propietario.
3. Puerto del backend configurable en `compose.yaml` (`${NEXARO_PORT:-8001}`) para resolver
   conflictos de puerto sin editar archivos.

---

## 4. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| `host.docker.internal` no alcanza a Ollama nativo si este escucha solo en 127.0.0.1 | Chat no disponible (DEGRADED) | En Docker Desktop para Windows el reenvío a localhost del host funciona normalmente; **se debe verificar en Windows real**. Alternativa: modo `bundled` o `OLLAMA_HOST=0.0.0.0` (expone Ollama a la LAN: solo con cortafuegos). Documentado en TROUBLESHOOTING. |
| Docker Desktop no instalado / WSL2 o virtualización desactivados | La app no puede arrancar servicios | Pantalla de error clara con el enlace de descarga. No se instala nada con permisos de administrador en silencio. |
| Primera construcción de la imagen lenta (pip, varios minutos) y necesita Internet | Primer arranque largo | Estado SERVICES_STARTING con mensaje explícito; timeout amplio. Futuro: imagen publicada. |
| Puerto 8001 ocupado por otro programa | No arranca | Detección: si el puerto responde `/api/health/live` es NEXARO (se adopta); si no, error PORT_CONFLICT con el puerto. |
| Choque con un `make run` / `make up` del desarrollador | Dos backends | Mismo proyecto Compose = mismo stack (no se duplica). En modo desarrollo del escritorio se puede conectar a un backend ya arrancado (`NEXARO_DESKTOP_BACKEND_URL`) sin gestionar Docker. |
| Base en volumen Docker y no en `%APPDATA%` | Un "reset" de Docker Desktop borra los datos | Copias de seguridad exportables (Fase 12) y aviso en la guía. Nunca se ejecuta `down -v`. |
| Licencia de Docker Desktop en empresas > 250 empleados | Coste para algunos usuarios | Documentado. Opción futura de backend nativo. |
| Instalador sin firma de código | SmartScreen avisa "editor desconocido" | Documentado; firmar requiere certificado del propietario. |
| No se puede probar Windows en la nube | Fallos solo visibles en Windows | Lógica de Windows aislada y probada con dobles; lista explícita de lo no probado. |
| Otras sesiones cambian el backend a la vez | Conflictos | Todo vive en `desktop/`; el PR se apila sobre el de la app canónica. |

---

## 5. Consideraciones específicas de Windows

- Detección de Docker Desktop: `docker.exe` en `PATH` o en `C:\Program Files\Docker\Docker\resources\bin`;
  ejecutable de la app en `C:\Program Files\Docker\Docker\Docker Desktop.exe` (ruta configurable).
  Arrancarlo no requiere permisos de administrador.
- Detección de Ollama: `%LOCALAPPDATA%\Programs\Ollama\ollama app.exe` / `ollama.exe` o `PATH`
  (ruta configurable). Se arranca la app de bandeja de Ollama, que levanta el servidor.
- Versión: `os.release()` → `10.0.<build>`; build ≥ 22000 es Windows 11, ≥ 10240 Windows 10.
- Instancia única (`requestSingleInstanceLock`): un segundo doble clic enfoca la ventana existente.
- `app.setAppUserModelId` para que notificaciones y anclado a la barra de tareas funcionen.
- Procesos hijos con `windowsHide: true` (no aparecen ventanas de consola).
- Inicio con Windows: `app.setLoginItemSettings` (Fase 8), sin tocar el registro a mano.
- Instalador NSIS por usuario (sin admin), accesos directos en Escritorio y Menú Inicio,
  desinstalador que **no** borra `%APPDATA%\NEXARO AI` ni los volúmenes Docker salvo que el usuario
  lo marque.

---

## 6. Fases de implementación

| Hito | Contenido | Fases del enunciado |
|---|---|---|
| **1 (este PR)** | Proyecto Electron en `desktop/`; máquina de estados; detección de Windows, Docker, Compose, Ollama y puertos; arranque de Docker Desktop y Ollama si están instalados; `compose up --wait` con override; sondas de salud (backend, IA, base de datos); ventana nativa segura con pantalla de arranque/error y botón Reintentar; carga del frontend existente; monitor con recuperación limitada; parada segura (`compose stop`, nunca `-v`); configuración y logs en `%APPDATA%`; IPC con lista blanca; modo desarrollo/producción; configuración de `electron-builder` (NSIS); tests. | 1, 2, 3, 4 (núcleo), 10, 14, 15 (base) |
| 2 | Bandeja del sistema (abrir, arrancar/parar/reiniciar, estado, logs, salir), comportamiento al cerrar ventana, notificaciones nativas. | 6, 7 |
| 3 | Página de ajustes del escritorio (arranque con Windows, minimizado, servicios, rutas de Ollama/Docker, puertos y conflictos). | 8 |
| 4 | Panel de Ollama: modelos instalados, modelo por defecto, instalación **con confirmación** y progreso, requisitos de memoria. | 5 |
| 5 | Asistente de primera ejecución, incluido crear el primer administrador sin terminal. | 9 |
| 6 | Diagnóstico exportable sin secretos; copia y restauración de configuración y base. | 12, 13 |
| 7 | Instalador probado en Windows 10 y 11, guía de actualización, firma (si hay certificado). | 11, 17 |
| 9 bis (opcional) | Backend nativo sin Docker. | — |

Cada hito: tests propios, documentación actualizada y PR separado.

### Primer hito: definición de "hecho"

1. `npm test` en `desktop/` pasa (pruebas reales ejecutadas, no simuladas en el informe).
2. En Linux (nube) se comprueba con Electron real en modo "conectar a backend existente" que la
   ventana carga el frontend y que la seguridad del renderer está activa.
3. Lo que solo puede comprobarse en Windows queda listado en `desktop/docs/TESTING.md`.
