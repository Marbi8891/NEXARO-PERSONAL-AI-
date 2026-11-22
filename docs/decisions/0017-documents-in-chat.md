# ADR-0017: Documentos en el chat (Fase 4, primer alcance)

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto

Los documentos de una organización ya se cargan, se trocean y se buscan con BM25 (ADR-0012), pero solo
se usan desde la pantalla «Documentos» (`/ask`). El chat normal no los conocía.

## Opciones

- A. El chat consulta los documentos con el BM25 existente, con interruptor por mensaje.
- B. Memoria de usuario (hechos persistentes entre conversaciones; tabla y migración nuevas).
- C. Embeddings semánticos con un modelo de Ollama (usa la tabla `embeddings`).
- D. Resumen de conversaciones largas con el propio modelo.

## Decisión

A, opt-in. `POST /api/chat` y `/api/chat/stream` aceptan `document_organization_id`. Sin él, nada cambia.
Con él, el router exige membresía y `documents:read` (404 si no es miembro, 403 sin permiso, igual que las
rutas de la organización), el servicio busca los 4 mejores fragmentos y los envía **solo en ese mensaje**:
fragmentos delimitados y neutralizados en el mensaje de usuario, reglas en el prompt de sistema (las mismas
que `/ask`). En la base se guarda el texto que escribió el usuario, no el contexto. Las fuentes viajan en
un evento SSE `sources` (o en `sources` en la respuesta sin streaming). Sin fragmentos relevantes el
modelo responde igualmente, con una instrucción de no inventar contenido de los documentos.

## Razón y trade-offs

Máximo valor con cero migraciones ni dependencias, y sin gastar contexto salvo que el usuario lo pida
(la CPU es el cuello de botella). Límites conocidos: la búsqueda es léxica (sin sinónimos); la consulta
es el mensaje actual, sin reformular con el historial (un «¿y la fianza?» de seguimiento rinde menos);
las fuentes no se guardan, al reabrir la conversación solo quedan las citas `[n]` del texto. B, C y D
se reevalúan con uso real y datos del benchmark (DECISION REVIEW).

## Consecuencias

- El tamaño de entrada sube hasta ~4 KB por mensaje con documentos; sigue acotado por `AI_MAX_INPUT_CHARS`.
- `check_org_permission` se extrae de `require_permission` y lo comparten las rutas de organización y el chat.
