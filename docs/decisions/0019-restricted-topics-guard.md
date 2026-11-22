# ADR-0019: Bloqueo de preguntas sobre el modelo de IA y la infraestructura interna

- **Estado:** Propuesta (implementada en `feature/nexaro-design-system`, pendiente de revisión)
- **Fecha:** 2026-11-17

## Contexto

Las preguntas sobre qué modelo usa el asistente, su proveedor o la infraestructura interna
(servidores, base de datos, contenedores, red, prompt de sistema) no deben responderse. Además, el
prompt de sistema le daba al modelo el proveedor, el modelo y el stack (FastAPI, SQLite, Docker
Compose), así que cualquier pregunta podía sacarlos.

## Opciones

- A. Solo una instrucción en el prompt. Sin coste, pero no es determinista y el modelo seguiría
  teniendo los datos.
- B. Filtro determinista en el backend antes del proveedor y prompt sin esos datos.
- C. Clasificador con el propio LLM. Duplica la latencia y el coste de CPU de cada mensaje, y el
  clasificador también se puede manipular.

## Decisión

B. `products/personal_ai/guard.py` clasifica el mensaje (`model`, `infrastructure`, `internal` o
ninguna) frase a frase sobre el texto normalizado (minúsculas, sin tildes). Se aplica en
`PersonalAIService.chat` y `open_stream` (o sea, en `/api/chat`, `/api/chat/stream` y
`/api/v1/chat`) y en `/api/organizations/{id}/documents/ask`, antes de buscar en documentos y de
llamar al proveedor. Si una pregunta queda bloqueada:

- se responde con un texto fijo (`REFUSAL`), con el mismo contrato que una respuesta normal (en
  streaming: `start`, `token`, `done`);
- el turno se guarda en la conversación y la propiedad se comprueba igual que en un turno normal
  (404 si la conversación es de otro usuario);
- en el log queda solo la categoría, nunca el texto del usuario;
- no se registra consumo del modelo porque no hay inferencia.

El prompt de sistema deja de incluir el proveedor, el modelo y el stack, y añade una regla de
confidencialidad con la misma respuesta fija (defensa en profundidad).

## Trade-offs

- Se prefieren los falsos negativos a los falsos positivos: el «tú» impersonal del español
  («¿qué puertos tienes que abrir para SSH?») obliga a exigir una señal clara de que se pregunta por
  NEXARO o por el asistente. Una reformulación hábil o en otro idioma puede pasar el filtro. En ese
  caso, el modelo ya no tiene los datos.
- Mencionar NEXARO junto a términos de infraestructura se bloquea aunque la pregunta sea por la marca
  NEXARO de servicios («¿qué arquitectura usa NEXARO para sus webs?»).
- Los patrones están en una lista de reglas. Cada cambio debe añadir casos a `tests/unit/test_guard.py`,
  tanto bloqueados como permitidos.

## Consecuencias

- `build_system_prompt()` ya no recibe argumentos.
- El administrador sigue viendo el modelo en `GET /api/admin/models`: el bloqueo afecta a lo que
  responde el asistente, no a la consola de administración.
