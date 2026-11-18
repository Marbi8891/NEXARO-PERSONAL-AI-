# ADR-0020: Modo tutor de programación

- **Estado:** Aceptada
- **Fecha:** 2026-11-17

## Contexto

El usuario quiere un asistente de programación que funcione en su Docker y que le **guíe** en lugar de
darle la solución (estudia DAW). También quiere usarlo desde Python Learning Dashboard (PLD).

## Opciones

- A. Un modo dentro de NEXARO Personal AI: el mismo backend, Ollama, cuentas, historial y filtro.
- B. Una extensión del editor (Continue) conectada a Ollama: sin código propio.
- C. Un servicio o agente nuevo con herramientas: lento y poco fiable con un i5 sin GPU y modelos
  de 3–7B, y con más superficie de ataque.

## Decisión

A. `ChatRequest.mode` admite `general` (por defecto) o `tutor` en `/api/chat`, `/api/chat/stream` y
`/api/v1/chat`. El tutor **añade** reglas al prompt general (`TUTOR_RULES`): identidad, seguridad,
confidencialidad y el filtro de `guard` son los mismos. Reglas pedagógicas:

- pistas graduales;
- la solución completa solo tras un intento propio y si la pide;
- señalar el error en vez de reescribir su código;
- ejemplos breves;
- terminar con una pregunta.

Nunca usa el tope de salida largo de «code» (2048): usa el general (1024). Las consultas breves
siguen con el corto. En esta CPU, menos tokens son respuestas antes.

El modo va en cada mensaje y no se guarda en la conversación: sin migración, igual que los documentos
(ADR-0017). El frontend lo recuerda en `localStorage`.

PLD lo usa a través de `/api/v1/chat` con una clave de API guardada solo en su backend (ver su
documentación).

## Trade-offs

- **Mismo modelo que el modo general.** El gateway fija el modelo por ruta (`Route.model`) e ignora
  el de la petición. Un modelo propio para el tutor (p. ej. `qwen2.5-coder`) exige tocar el enrutado.
  Se decidirá con los datos de `make eval` (categoría `tutor`, comprobación `max_code_lines`).
- El comportamiento depende del modelo. Un 3B puede saltarse las reglas y dar la solución. La
  evaluación lo mide; el backend no lo impide.

## Consecuencias

- `build_system_prompt(mode)`; casos `tutor` en `scripts/eval/cases.json`.
- Selector «Modo» en el chat.
