# Integración Obsidian — NEXARO Personal AI

## Estado inicial
La integración se añade en modo **solo lectura**. NEXARO no crea, edita, renombra ni elimina notas del Vault.

## Configuración
Define `OBSIDIAN_VAULT_PATH` en el entorno del backend con la ruta al Vault de Obsidian.

Ejemplo Windows con Docker Desktop:
```dotenv
OBSIDIAN_VAULT_PATH=C:/Users/TU_USUARIO/Documents/Mrabeh-Knowledge-Base
```

Si el backend corre dentro de Docker, el Vault debe montarse explícitamente como volumen de solo lectura y la variable debe apuntar a la ruta dentro del contenedor. No montes el disco completo ni la carpeta `.obsidian`.

## Endpoints autenticados
- `GET /api/obsidian/status`: estado y cantidad de notas Markdown.
- `GET /api/obsidian/notes?limit=200&offset=0`: listado paginado con título, tags y tamaño.
- `GET /api/obsidian/note/{path}`: lectura de una nota Markdown.
- `GET /api/obsidian/search?q=...`: búsqueda literal simple.

Todos requieren la sesión de NEXARO. La API no admite operaciones de escritura.

## Exclusiones de seguridad
El conector excluye carpetas ocultas y `.obsidian`, `.trash`, `.git`, `node_modules`. Valida que las rutas resueltas permanezcan dentro del Vault y solo permite archivos Markdown.

## Limitaciones de esta primera entrega
- No hay indexación vectorial/RAG todavía.
- No hay sincronización incremental ni file watcher.
- No hay creación o modificación de notas.
- No hay integración MCP.
- La búsqueda es literal y básica.

La siguiente fase deberá conectar este lector al pipeline documental/RAG existente, conservar las rutas y citas, y añadir la interfaz de Knowledge Base.
