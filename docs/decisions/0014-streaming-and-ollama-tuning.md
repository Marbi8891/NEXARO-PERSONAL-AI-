# ADR-0014: Inferencia con streaming real y parámetros de Ollama configurables

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
La auditoría (F19.1) encontró que cada respuesta se pedía a Ollama con `stream: false`: el usuario no veía
nada hasta que terminaba la generación, de modo que su «primer contenido» era el tiempo total. Además se
creaba un cliente HTTP nuevo por petición y por comprobación de salud, no se enviaban `keep_alive` ni
`num_ctx`, `num_predict` era siempre 2048 y el historial (12 mensajes) se reenviaba sin límite de tamaño.
El equipo de destino es un Mac con Intel i5 y Docker Desktop limitado a 8 CPU y ~7,75 GiB: la inferencia es
solo CPU, por lo que lo que más se nota es no esperar a la respuesta completa y no recargar el modelo.

## Opciones
- **Entrega:** SSE sobre `POST` con `fetch` + `ReadableStream` *(elegida)* frente a WebSocket (más estado y
  superficie sin necesidad: la comunicación es unidireccional) o `EventSource` (solo `GET`, no permite cuerpo
  ni cabeceras propias, y el mensaje viajaría en la URL).
- **Cancelación:** el cliente aborta la petición; al cerrarse la conexión el servidor cierra el flujo hacia
  Ollama, que detiene la generación *(elegida)*, frente a un endpoint de cancelación aparte.
- **Parámetros:** `keep_alive` y `num_ctx` por petición desde la configuración *(elegida)*; fijarlos solo en el
  servidor de Ollama exigiría tocar otra pila y no viaja con el repositorio.
- **`num_ctx`:** 4096 constante. Con 8192 el KV-cache se duplica y el prompt se evalúa sobre más contexto; el
  historial está acotado por caracteres, así que 4096 basta. Cambiarlo entre peticiones recarga el modelo, por
  eso es una sola variable global.
- **`num_thread`:** sin fijar por defecto (decide Ollama); solo se fija si el benchmark lo justifica.
- **Dos modelos residentes:** no se enruta a `qwen2.5-coder` por defecto: con ~7,75 GiB disponibles, tener
  ambos cargados o alternarlos penaliza más (recargas) de lo que gana. Se podrá activar con evidencia.

## Decisión
- `OllamaProvider` con un único `httpx.AsyncClient` (cerrado en el apagado), `stream()` que parsea NDJSON, y
  `keep_alive`/`num_ctx`/`num_thread` configurables (`OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_NUM_CTX=4096`,
  `OLLAMA_NUM_THREAD` vacío).
- `Gateway.stream()`: política, reintentos y respaldo solo **antes** del primer contenido (después ya se ha
  emitido texto y reintentar duplicaría la respuesta); registra el uso al terminar, fallar o cancelarse.
- `POST /api/chat/stream` (SSE: `start`, `token`, `done`, `error`) además de `/api/chat` y `/api/v1/*`, que no
  cambian. Conversación inexistente o ajena: 404 antes de empezar a emitir. Los errores del proveedor se
  envían con un mensaje genérico.
- Tope de salida adaptativo por tipo de consulta (`OUTPUT_TOKENS_SHORT/DEFAULT/CODE` = 512/1024/2048) y
  historial limitado a `CHAT_HISTORY_MAX_CHARS` (8000), conservando lo más reciente. Son valores de partida:
  se ajustan con el benchmark, no se han medido todavía.
- El mensaje completo se guarda al terminar; si el cliente cancela, se conserva lo generado hasta ese punto.
  El SQLite síncrono del arranque del turno va fuera del bucle de eventos (`asyncio.to_thread`).
- Migración 6: `model_usage.ttft_ms/load_ms/prompt_eval_ms/generation_ms`. Solo se rellenan cuando hay
  métricas; sin contenido de mensajes ni secretos. `GET /api/admin/usage` añade `inference` (medias y cargas
  en frío) y Administración lo muestra.
- Frontend: lectura incremental, repintado solo del mensaje en curso (como mucho cada ~60 ms), botón
  «Detener», indicador de generación y renderizado Markdown propio con nodos DOM (sin `innerHTML`, sin enlaces
  ni imágenes) que mantiene el HTML del modelo como texto.

## Consecuencias
- El primer texto aparece tras carga + lectura del prompt + primer token, en lugar de tras toda la generación.
- `keep_alive` mantiene el modelo (~2 GB) en RAM hasta 30 min: es memoria que se deja de tener para otros
  contenedores. Configurable.
- Un proxy que acumule respuestas rompería el streaming; se envía `X-Accel-Buffering: no` y `Cache-Control:
  no-store`.
- Las cifras de mejora **no** están en este ADR: salen de `scripts/ollama_benchmark.py` ejecutado por el
  usuario (`docs/informe-rendimiento-ollama.md`).
