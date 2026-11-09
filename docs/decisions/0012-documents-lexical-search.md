# ADR-0012: Documentos por organización con búsqueda léxica (sin embeddings por ahora)

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
El usuario pidió «Personal AI con documentos». El esquema de la migración 2 ya tiene `documents`,
`document_chunks` (con claves foráneas compuestas por organización) y `embeddings`, y los permisos
`documents:read`/`documents:write`. Falta decidir cómo se busca el contenido y cómo se responde con él.

## Opciones
- **A. Embeddings con Ollama** (`nomic-embed-text` o similar): encuentra sinónimos, pero exige descargar
  otro modelo (UNKNOWN cuál hay instalado), añade latencia de indexado, una dependencia de red entre
  contenedores en cada subida y vectores que recalcular al cambiar de modelo. No se puede verificar sin
  Ollama real.
- **B. SQLite FTS5:** rápido, pero crea tablas virtuales y sombra que rompen la prueba de paridad con
  PostgreSQL (que comparan tablas y columnas) y habría que reimplementarlo con `tsvector` en PostgreSQL.
- **C. Puntuación BM25 en Python sobre los fragmentos de la organización** *(elegida)*: sin migración, sin
  dependencias, idéntica en SQLite y PostgreSQL, determinista y probable al 100 % en CI.

## Decisión
- Solo texto plano UTF-8 (`.txt`, `.md`, `.csv`, `.json`, `.log`); la interfaz lee el archivo y envía su
  texto en JSON (no hay subida multipart ni dependencia nueva). PDF y Office quedan fuera: UNKNOWN si
  hacen falta (requerirían extracción de texto y revisar su superficie de ataque).
- Límites: 200 000 caracteres por documento, 100 documentos activos por organización. Mismo contenido
  (SHA-256) en la misma organización: 409.
- Fragmentos de ~1000 caracteres por párrafos y frases. Búsqueda: normalización sin tildes ni mayúsculas,
  palabras vacías, raíz de 6 caracteres (aproxima plurales) y BM25 (k1=1,5; b=0,75).
- Endpoints bajo `/api/organizations/{id}/documents`: listar, subir, borrar (lógico, y se eliminan sus
  fragmentos), `search` y `ask`. Permisos: lee quien tenga `documents:read` (todos los roles), escribe
  `documents:write` (propietario, administrador, miembro).
- `ask`: los 4 fragmentos más relevantes se pasan al modelo dentro de etiquetas `<fragmento>` con una
  instrucción de sistema que los declara contenido, no órdenes. Sin fragmentos relevantes **no se llama al
  modelo** y se responde que no hay información (evita respuestas inventadas y gasto). La respuesta lleva
  las fuentes. No se guarda como conversación. El uso queda registrado con la organización.
- Auditoría: `document.create` y `document.delete` (sin el contenido).

## Trade-offs
- No encuentra sinónimos ni paráfrasis («coche» frente a «automóvil»). Es el límite real de la opción C.
- Cada búsqueda lee y tokeniza todos los fragmentos de la organización: con los límites de arriba son
  como mucho ~20 MB de texto; es aceptable para uso personal y de equipo pequeño, no para corpus grandes.
- La inyección de instrucciones en documentos se mitiga (delimitación + prompt de sistema), no se elimina:
  un modelo pequeño local puede seguir obedeciendo texto malicioso. Quien sube documentos es miembro de
  la organización, no un anónimo.
- El borrado de fragmentos es físico: borrar un documento lo hace irrecuperable salvo desde copia.

## Consecuencias
- Sin migración nueva. La tabla `embeddings` sigue sin uso.
- Cuando el corpus supere los límites o se necesiten sinónimos: añadir embeddings (opción A) detrás de la
  misma interfaz `search`, indexando al subir y reordenando con BM25 + similitud. VERIFY entonces qué
  modelo de embeddings hay en el Ollama del usuario.
