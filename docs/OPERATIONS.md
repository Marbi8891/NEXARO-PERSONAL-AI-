# Operación y despliegue

## 1. Requisitos

Para despliegue local Docker:
- Docker Desktop o Docker Engine.
- Docker Compose 2.20 o superior.
- `make` y `curl`.
- Aproximadamente 4 GB de RAM libres para la configuración documentada con `qwen2.5:3b`; el contenedor Ollama tiene un límite configurado de 6 GB por defecto.

## 2. Arranque local

La configuración publicada usa el puerto local 8001 y mantiene el backend accesible solo desde loopback.

```bash
make up
make model
make smoke
```

- `make up`: valida requisitos, construye y espera a que los servicios estén sanos.
- `make model`: descarga el modelo configurado si falta.
- `make model-check`: comprueba el modelo.
- `make smoke`: comprueba servicios, health, modelo, respuesta real y persistencia.

Aplicación: `http://127.0.0.1:8001` (`NEXARO_PORT` si 8001 está ocupado; ajusta también `ALLOWED_ORIGINS`).

Health:
- `/api/health/live`: proceso vivo.
- `/api/health`: servicio y modelo de IA listos.

## 3. Modos de Ollama

### Ollama externo (predeterminado)

Se conecta a la red Docker externa `ollama-local_default`, normalmente creada por el proyecto independiente de Ollama.

### Ollama incluido

Activa el perfil `ollama` y define `OLLAMA_NETWORK=nexaro_ollama` en el archivo `.env`. El perfil crea el contenedor y el volumen persistente de modelos.

No mezcles ambos modos en la misma red. La configuración impide publicar el puerto de Ollama desde este Compose.

## 4. Configuración

Consulta `.env.example` como referencia. El archivo `.env` debe permanecer fuera del control de versiones.

Variables relevantes documentadas:
- `OLLAMA_MODEL`: modelo activo.
- `OLLAMA_NETWORK`: red Docker de Ollama.
- `OLLAMA_IMAGE`: imagen de Ollama; conviene fijar versión o digest.
- `OLLAMA_MEM_LIMIT`: límite de memoria del servicio.
- Configuración de seguridad, cookies, orígenes, base de datos, límites y logs.

No compartas archivos `.env`, secretos, claves API o bases de datos con información real.

## 5. Persistencia

Datos de la aplicación:
- Volumen Docker `nexaro-personal-ai_nexaro_data`.
- SQLite en `/data/nexaro.db`.

Modelos, cuando Ollama está incluido:
- Volumen `nexaro-personal-ai_ollama_models`.

Los volúmenes se conservan al detener el proyecto. **No uses `docker compose down -v`** en una instalación que contenga datos.

## 6. Copias de seguridad

Procedimiento completo, restauración y resultado de la prueba: [BACKUP_RESTORE.md](../BACKUP_RESTORE.md).

```powershell
pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\backup_nexaro.ps1 -Reason pre-update
```

Antes de una actualización:
1. Copia `pre-update` y `verify_backup.ps1`.
2. Ejecuta las pruebas del proyecto.
3. Reconstruye solo el backend conservando el volumen (`docker compose up -d --build --no-deps backend`).
4. Verifica health, login y una consulta de chat (Administración → Operaciones).
5. Conserva la imagen anterior para rollback (`docker tag nexaro-personal-ai-backend nexaro-personal-ai-backend:rollback-<fecha>` antes de construir).

Las migraciones son aditivas y se aplican al arranque en una transacción. No existe downgrade: volver
atrás exige restaurar la copia previa. Una base de un esquema más nuevo (u otra rama) hace que el
backend no arranque, sin modificarla.

## 6 bis. Monitorización

**Administración → Operaciones** (`GET /api/admin/status`, solo administradores): estado del backend,
Ollama y el modelo, integridad y versión de la base, agentes, CPU/memoria del contenedor, disco del
volumen, peticiones y latencia p50/p95, generación de las últimas 24 h, últimos errores 5xx (con su
`request_id`) y estado de la última copia (escrito por `backup_nexaro.ps1`).

Logs: una línea JSON por evento en la salida del contenedor, con `request_id` (también en la cabecera
`X-Request-ID` de cada respuesta), sin cuerpos, consultas ni secretos. Rotación por Docker
(`json-file`, 10 MiB × 5). Para investigar un error del panel:

```powershell
docker logs nexaro-backend 2>&1 | Select-String <request_id>
```

Las métricas de peticiones están en memoria (se reinician con el contenedor); el histórico de uso del
modelo está en la base (`/api/admin/usage`).

## 7. Comprobación de contenedores

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 ollama
```

El nombre de servicio puede variar según el Compose usado; el archivo del proyecto define el contenedor backend como `nexaro-backend`.

## 8. Resolución de problemas

| Síntoma | Posible causa | Acción |
|---|---|---|
| No abre localhost:8001 | Contenedor detenido o puerto ocupado | `docker compose ps`; revisar logs |
| Health devuelve 503 | Ollama no disponible | Comprobar red y contenedor Ollama |
| Modelo no disponible | No está descargado | Ejecutar `make model` |
| La primera respuesta tarda | Carga del modelo en CPU | Esperar; `OLLAMA_KEEP_ALIVE` mantiene el modelo cargado |
| Error de red Ollama | Red externa no creada | Arrancar el Compose externo o cambiar al modo incluido |
| Dos servicios llamados Ollama | Configuración de redes mezclada | Separar los modos externo e incluido |
| Compose demasiado antiguo | Versión inferior a 2.20 | Actualizar Docker Compose |

## 9. Seguridad operacional

- Mantén el acceso local mientras no hayas configurado un despliegue remoto seguro; para el acceso remoto usa solo Tailscale Serve ([REMOTE_ACCESS.md](../REMOTE_ACCESS.md)).
- En producción, HTTPS y cookies Secure son obligatorios por configuración.
- No abras el puerto de Ollama a Internet.
- No publiques el panel de administración sin revisar autenticación y controles.
- Actualiza dependencias y fija imágenes.
- Revisa logs y auditoría; evita copiar datos sensibles.
- Usa copias de seguridad verificadas.
- No despliegues Terraform/AWS sin aprobación explícita del propietario.

## 10. Desarrollo y tests

```bash
make install
make check
make run
```

El objetivo `make check` ejecuta las comprobaciones descritas por el Makefile (lint, tipos, tests y cobertura). Consulta [DEVELOPMENT.md](../DEVELOPMENT.md) para los detalles y comandos de desarrollo.
