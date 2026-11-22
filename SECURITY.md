# Seguridad

## Controles implementados

- Contraseñas con scrypt (N=2^14, r=8, p=1); sin contraseñas ni secretos en código ni logs.
- Sesiones: token opaco de 256 bits, solo se almacena su SHA-256; cookie HttpOnly,
  `SameSite=Strict`, `Secure` configurable (obligatoria en producción).
- Validación de `Origin` en rutas que modifican estado.
- Limitación de intentos de login por IP+correo; hash ficticio para igualar tiempos.
- Auditoría append-only (triggers que impiden UPDATE/DELETE), con correo seudonimizado.
- Sin administradores ni registro público creados automáticamente.
- Contenedor no root (uid 10001), cabeceras `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`.
- CI: pip-audit, gitleaks, escaneo de imagen con Trivy.

- Aislamiento entre organizaciones: `organization_id NOT NULL` + claves foráneas compuestas
  (la base rechaza referencias entre organizaciones), acceso por membresía y permiso (404 si no
  eres miembro, incluso siendo admin de plataforma) y, en PostgreSQL, Row Level Security.
  Un test inspecciona el esquema y falla si una tabla nueva no lo cumple.

- Frontend: CSP estricta (`script-src 'self'`, sin estilos ni manejadores en línea), sin `innerHTML`/`eval`
  (un test lo vigila) y fuentes autoalojadas.
- Claves de API: solo se guarda el hash SHA-256 (clave de 256 bits), el secreto se muestra una vez, caducan
  y se revocan, dejan de valer si su creador pierde cuenta o membresía, y los fallos se limitan por IP
  con respuesta uniforme. Nunca se registran en auditoría (ADR-0009).
- Resumen de seguridad (`/api/admin/security`): solo administradores; muestra IP de origen de accesos fallidos (dato personal: acceso restringido) y nunca correos, seudónimos ni `details`.
- Avisos y panel: se calculan en servidor a partir de datos reales; no incluyen correos, IPs ni contenido.
- Infraestructura (Terraform): rol de la tarea sin comodines, cifrado con KMS, buckets sin acceso
  público, HTTPS obligatorio, credenciales de base de datos gestionadas por AWS. Tests estáticos
  lo vigilan; `terraform validate` solo se ejecuta en CI.

## Pendiente / límites

- El límite de intentos (login y claves de API) es en memoria del proceso; con varias instancias haría falta un almacén compartido. `client_ip` debe reflejar la IP real tras un proxy (VERIFY en el despliegue).
- Sin scopes por clave de API: una clave puede lo mismo que su creador en `/api/v1/chat`.
- Subir el coste de scrypt exige verificación versionada y rehash (no hecho).
- RLS solo existe en el DDL de PostgreSQL y no protege frente a superusuarios; la aplicación aún no
  ejecuta sobre PostgreSQL (ADR-0005). En SQLite el aislamiento depende de claves compuestas y de la capa de aplicación.
- Documentos, agentes y tareas tienen tablas pero aún no API: el aislamiento está probado a nivel de esquema.

## Reporte de vulnerabilidades

Escribe a mrabehfathiprofesional@gmail.com. No abras un issue público con detalles explotables.
