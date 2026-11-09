# ADR-0011: Permisos por clave de API, lectura de conversaciones y límite por clave

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
ADR-0009 dejó una sola capacidad pública (`/api/v1/chat`) y anotó que los scopes serían necesarios si
la API crecía. Una clave que solo debe leer no debería poder gastar tokens, y una clave actúa en nombre
de su creador, que tiene además un chat web privado que una integración no debe ver.

## Opciones
- **Scopes:** (A) `chat:write` y `conversations:read` *(elegida)*; (B) solo lectura / lectura-escritura;
  (C) scopes finos por recurso. C es sobreingeniería sin endpoints que la justifiquen; B pierde precisión.
- **Qué lee la API:** (A) todas las conversaciones del creador; (B) solo las creadas mediante claves de la
  misma organización *(elegida)*.
- **Límite:** fijo por clave y minuto, en memoria *(elegida)*, frente a no limitar.

## Decisión
- Migración 4: `api_keys.scopes` (texto separado por comas, `NOT NULL DEFAULT 'chat:write'`; las claves
  existentes conservan exactamente lo que podían hacer). La aplicación valida los valores; un permiso
  desconocido o una lista vacía se rechaza al crear.
- `POST /api/v1/chat` exige `chat:write`; `GET /api/v1/conversations` y `/{id}` exigen
  `conversations:read`. Sin el permiso: 403 (la clave ya está autenticada, así que no revela nada nuevo).
- Las conversaciones creadas con una clave se marcan con `conversations.organization_id`. Con clave solo se
  listan, leen o continúan las de esa organización; el chat web (sin organización) y las de otras
  organizaciones responden 404. Inversamente, el chat web no continúa conversaciones de API.
- Límite de `API_KEY_REQUESTS_PER_MINUTE` (60 por defecto) peticiones por clave; al superarlo, 429 con
  `Retry-After: 60`. Cada clave tiene su propio contador.
- La auditoría de `apikey.create` incluye los permisos concedidos.

## Trade-offs
- El contador está en memoria del proceso: se reinicia al reiniciar y no se comparte entre réplicas
  (mismo límite que ADR-0003). Con varias réplicas el límite efectivo se multiplica.
- No se pueden cambiar los permisos de una clave existente: se revoca y se crea otra (más simple y sin
  escaladas silenciosas).
- Las conversaciones web anteriores a esta versión siguen sin organización y son invisibles para claves.

## Consecuencias
- Cada endpoint público nuevo declara su scope; añadir un scope exige actualizar `SCOPES`, la UI y la API.
- UNKNOWN: si harán falta límites por organización o cuotas de coste.
