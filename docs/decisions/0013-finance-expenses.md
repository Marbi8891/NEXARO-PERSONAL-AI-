# ADR-0013: Módulo Finance, primer alcance: gastos de la organización

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
El usuario eligió «Finance/Business» y, entre gastos, facturas y CRM ligero, empezar por **gastos**.
Es el caso más pequeño con valor inmediato (controlar lo que se gasta y preparar el IVA soportado) y no
tiene las obligaciones legales de la facturación (numeración correlativa, VERI*FACTU). Los datos son
dinero: deben ser exactos, aislados por organización y de acceso restringido.

## Opciones
- **Importes:** céntimos enteros *(elegida)* frente a decimal/float. Sin errores de redondeo; en PostgreSQL
  `bigint`.
- **Categorías:** texto libre normalizado (minúsculas, espacios colapsados) *(elegida)* frente a tabla de
  categorías por organización (más pantallas y gestión sin necesidad hoy) o lista fija en código
  (configuración incrustada). La interfaz sugiere las ya usadas.
- **Quién ve finanzas:** solo propietario y administrador de la organización *(elegida)*, con permisos
  nuevos `expenses:read`/`expenses:write`; miembros y lectores no. Reutilizar `documents:*` o `usage:read`
  mezclaría conceptos.
- **Borrado:** lógico (`deleted_at`) *(elegida)*, recuperable desde base de datos; no hay papelera en UI.

## Decisión
- Migración 5 (`expenses`, SQLite y PostgreSQL con las mismas columnas; en PostgreSQL con RLS por
  organización como el resto de tablas de inquilino). `CHECK` en base de datos: importe > 0, IVA entre 0
  y el importe, descripción 1–200, categoría 1–40, fecha con formato válido.
- Módulo `products/finance`. API bajo `/api/organizations/{id}/expenses`: listar con filtros (fechas,
  categoría, texto, paginación), crear, editar parcialmente, borrar, `summary?month=AAAA-MM` y
  `export.csv`.
- Importe = total pagado **con IVA**; `vat_cents` = parte del total que es IVA (puede ser 0). Moneda única
  EUR (ASSUMPTION: negocio español; la columna `currency` existe pero solo se usa EUR).
- Fechas: desde 2000-01-01 hasta mañana. Importe máximo 1 000 000 €.
- Resumen mensual: total, IVA, número, reparto por categoría y serie de 6 meses, con tres consultas
  (sin N+1). La interfaz muestra los céntimos con `Intl` en es-ES.
- Exportación CSV pensada para hoja de cálculo en español: `;`, coma decimal, BOM UTF-8, y neutraliza
  celdas que empiecen por `= + - @` (inyección de fórmulas). Exportar queda auditado (`expense.export`).
- Auditoría: `expense.create`, `expense.update` (con los campos tocados, no los valores),
  `expense.delete`, `expense.export`.

## Trade-offs
- No hay adjuntos (tickets/facturas escaneadas), recurrencia, presupuestos ni multimoneda. Son los
  siguientes candidatos si hay uso real; añadirlos ahora sería especulación.
- Sin conciliación bancaria ni cálculo fiscal: el IVA se registra tal cual lo introduce el usuario, no se
  valida contra un tipo. **No es contabilidad ni sustituye a un asesor.**
- Sin tope de gastos por organización; la lista se pagina a 200 y el resumen agrega en SQL.
- Cuando se hagan facturas habrá que decidir si comparten tabla/categorías con gastos (UNKNOWN).

## Consecuencias
- `role_permissions` de propietario/administrador crece en dos permisos (paridad comprobada con PostgreSQL).
- Si un cliente necesita que un miembro registre gastos sin ver el resumen, hará falta un permiso más
  fino (UNKNOWN si hace falta).
