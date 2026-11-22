# ADR-0024: Biblioteca de prompts como módulo de la plataforma

- **Estado:** Aceptada
- **Fecha:** 2026-11-22

## Contexto

La rama `feature/prompt-library-mvp` (PR #2) contenía una biblioteca de prompts útil (CRUD, versiones,
catálogo de 100 prompts, packs, workflows) pero como **otra aplicación FastAPI** en la raíz del repositorio:
su propio SQLite, sin autenticación ni organizaciones, con XSS almacenado por ID (corregido en el PR #7) y
un `Dockerfile` que choca con el de la app principal. El propietario decidió (2026-11-22) integrarla como
módulo en lugar de mantener servicios separados.

## Opciones

- **A. Mantener el servicio aparte** y añadirle autenticación: duplicaría sesiones, usuarios y permisos.
- **B. Módulo de la plataforma** *(elegida)*: tablas por organización, permisos y auditoría existentes.
- **Ejecución:** B1, endpoint propio que llama al gateway con el `system_prompt` del prompt; B2 *(elegida)*,
  el servidor **renderiza** y el mensaje se envía por el chat normal. B1 abriría un segundo camino al modelo
  donde el `system_prompt` del usuario sustituiría al de la plataforma (guardia de temas, identidad,
  reglas de seguridad) y habría que duplicar límites, métricas y auditoría.

## Decisión

- Migración 11: `prompts` y `prompt_versions` por organización, clave foránea compuesta
  `(prompt_id, organization_id)` y RLS en PostgreSQL. Permisos `prompts:read` (todos los roles) y
  `prompts:write` (propietario, administrador y miembro, como `documents:write`).
- Código en `products/personal_ai/prompt_library.py` (va unido al chat) y API en
  `/api/organizations/{id}/prompts` y `/api/prompt-catalogue`.
- Cada cambio crea una versión; restaurar crea una versión nueva con el contenido antiguo (el historial
  no se reescribe). Borrar un prompt borra su historial.
- El catálogo de 100 prompts se incluye en el código (`products/personal_ai/data/prompt_catalogue.json`) y
  es de solo lectura; «Instalar» lo copia a la organización (idempotente por `catalogue_id`).
- `POST .../render` sustituye `{{variable}}` con valores literales (no se reinterpretan) y antepone las
  instrucciones del prompt **dentro del mensaje del usuario**. El frontend deja el resultado como borrador
  en el chat: el usuario lo revisa y lo envía.
- Los nombres de variable son identificadores (`[A-Za-z_][A-Za-z0-9_]*`, ≤ 40) y el frontend construye el
  DOM con `h()`, sin `innerHTML`.

## Consecuencias

- Sin duplicar autenticación ni almacenamiento; aislamiento entre organizaciones probado.
- Quedan fuera por ahora: packs, workflows encadenados, evaluación con IA y prompt builder de la rama
  original. Los workflows encadenados se harán sobre la orquestación de agentes, no como otro motor.
- Las instrucciones de un prompt tienen menos peso que el prompt de sistema: es intencionado.
