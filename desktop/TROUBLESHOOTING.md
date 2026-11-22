# Solución de problemas

Los registros están en `%APPDATA%\NEXARO AI\logs\desktop.log` (botón **Abrir registros** en la
pantalla de arranque). No contienen contraseñas, tokens ni claves: se redactan antes de escribirse.

## Errores de arranque

| Código / mensaje | Causa probable | Qué hacer |
|---|---|---|
| `DOCKER_NOT_INSTALLED` — Docker Desktop no está instalado | No se encuentra `docker.exe` en el PATH ni en `C:\Program Files\Docker\Docker\resources\bin`. | Instala Docker Desktop. Si está en otra ruta, pon `docker.executablePath` en `desktop-config.json`. |
| `COMPOSE_TOO_OLD` | Compose < 2.20. | Actualiza Docker Desktop. |
| `DOCKER_NOT_RUNNING` | Motor parado y arranque automático desactivado, o no se pudo abrir Docker Desktop. | Abre Docker Desktop y pulsa Reintentar. Revisa `docker.desktopPath`. |
| `DOCKER_START_TIMEOUT` | Docker Desktop no terminó de arrancar en 180 s. | Comprueba WSL 2 (`wsl --status`) y la virtualización. Abre Docker Desktop a mano y mira su mensaje de error. Sube `docker.startTimeoutSec` en equipos lentos. |
| `PORT_CONFLICT` | Otro programa usa `127.0.0.1:8001`. | `netstat -ano | findstr :8001` muestra el PID; ciérralo desde el Administrador de tareas. |
| `NETWORK_FAILED` | No se pudo crear la red `nexaro_desktop`. | Reinicia Docker Desktop. |
| `SERVICES_FAILED` | `docker compose up` falló (sin Internet en la primera construcción, error de la imagen, healthcheck). | El detalle de la pantalla trae el final del error de Compose. Revisa la conexión y Reintentar. |
| `SERVICES_NOT_STARTED` | `services.autoStart` está en `false` y los contenedores están parados. | Pulsa Reintentar o cambia el ajuste. |
| `BACKEND_UNHEALTHY` | Los contenedores arrancaron pero `/api/health/live` no responde en 2 minutos. | Docker Desktop → Containers → `nexaro-backend` → Logs. |
| `BACKEND_RECOVERY_FAILED` | El backend cayó y 3 recuperaciones en 10 minutos no bastaron. | Revisa los logs del contenedor; Reintentar vuelve a empezar desde cero. |

## "NEXARO funciona con limitaciones" (DEGRADED)

| Mensaje | Qué hacer |
|---|---|
| Falta el modelo `X` | Abre Ollama y descarga el modelo, o cambia `ollama.defaultModel` a uno instalado (`ollama list`). |
| El backend no alcanza a Ollama | 1) ¿Ollama está abierto? (icono en la bandeja). 2) `http://127.0.0.1:11434/api/tags` debe responder en el navegador. 3) Si responde en el PC pero no desde Docker: el backend lo busca en `host.docker.internal:11434`. Prueba el modo incluido (`"ollama": {"mode": "bundled"}`) o, solo si sabes lo que haces, `OLLAMA_HOST=0.0.0.0` en las variables de entorno de Windows (expone Ollama a tu red local: limita el puerto 11434 en el firewall). |
| La base de datos no se pudo verificar | `docker exec nexaro-backend ls -l /data` debe mostrar `nexaro.db`. |

## Recuperar servicios a mano

Siempre desde la carpeta de instalación (`<instalación>\resources\nexaro`) o la raíz del repo, con
los mismos dos archivos que usa la app:

```powershell
$env:OLLAMA_NETWORK = "nexaro_desktop"   # la red que usa la app (sin esto Compose busca la del Mac)
docker compose -f compose.yaml -f ..\compose\compose.desktop.yaml ps
docker compose -f compose.yaml -f ..\compose\compose.desktop.yaml logs backend --tail 200
docker compose -f compose.yaml -f ..\compose\compose.desktop.yaml up -d --wait
```

**No ejecutes `docker compose down -v`**: borra el volumen con la base de datos.

## Configuración dañada

Si `desktop-config.json` no es JSON válido, la app lo guarda como `desktop-config.json.corrupt` y
arranca con los valores por defecto. Hay una copia del anterior en `desktop-config.json.bak`.

## La ventana no aparece

Solo puede haber una instancia: un segundo doble clic enfoca la existente. Si
`window.startMinimized` es `true`, la ventana empieza oculta (la bandeja llega en el hito 2:
pon el ajuste a `false` mientras tanto).
