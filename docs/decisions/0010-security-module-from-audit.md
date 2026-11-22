# ADR-0010: Módulo Security como vista derivada de la auditoría

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
Security es uno de los cinco módulos de marca y la auditoría append-only ya registra accesos, denegaciones y
bloqueos. ADR-0008 exige que un módulo entre en la navegación solo con funcionalidad real.

## Opciones
- A. Tablas nuevas de «incidentes» y reglas de alerta configurables: más potente, pero duplica la auditoría y
  añade complejidad sin un caso de uso demostrado.
- B. Vista y endpoint de resumen calculados desde `audit_events`. *(elegida)* Sin migración, sin duplicar datos.

## Decisión
`GET /api/admin/security` agrega en SQL (una consulta por día/acción/resultado, una por IP y una de recientes,
todas acotadas) y `#/security` lo muestra. Solo administradores de plataforma (ASSUMPTION: la auditoría es
global; un resumen por organización queda para cuando haya eventos con `organization_id`). Los umbrales de
aviso siguen en `notifications.py` (constantes), sin configuración por ahora.

## Trade-offs
- La IP es un dato personal: se muestra solo a administradores y nunca junto a correos o seudónimos.
- `occurred_at` se guarda con `+00:00` (ISO) y los filtros usan `date()`; el día es UTC, no hora local.
- Sin reglas configurables ni exportación; si hacen falta, será una decisión nueva (valor/coste).

## Consecuencias
Todo evento nuevo que se audite aparece en `by_action` sin cambios de código. Detrás de un proxy, `client_ip`
debe reflejar la IP real o el ranking de orígenes será inútil (VERIFY en el despliegue).
