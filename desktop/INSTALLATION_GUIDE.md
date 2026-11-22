# Guía de instalación de NEXARO AI (Windows 10 y 11)

## Qué se instala y qué no

| | Qué es | ¿Lo instala NEXARO? |
|---|---|---|
| **NEXARO AI** | La aplicación de escritorio (este instalador). | Sí. Por usuario, sin permisos de administrador. |
| **Docker Desktop** | Ejecuta el backend de NEXARO. **Obligatorio.** | No. Requiere administrador, WSL 2 y virtualización: lo instalas tú. |
| **Ollama para Windows** | Ejecuta los modelos de IA en tu PC. **Recomendado.** | No. |
| **Modelo de IA** (p. ej. `qwen2.5:3b`, ~2 GB) | | No. Nunca se descarga sin tu confirmación. |

Sin Ollama la aplicación abre igual (inicio de sesión, documentos, finanzas...) pero el chat avisará
de que la IA no está disponible.

## Requisitos

- Windows 10 (build 19045 o posterior recomendado) o Windows 11, 64 bits.
- 8 GB de RAM como mínimo (16 GB recomendados si usas modelos de 7B).
- ~5 GB libres: imagen del backend (~300 MB) + modelos (2–5 GB cada uno).
- Virtualización activada en la BIOS/UEFI y WSL 2 (Docker Desktop lo configura al instalarse).

## Pasos

1. **Docker Desktop**: descárgalo de https://www.docker.com/products/docker-desktop/, instálalo,
   reinicia si lo pide y ábrelo una vez hasta que diga *Engine running*.
2. **Ollama** (recomendado): descárgalo de https://ollama.com/download e instálalo. Para tener el
   modelo por defecto, abre Ollama y descarga `qwen2.5:3b` (o el que elijas en la configuración).
   Desde el hito 4 esto se podrá hacer desde NEXARO, siempre con confirmación.
3. **NEXARO AI**: ejecuta `NEXARO AI Setup <versión>.exe`. Elige la carpeta (o deja la propuesta)
   y termina. Crea accesos directos en el Escritorio y en el menú Inicio.
   - El instalador aún **no está firmado**: Windows SmartScreen mostrará "Windows protegió su PC".
     Pulsa *Más información* → *Ejecutar de todas formas* solo si lo descargaste del repositorio
     oficial.
4. Haz doble clic en **NEXARO AI**. La primera vez se construye la imagen del backend: necesita
   Internet y puede tardar varios minutos. Las siguientes veces arranca en segundos.

### Primer administrador

Hoy el primer usuario administrador todavía se crea con un comando (lo resolverá el asistente de
primera ejecución, hito 5). Mientras tanto, con NEXARO abierto, en PowerShell:

```powershell
docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin --confirm-database /data/nexaro.db --email TU_CORREO
```

## Actualizar

Ejecuta el instalador de la versión nueva encima: conserva la configuración (`%APPDATA%\NEXARO AI`)
y los datos (volumen Docker). Si la versión cambia el backend, el primer arranque reconstruye la
imagen (próximo hito: botón "Reconstruir").

## Desinstalar

*Configuración de Windows → Aplicaciones → NEXARO AI → Desinstalar.*

La desinstalación **no borra**:

- `%APPDATA%\NEXARO AI` (configuración y logs). Bórrala a mano si no la quieres.
- El volumen Docker `nexaro-personal-ai_nexaro_data` con tu base de datos ni los modelos de Ollama.
  Para eliminarlos de verdad: Docker Desktop → *Volumes* → elimina el volumen (irreversible: haz
  antes una copia de seguridad).
