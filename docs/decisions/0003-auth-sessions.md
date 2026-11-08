# ADR-0003 — Autenticación por sesiones con cookie

- **Estado:** Aceptada (ratifica lo implementado en `docs/AUTH_AUDIT.md`)
- **Fecha:** 2026-11-08

## Contexto
Aplicación web de mismo origen, alta de cuentas controlada por un administrador.

## Opciones
- **A. JWT sin estado.** Revocación difícil; el token vive en JS o en cookie igualmente.
- **B. Sesión opaca en servidor + cookie `HttpOnly`.** Revocación inmediata, nada sensible en el cliente.

## Decisión
**B.** Token aleatorio de 256 bits, solo se guarda su SHA-256; cookie `HttpOnly`, `SameSite=Strict`, `Secure` configurable; allowlist de `Origin` en peticiones que modifican estado; scrypt para contraseñas; límite de intentos por IP y por cuenta.

## Trade-offs
Cada petición consulta la base de datos (aceptable con SQLite local y con PostgreSQL; si fuese cuello de botella, caché corta en Redis).

## Consecuencias
Registro público desactivado por defecto; aprobación manual; nunca se crea un administrador automáticamente. Mejora aplazada: rehash de scrypt con parámetros actuales (ver auditoría).
