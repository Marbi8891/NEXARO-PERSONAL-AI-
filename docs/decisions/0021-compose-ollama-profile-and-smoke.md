# ADR-0021: Ollama opcional por perfil de Compose, modelo comprobado y prueba de humo

- **Estado:** Aceptada. Modo externo verificado en el MacBook; el modo incluido está pendiente de probarse en Linux con la imagen real de Ollama
- **Fecha:** 2026-11-18

## Contexto

Ollama vive en otro proyecto de Compose (`~/Docker/ollama-local`, contenedor `ollama`, red
`ollama-local_default`, volumen `ollama_data` con los modelos ya descargados). En una máquina nueva
(p. ej. Linux en VirtualBox) ese proyecto no existe. `/api/health` solo decía si Ollama respondía,
no si el modelo configurado estaba instalado, así que el chat podía fallar con la salud en verde. La
descarga del modelo era manual y no había una prueba de extremo a extremo del stack.

Al probar una instalación desde cero apareció además un fallo: `/data` no existía en la imagen,
Docker creaba el punto de montaje como `root` y el backend (uid 10001) no podía crear la base.

## Opciones

- A. Meter Ollama en `compose.yaml` siempre. Duplica el Ollama del Mac (otro contenedor, otros ~2 GB
  de modelos) o obliga a migrar sus datos.
- B. Ollama en `compose.yaml` bajo un perfil `ollama`, desactivado por defecto; sin el perfil se usa el
  externo. La misma URL (`http://ollama:11434`) en los dos modos.
- C. Dejar Ollama fuera y documentar cómo levantarlo a mano.

## Decisión

B.

- **Modo externo (por defecto):** el de siempre. Compose no puede depender de un servicio de otro
  proyecto, así que el backend arranca igual y `/api/health` da 503 hasta que Ollama y el modelo estén.
- **Modo incluido:** `COMPOSE_PROFILES=ollama` y `OLLAMA_NETWORK=nexaro_ollama` en `.env`. Servicio
  `ollama` sin puertos publicados, alias de red `ollama`, volumen `ollama_models`, healthcheck
  `ollama list` (consulta la API del servidor), `cap_drop: ALL`, `no-new-privileges`, límites y
  rotación de logs. El backend espera a que esté sano con `depends_on: {condition: service_healthy,
  required: false}`: sin el perfil, esa dependencia no existe (comprobado con Compose 5.7).
- **Red:** su nombre es configurable (`OLLAMA_NETWORK`, por defecto `ollama-local_default`).
  `scripts/stack.sh preflight` crea la red del modo incluido si falta, pero nunca la del externo (la crea
  el proyecto `ollama-local`). También se niega a arrancar si los dos Ollama compartirían red, para que
  el alias `ollama` no se resuelva a dos contenedores.
- **Modelo:** `/api/health` devuelve 503 con «Modelo de IA no disponible» si falta (sin revelar el
  nombre, ADR-0019) y `"model": "ready"` si está. Sale de la misma llamada a `/api/tags` que ya
  comprobaba la salud, así que no hay ninguna petición extra a Ollama.
- **Descarga:** `scripts/ollama_model.py` (solo biblioteca estándar) con `check`, `ensure` y
  `generate`. Se ejecuta dentro del backend (misma red y misma `OLLAMA_BASE_URL`) sin copiarse en la
  imagen. `ensure` no descarga nada si el modelo ya está, corta si la descarga se queda sin progreso y
  reintenta con espera exponencial si Ollama no responde.
- **Prueba de humo:** `make smoke` comprueba que los servicios están en marcha y sanos, que el backend
  ve a Ollama y el modelo, que hay una generación real y que todo persiste tras recrear los
  contenedores. Los datos se leen en solo lectura; el único archivo que escribe es uno propio en
  `/data`, que borra al terminar.
- **Nombre de proyecto fijo** (`name: nexaro-personal-ai`): el volumen de datos no depende del nombre
  de la carpeta. Hoy las dos copias del repositorio ya resuelven a ese nombre, así que no cambia nada.
- **`/data` con propietario 10001 en la imagen:** Docker lo copia solo al crear un volumen vacío. Un
  volumen con datos no cambia.

## Razón y trade-offs

No duplica nada en el Mac, permite instalar desde cero en Linux con un solo `make up` y mantiene a
Ollama fuera de cualquier interfaz publicada.

En contra:
- Hace falta Compose >= 2.20 por `required: false`. Con uno más antiguo el error es explícito, no
  silencioso, y el preflight lo comprueba antes.
- La imagen de Ollama no está fijada (`OLLAMA_IMAGE`, por defecto `latest`, igual que en
  `ollama-local`). Fijarla requiere conocer la versión que funciona: VERIFY tras la primera descarga.
- `cap_drop: ALL` en Ollama: comprobado con la imagen real (arranque y API), sin descargar un modelo.
- El smoke reinicia el Ollama externo solo con `SMOKE_RESTART_OLLAMA=1`, porque es otro proyecto.

## Consecuencias

- `make up` = preflight + `docker compose up -d --build --wait`; `make model`, `make model-check` y
  `make smoke` nuevos.
- Verificado en un Docker 29 / Compose 5.7 aislado, con el backend construido desde este Dockerfile
  (cambiando solo la imagen base) y un Ollama simulado con la misma API. Se probaron:
  - los modos externo e incluido;
  - la protección contra dos «ollama» en la misma red y el error si falta la red externa;
  - la descarga idempotente;
  - el reinicio con datos reales (1 usuario, 1 conversación, 2 mensajes);
  - la persistencia de los modelos tras `down` y `up`;
  - el fallo del smoke con Ollama parado.

  **No verificado:** imagen real de Ollama, `qwen2.5:3b` real, Docker Desktop en macOS, Linux en
  VirtualBox.

## Verificación real (2026-11-18, MacBook Pro, Docker 29.9.2, Compose 5.6.1)

Modo externo, con `~/Docker/ollama-local` y `qwen2.5:3b` real. `make up`: backend reconstruido y
*healthy* en 7 s. `make model-check`: modelo instalado. `make smoke`: SMOKE OK (primera generación en
21,8 s, con la carga del modelo en CPU). `SMOKE_RESTART_OLLAMA=1 make smoke`: SMOKE OK (1,4 s), con
Ollama reiniciado. La base real se conservó en los dos casos (users=1, conversations=14, messages=64,
documents=1, antes y después).

Imagen real `ollama/ollama:latest` con `--cap-drop ALL` y `no-new-privileges`: arranca y atiende la API
(`ollama list` y `GET /api/tags` con 200). Docker Desktop tiene 7,8 GiB; `OLLAMA_MEM_LIMIT=6g` cabe.

Pendiente (VERIFY): el modo incluido completo (`make up` + `make model` + `make smoke`) en Linux con
VirtualBox.
