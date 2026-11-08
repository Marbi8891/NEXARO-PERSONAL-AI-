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

- Infraestructura (Terraform): rol de la tarea sin comodines, cifrado con KMS, buckets sin acceso
  público, HTTPS obligatorio, credenciales de base de datos gestionadas por AWS. Tests estáticos
  lo vigilan; `terraform validate` solo se ejecuta en CI.

## Pendiente / límites

- CSP estricta: requiere sacar el JavaScript inline del frontend (fase de frontend).
- Subir el coste de scrypt exige verificación versionada y rehash (no hecho).
- RLS solo existe en el DDL de PostgreSQL y no protege frente a superusuarios; la aplicación aún no
  ejecuta sobre PostgreSQL (ADR-0005). En SQLite el aislamiento depende de claves compuestas y de la capa de aplicación.
- Documentos, agentes y tareas tienen tablas pero aún no API: el aislamiento está probado a nivel de esquema.

## Reporte de vulnerabilidades

Escribe a mrabehfathiprofesional@gmail.com. No abras un issue público con detalles explotables.
