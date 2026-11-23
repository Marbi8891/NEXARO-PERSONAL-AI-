# NEXARO Personal AI 1.0 — notas de versión (candidata)

Rama `claude/nexaro-v1-consolidation-921fe0` sobre `main` (4022b0e). **Sin commit ni merge**: los
cambios están en el árbol de trabajo para tu revisión. Estado de release: ver
[RELEASE_CHECKLIST_V1.md](RELEASE_CHECKLIST_V1.md).

## Qué es la 1.0

Una versión **personal**: un único equipo (ThinkPad, Windows + Docker Desktop), tus cuentas,
modelos locales con Ollama y acceso desde tus dispositivos por Tailscale. No es un producto para
clientes externos (sin alta disponibilidad, sin correo saliente, límites en memoria de un proceso).

## Novedades

### Seguridad
- **Obsidian solo para el propietario.** Hasta ahora cualquier cuenta aprobada podía leer tu Vault
  entero. Ahora: administradores y las cuentas de `OBSIDIAN_ALLOWED_EMAILS`; el resto recibe 403 y
  queda en la auditoría. Notas de más de 1 MiB no se cargan; los recorridos se detienen a las 5 000
  notas; 60 consultas por minuto y usuario.
- **Cambio de contraseña** en Perfil → Contraseña (`POST /api/auth/password`): exige la actual, cierra
  tus demás sesiones y se limita como el login.
- La interfaz ya no queda en caché tras actualizar (revalidación en cada carga, barata gracias a ETag).

### Copias de seguridad
- `backup_nexaro.ps1`: copia consistente con la app en marcha o parada, verificada (integridad, claves
  foráneas, SHA-256), de solo lectura, nunca sobrescrita, fuera del repositorio, con retención por
  motivo y registro. La configuración se copia sin secretos.
- `verify_backup.ps1`, `restore_nexaro.ps1` (por defecto en un volumen nuevo; sobre el real solo con
  confirmación escrita y copia previa) y `register_backup_task.ps1` (copia diaria; simulación por
  defecto).
- Prueba completa de restauración en entorno temporal: 14/14 PASS (BACKUP_RESTORE.md).

### Operación
- **Administración → Operaciones**: backend, Ollama y modelo, base de datos (integridad, esquema,
  tamaño), agentes, CPU/memoria/disco, peticiones, latencia p50/p95, generación de las últimas 24 h,
  últimos errores 5xx con `request_id` y estado de la última copia.
- `NEXARO_PORT`, `ALLOWED_ORIGINS` y `COOKIE_SECURE` configurables desde `.env`.

### Acceso remoto
- `remote_access.ps1` (check / plan / enable / disable) y REMOTE_ACCESS.md: Tailscale Serve con HTTPS
  privado, sin abrir puertos, sin publicar el backend ni Ollama. **No activado**: requiere instalar
  Tailscale (tu decisión).

### Móvil y PWA
- Pestañas desplazables en pantallas estrechas, controles táctiles de 44 px, service worker también en
  `127.0.0.1`, manifest con `id` y icono para iOS/macOS.

### Calidad
- Tests nuevos: aislamiento y límites de Obsidian, cambio de contraseña, actualización desde cada
  versión anterior del esquema, rechazo seguro de bases de otras ramas, panel de operaciones, scripts
  de copias, E2E de Operaciones.
- 5 tests que fallaban en Windows (codificación) corregidos; también `quality_eval.py`.
- `scripts/smoke_isolated.ps1`: prueba una imagen nueva contra el Ollama real con datos temporales.
- Resultado: 665 tests passed, 0 failed, 3 skipped (91,70 % de cobertura); E2E 36/36; evaluación de
  la IA 34/42 con `qwen2.5:3b` (AI_EVALUATION.md).

## Actualizar desde la instalación actual

La base del ThinkPad está en el esquema 6; esta versión aplica la 7 al arrancar (aditiva, probada).
Sigue [DEPLOYMENT.md](DEPLOYMENT.md#despliegue-permanente-en-el-thinkpad-windows--docker-desktop--v10):
resolver el puerto 8001, copia `pre-update`, `docker compose up -d --build --wait`.

## No incluido (en PRs pendientes)

Renombrar conversaciones (#8), selección de modelo por conversación (#9), agentes personales y de
organización (#10), Prompt Library integrada (#11), copia automática antes de migrar (#5) y el
aislamiento estricto de conversaciones con triggers (rama `integration/security-conversation-isolation`).
Orden de integración y conflictos de numeración: AUDIT_V1.md §4.

## Problemas conocidos

- NEXARO no arranca mientras `nexaro-prompt-library` ocupe `127.0.0.1:8001` (ver DEPLOYMENT.md).
- Sin recuperación de contraseña olvidada.
- Sesiones de 7 días sin caducidad por inactividad.
- Métricas del panel en memoria (se reinician con el contenedor).
