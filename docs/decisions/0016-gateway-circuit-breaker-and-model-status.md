# ADR-0016: Cortacircuitos del gateway y estado de modelos

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto

Con Ollama caído, cada petición esperaba el tiempo de conexión (5 s) y reintentaba. El modelo se fija por
variable de entorno y no había forma de ver si estaba instalado ni qué otros había.

## Opciones

- A. Dejarlo como está.
- B. Cortacircuitos por proveedor + endpoint de solo lectura con el estado de las rutas.
- C. B + selección de modelo por petición o por perfil.

## Decisión

B. Tras `AI_BREAKER_THRESHOLD` (3) fallos de **disponibilidad** seguidos el proveedor se pone en pausa
`AI_BREAKER_COOLDOWN_SECONDS` (30 s): se pasa a la siguiente ruta si existe o se falla en el acto. Pasado
el enfriamiento se deja pasar una sonda; si funciona, el circuito se cierra. Los timeouts y las respuestas
inválidas no cuentan (una generación lenta no es un proveedor caído). `GET /api/admin/models` consulta
`/api/tags` de Ollama y la salud de cada ruta.

## Razón y trade-offs

Fallo rápido y recuperación automática sin infraestructura nueva; el estado vive en memoria del proceso
(se pierde al reiniciar, no se comparte entre instancias, igual que los limitadores). C se aparca:
cambiar de modelo en una CPU obliga a descargar uno de RAM y cargar el otro, y con un 3B los beneficios
no están medidos. Se reabre con datos de `scripts/ollama_benchmark.py` (DECISION REVIEW).

## Consecuencias

- Una sonda fallida reinicia la pausa; la nube sigue exigiendo su política y presupuesto.
- Las peticiones rechazadas por el circuito quedan en `model_usage` como `denied/circuit_open`.
