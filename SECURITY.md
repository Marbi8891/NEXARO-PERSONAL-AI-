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

## Pendiente / límites

- CSP estricta: requiere sacar el JavaScript inline del frontend (fase de frontend).
- Subir el coste de scrypt exige verificación versionada y rehash (no hecho).
- El aislamiento entre organizaciones aún no existe.

## Reporte de vulnerabilidades

Escribe a mrabehfathiprofesional@gmail.com. No abras un issue público con detalles explotables.
