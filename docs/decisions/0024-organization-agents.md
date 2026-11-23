# ADR-0024: Agentes personales y de organización

- **Estado:** Aceptada (el propietario eligió «ambos» el 2026-11-22)
- **Fecha:** 2026-11-22

## Contexto

Los agentes personales (migración 10, `user_agents`) solo los ve su propietario. El propietario
decidió que haya también agentes compartidos por una organización. La tabla `agents` de 0002 ya
estaba pensada para eso, con `organization_id`, pero ningún código la usaba.

## Decisión

- Se reutiliza `agents` y la migración 11 solo **añade** columnas (`category`, `base_agent`,
  `tools`, `model`, `updated_at`) e índice. No borra ni reescribe datos. `system_prompt` guarda las
  instrucciones.
- Mismas reglas que un agente personal: parte de un agente predefinido, hereda sus reglas y como
  máximo sus herramientas; las instrucciones van delimitadas y subordinadas al prompt general.
- Permisos de la organización ya existentes: `agents:read` para verlos (todos los roles),
  `agents:manage` para crear, editar, duplicar y borrar (propietario y administrador) y
  `agents:run` para usarlos en el chat (propietario, administrador y miembro; el lector no).
- `GET /api/agents` lista los de las organizaciones donde el usuario puede usarlos, sin sus
  instrucciones. Al usar uno en el chat se vuelve a comprobar la membresía activa, el permiso y el
  estado del agente: quien sale de la organización deja de poder usarlo al instante.
- No ser miembro da 404 de la organización; un agente de otra organización, 404 del agente; en el
  chat, 422 «Agente no disponible» en todos los casos.

## Trade-offs

- Dos tablas con casi las mismas columnas en lugar de una con «ámbito»: evita reescribir
  `user_agents` (que exigiría recrear la tabla en SQLite) a cambio de algo de código paralelo.
- Falta la pantalla para gestionarlos: de momento se gestionan por API; en el chat ya aparecen
  como «Nombre · Organización».
