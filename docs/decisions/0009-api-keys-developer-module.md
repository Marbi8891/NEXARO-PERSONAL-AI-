# ADR-0009: Claves de API por organización como primer módulo real (Developer)

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
ADR-0008 exige que un módulo entre en la navegación solo cuando tenga API y pantalla reales. El usuario
eligió «Developer: claves de API y uso». Una clave que no autentica nada sería un botón sin función, así
que la clave debe poder llamar a un endpoint público real. La plataforma ya tiene organizaciones, roles
con permisos, auditoría y registro de uso del gateway (`model_usage`).

## Opciones
**Quién es una clave:**
- A. Principal propio (cuenta de servicio) con permisos propios: más flexible, pero exige un modelo nuevo
  de identidad, sin tenerlo hoy.
- B. Actúa en nombre de quien la creó, dentro de una organización. *(elegida)* Reutiliza usuarios,
  conversaciones y permisos; deja de valer si el creador pierde cuenta o membresía.

**Almacenamiento:** hash SHA-256 de una clave de 256 bits aleatorios *(elegida)* frente a un hash lento
(bcrypt/argon2): con esa entropía no hay ataque de diccionario, y un hash lento penalizaría cada petición.
Se guarda un prefijo corto (`nxr_` + 6 caracteres) solo para reconocerla en el listado.

**Uso por clave:** columna `model_usage.api_key_id` rellenada por el gateway *(elegida)* frente a una tabla
de uso aparte (duplicaría el registro y los costes).

## Decisión
- Tabla `api_keys` (migración 3, SQLite y PostgreSQL con las mismas columnas) y permiso `api_keys:manage`
  para propietario y administrador de la organización. Miembros y lectores no gestionan claves.
- La clave completa se devuelve una sola vez al crearla. Revocar es lógico (se conserva la fila y su
  fecha) e idempotente. Caducidad opcional (1–365 días). Máximo 25 claves activas por organización.
- Autenticación `Authorization: Bearer nxr_…` solo en `/api/v1/*`. No usa cookies ni exige Origin (no hay
  navegador); una cookie de sesión no autentica ahí. Los fallos se limitan por IP y la respuesta es la
  misma para clave inexistente, revocada o caducada.
- Una clave es válida solo si no está revocada ni caducada, la organización está activa y su creador
  sigue activo, aprobado y con membresía activa en esa organización.
- `GET /api/organizations/{id}/usage` (permiso `usage:read`): peticiones, errores, tokens y coste por clave.
  Solo cuenta lo que pasó por una clave; el chat personal no tiene organización.
- Auditoría: `apikey.create` y `apikey.revoke`. Nunca se registra la clave ni su hash.

## Trade-offs
- Una clave hereda al creador: si se va de la organización, sus claves dejan de funcionar (deseado, pero
  obliga a recrearlas). Las cuentas de servicio (opción A) quedan para cuando haya un caso real.
- `last_used_at` se actualiza como mucho una vez por minuto para no convertir lecturas en escrituras.
- SQLite no permite añadir una clave foránea compuesta con `ALTER TABLE` y no se reconstruye
  `model_usage` con datos reales: un trigger impone que `api_key_id` pertenezca a `organization_id`.
  En PostgreSQL es una clave foránea compuesta. `api_keys` no tiene RLS porque la clave se busca por su
  hash antes de conocer la organización.
- El límite de fallos usa el limitador en memoria del proceso (no compartido entre instancias).

## Consecuencias
- Un único endpoint público (`/api/v1/chat`). Ampliar la API pública requerirá versionado y, si se
  necesitan permisos por clave, scopes (no implementados: UNKNOWN si harán falta).
- Si se despliega detrás de un proxy, `client_ip` debe reflejar la IP real (VERIFY en el despliegue).
