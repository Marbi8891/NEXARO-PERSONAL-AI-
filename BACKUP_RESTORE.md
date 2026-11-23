# Copias de seguridad y restauración (v1.0)

Sistema de copias para el despliegue personal en Windows + Docker Desktop. Scripts en PowerShell
(5.1 y 7) que hacen el trabajo con SQLite **dentro de un contenedor** de la propia imagen del
backend: el equipo no necesita Python ni `sqlite3`.

> Ruta del repositorio en los ejemplos: `C:\Users\pc\NEXARO-PERSONAL-AI-` (el clon desde el que
> despliegas con `docker compose`). Destino por defecto de las copias: `C:\Users\pc\NEXARO-Backups`
> (variable `NEXARO_BACKUP_ROOT` o parámetro `-BackupRoot`). **Nunca dentro del repositorio**: el
> script se niega.

## Qué se copia

Cada copia es una carpeta `nexaro-<AAAAMMDD-HHMMSS>-<motivo>` con:

| Archivo | Contenido |
|---|---|
| `nexaro.db` | Base SQLite completa (usuarios, sesiones, conversaciones, mensajes, organizaciones, **documentos y sus fragmentos**, claves de API (solo hash), gastos, auditoría, uso del modelo). Copia consistente con la API de backup de SQLite. |
| `config/compose.yaml`, `config/.env.example` | Configuración del despliegue. |
| `config/env.redacted` | Tu `.env` con los valores de claves sensibles (`*SECRET*`, `*TOKEN*`, `*PASSWORD*`, `*KEY*`, credenciales) sustituidos por `<redacted>`. |
| `container.json` | Imagen del backend y variables de entorno **no sensibles** del contenedor. |
| `models.txt` | Modelo configurado y `ollama list` (los modelos se vuelven a descargar con `make model`; no se copian los GB de pesos). |
| `manifest.json` | Motivo, fecha, commit, imagen, versión del esquema, recuentos por tabla e integridad. |
| `SHA256SUMS` | SHA-256 de cada archivo. |

Los archivos se marcan como **solo lectura**; el nombre lleva fecha y hora y el script falla si ya
existe (no se sobrescribe nunca). Una copia a medias se escribe en `*.partial` y se borra si algo falla.

**Las copias contienen datos personales** (conversaciones, documentos). Guárdalas en una unidad
cifrada (BitLocker) y, si las sacas del equipo, en un destino cifrado.

## Uso

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\backup_nexaro.ps1
```

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\verify_backup.ps1
```

| Parámetro de `backup_nexaro.ps1` | Por defecto | Uso |
|---|---|---|
| `-Reason` | `manual` | `daily`, `pre-migration`, `pre-update`, `pre-restore`, `manual` |
| `-Keep` | 14 | Copias que se conservan **de ese motivo**. Solo se retiran carpetas creadas por el script (patrón exacto + `manifest.json`); una carpeta con un archivo `.keep` nunca se retira |
| `-NoPrune` | — | No aplica la retención |
| `-BackupRoot` | `C:\Users\pc\NEXARO-Backups` | Destino (fuera del repositorio) |

- **Con el backend en marcha**: `docker exec` + API de backup de SQLite (no bloquea la app; las
  transacciones sin confirmar no entran en la copia). La copia temporal dentro del volumen se borra.
- **Con el backend parado**: contenedor temporal sin red con el volumen montado **en solo lectura**.
- Tras cada copia se verifica `integrity_check` y `foreign_key_check` en un contenedor sin red.
- Resultado en `C:\Users\pc\NEXARO-Backups\backup-log.jsonl` (una línea por ejecución) y
  `last-backup.json`; si el backend está en marcha, también en `/data/backup-status.json`, que
  muestra **Administración → Operaciones** (copia «Al día», «Antigua» (> 26 h), «Falló»…).

### Antes de migrar o actualizar

Las migraciones se aplican al arrancar el backend. Antes de reconstruirlo:

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\backup_nexaro.ps1 -Reason pre-update
```

(El PR #5 `fix/copia-antes-de-migrar` añade además una copia automática dentro del volumen justo
antes de aplicar migraciones; ver AUDIT_V1.md §4.)

### Copia diaria automática

Programarla modifica el Programador de tareas de Windows: **requiere tu autorización** y no se ha
hecho. El script, por defecto, solo muestra lo que haría:

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\register_backup_task.ps1
```

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\register_backup_task.ps1 -Register -At 03:30
```

Crea la tarea «NEXARO Backup diario» para tu usuario (sin privilegios elevados), con
`StartWhenAvailable` (si el portátil estaba apagado, se ejecuta al volver).

## Restauración

`restore_nexaro.ps1` verifica la copia antes de escribir nada.

**Restaurar para probar (por defecto, seguro):** crea un volumen NUEVO `nexaro-restore-<fecha>` y no
toca el real.

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\restore_nexaro.ps1 -Path C:\Users\pc\NEXARO-Backups\nexaro-20261124-033000-daily
```

Arranca un backend de prueba sobre él (puerto distinto, solo local) para comprobarlo:

```powershell
docker run --rm -d --name nexaro-restore-check -p 127.0.0.1:8011:8000 -v nexaro-restore-20261124-090000:/data nexaro-personal-ai-backend
```

**Restaurar de verdad (sustituir la base en uso):**

```powershell
docker stop nexaro-backend
```

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\restore_nexaro.ps1 -Path C:\Users\pc\NEXARO-Backups\nexaro-20261124-033000-daily -IntoLiveVolume
```

```powershell
docker start nexaro-backend
```

Con `-IntoLiveVolume` el script: exige el backend parado → hace una copia `pre-restore` del estado
actual → pide que escribas `RESTAURAR` → **renombra** (no borra) la base anterior a
`nexaro.replaced-<fecha>.db` dentro del volumen → copia la restaurada. No admite `-Yes`.

Si la copia es de un esquema más antiguo, el backend aplica las migraciones pendientes al arrancar.
Si es de un esquema **más nuevo** que el código (o de una rama con otra numeración de migraciones),
el backend se niega a arrancar sin modificar la base (probado en `tests/integration/test_upgrade_paths.py`).

## Prueba de restauración (obligatoria) — resultado

`scripts/test_backup_restore.ps1` hace la prueba completa en un entorno **temporal**: volúmenes y
contenedores `nexaro-bkptest-*` con la etiqueta `nexaro.test=<id>`, puertos 127.0.0.1:8091/8092,
datos sintéticos. Al terminar borra **solo** lo que creó (filtro por etiqueta y prefijo). No toca
`nexaro-personal-ai_nexaro_data`.

```powershell
docker build -t nexaro-personal-ai-backend:v1-candidate C:\Users\pc\NEXARO-PERSONAL-AI-
```

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\test_backup_restore.ps1 -Image nexaro-personal-ai-backend:v1-candidate
```

Ejecutada el 2026-11-23 con la imagen construida desde esta rama (esquema v7):

| Comprobación | Resultado |
|---|---|
| Arranque del backend de origen | PASS |
| Datos sintéticos (admin, conversación con 2 mensajes, organización, documento) | PASS |
| Copia con el backend en marcha (`docker exec`) | PASS |
| Copia con el backend parado (volumen `:ro`) | PASS |
| `verify_backup.ps1` de las dos copias (SHA-256, integridad, FK, manifiesto) | PASS |
| Archivos de la copia en solo lectura | PASS |
| Copia manipulada detectada (un byte cambiado → verificación falla) | PASS |
| Restauración en un volumen nuevo | PASS |
| Negativa a restaurar sobre un volumen que ya tiene base | PASS |
| Arranque del backend sobre la copia restaurada | PASS |
| Login con la cuenta de la copia | PASS |
| Conversación y mensajes recuperados (contenido idéntico) | PASS |
| Documento recuperado | PASS |
| Limpieza: 0 contenedores y 0 volúmenes `nexaro-bkptest-*` restantes | PASS |

**Copias reales (2026-11-23):** `nexaro-20261123-154227-pre-update` (esquema v6, backend parado)
y `nexaro-20261123-154314-manual` (v7, backend en marcha), ambas «COPIA VÁLIDA». La primera destapó
un fallo que los datos sintéticos no cubrían: una base WAL cerrada limpiamente no tiene `-shm` y
SQLite no puede crearlo en un volumen de solo lectura («unable to open database file»). La copia en
frío abre ahora el origen en modo `immutable` (solo con el backend parado y el volumen `:ro`); test
de regresión en `test_backup_scripts.py`.

**Copia diaria:** tarea «NEXARO Backup diario» registrada el 2026-11-23 (03:30, retención 14);
ejecución de prueba correcta (`nexaro-20261123-154529-daily`, «COPIA VÁLIDA»). Apunta al script
del worktree de la rama v1: tras integrarla en `main`, repite `register_backup_task.ps1 -Register`
desde el clon definitivo (sustituye la tarea; `-Force`). Para quitarla:
`Unregister-ScheduledTask -TaskName 'NEXARO Backup diario'`.

**Pendiente:** la restauración con
`-IntoLiveVolume` no se ha ejecutado sobre datos reales (por diseño: solo tú debes hacerla).

## Tests automáticos

`tests/unit/test_backup_scripts.py`: copia consistente con un escritor activo, no sobrescritura,
detección de una copia corrupta, borrado limitado a sus temporales, scripts sin `down -v`/`volume rm`
(salvo la prueba, filtrada por etiqueta), destino fuera del repositorio, restauración por defecto
en volumen nuevo y sintaxis de todos los `.ps1`.

## Scripts bash anteriores (macOS)

`scripts/rebuild_backend.sh` y `scripts/prune_backups.sh` (bash, macOS) siguen existiendo para el
MacBook. `rebuild_backend.sh` depende de una copia concreta de noviembre (`BACKUP_SHA`); en Windows
usa este documento.
