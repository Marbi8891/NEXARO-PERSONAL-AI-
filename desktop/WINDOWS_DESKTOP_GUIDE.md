# NEXARO AI para Windows: guía de desarrollo

Para instalar y usar la app: [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md). Problemas:
[TROUBLESHOOTING.md](TROUBLESHOOTING.md). Diseño: [DESKTOP_ARCHITECTURE.md](DESKTOP_ARCHITECTURE.md)
y [DESKTOP_IMPLEMENTATION_PLAN.md](DESKTOP_IMPLEMENTATION_PLAN.md).

## Requisitos de desarrollo

- Node.js 20 o posterior (CI usa 22).
- Docker Desktop (o Docker Engine en Linux) con Compose ≥ 2.20.
- Opcional: Ollama.

## Ejecutar en desarrollo

```bash
cd desktop
npm install
npm start            # gestiona Docker Compose desde la raíz del repo, con DevTools
```

Para trabajar en el frontend con recarga, arranca el backend aparte y conecta la app a él (no toca
Docker):

```bash
make run                                                  # en la raíz: uvicorn --reload en 127.0.0.1:8001
NEXARO_DESKTOP_BACKEND_URL=http://127.0.0.1:8001 npm start  # en desktop/
# PowerShell: $env:NEXARO_DESKTOP_BACKEND_URL="http://127.0.0.1:8001"; npm start
```

El frontend no tiene paso de compilación: un cambio en `frontend/` se ve con *Ctrl+R* en la ventana.
Desarrollo y producción no chocan: usan el mismo proyecto de Compose y el mismo volumen, y si el
puerto 8001 ya lo ocupa un NEXARO la app lo reutiliza en vez de arrancar otro.

## Tests

```bash
cd desktop
npm test
```

Usan el runner de Node (`node:test`), sin Electron ni Docker: los gestores reciben dobles, y las
partes de red y archivos se prueban con servidores y carpetas temporales reales. Qué cubre cada
archivo y qué queda sin probar en Windows: [docs/TESTING.md](docs/TESTING.md).

## Generar el instalador

En Windows:

```powershell
cd desktop
npm ci
npm run dist:win     # → desktop\dist\NEXARO AI Setup <versión>.exe
```

`electron-builder` con NSIS: instalación por usuario sin administrador, carpeta elegible, accesos
directos en Escritorio y menú Inicio, desinstalador que conserva `%APPDATA%\NEXARO AI` y los
volúmenes Docker. El instalador copia en `resources\nexaro` lo necesario para construir la imagen
del backend (`compose.yaml`, `Dockerfile`, `requirements`, `packages`, `products`, `apps/api`,
`frontend`) y en `resources\compose` el override del escritorio. No incluye modelos.

En Linux, `electron-builder --win` necesita Wine para el desinstalador y el icono del `.exe`; por eso
el instalador se genera en el workflow `.github/workflows/desktop.yml` (runner `windows-latest`),
que lo publica como artefacto `nexaro-ai-setup` en cada PR que toca `desktop/`.

### Firma de código

Sin certificado, SmartScreen avisa al instalar. Para firmar, define `CSC_LINK` y
`CSC_KEY_PASSWORD` (secretos del repositorio, nunca en el código) y quita
`CSC_IDENTITY_AUTO_DISCOVERY=false` del workflow.

## Ollama

- Modo `native` (por defecto): Ollama para Windows en `http://127.0.0.1:11434`. El escritorio lo
  abre si está instalado y parado. El backend (en Docker) lo alcanza por `host.docker.internal`.
- Modo `bundled`: Ollama en un contenedor (perfil `ollama` de `compose.yaml`). Sin GPU en Windows
  salvo configuración adicional de Docker; más lento.
- El modelo por defecto (`ollama.defaultModel`) se pasa al backend como `OLLAMA_MODEL`.
- Nunca se descargan modelos automáticamente.

## Docker

- Siempre `docker compose --project-directory <raíz> -f compose.yaml -f compose/compose.desktop.yaml`.
- Red propia `nexaro_desktop` (se crea si falta). Sin IPs de contenedor: nombres de servicio y
  `host.docker.internal`.
- Al salir, `compose stop` (si así está configurado y los arrancó la app). Nunca `down` ni `-v`.

## Estructura

```
desktop/
├── package.json             Electron 45.2.3, electron-builder 26.18.1, configuración NSIS
├── compose/compose.desktop.yaml
├── build/icon.png           icono (de frontend/icons/icon-512.png)
├── src/main/                proceso principal (ver DESKTOP_ARCHITECTURE.md)
├── src/preload/preload.js
├── src/renderer/            pantalla de arranque/error
├── test/                    node:test
└── docs/TESTING.md
```
