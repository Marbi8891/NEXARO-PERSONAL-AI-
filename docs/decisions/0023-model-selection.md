# ADR-0023: Selección de modelo por conversación

- **Estado:** Propuesta (pendiente de confirmar por el propietario)
- **Fecha:** 2026-11-22

## Contexto

El modelo se fijaba con `OLLAMA_MODEL` y ningún usuario podía cambiarlo. El propietario pide poder
elegir modelo y proveedor, ver cuál está activo, que la lista se descubra en el proveedor y que un
modelo no disponible dé un error claro sin cambiarse en silencio por otro.

## Decisión

- `GET /api/models` (cualquier usuario con sesión) devuelve lo que el proveedor principal dice que
  tiene instalado. Sin URLs ni detalles internos.
- `model` en el chat: un nombre instalado o `auto`. Con nombre, el gateway comprueba la lista y usa
  **solo** el proveedor principal con ese modelo, sin rutas de respaldo. `auto` es el comportamiento
  anterior (modelo configurado y respaldo).
- La conversación guarda su modelo (migración 9) solo cuando el turno produce respuesta.
- El nombre del modelo se valida con un patrón y, además, debe estar en la lista del proveedor antes
  de llegar a él.

## Trade-offs

- **Choca en parte con ADR-0019:** allí el asistente no revela su modelo. Esta ADR no cambia el
  filtro ni el prompt (el asistente sigue sin hablar de su modelo), pero la interfaz sí muestra a
  cada usuario qué modelos hay y cuál está activo. En una instalación personal es lo que se pide;
  con usuarios externos puede no serlo. **Decisión pendiente:** abierto a todos los usuarios (actual)
  o solo a administradores.
- Comprobar la lista antes de cada turno con modelo fijado añade una llamada local a `/api/tags`.
- Falta modelo por defecto por usuario y por agente, y proveedores en la nube seleccionables.
