# Guía de usuario

Esta guía describe los flujos de uso de NEXARO que constan en la documentación del repositorio.

## 1. Acceso a la aplicación

En el despliegue local Docker, abre:

`http://127.0.0.1:8001`

El registro público está cerrado por defecto. No existe un administrador inicial automáticamente.

Para preparar el primer administrador, desde el contenedor backend ejecuta el comando de bootstrap descrito en README:

```bash
docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin \
  --confirm-database /data/nexaro.db --email TU_CORREO
```

Después, inicia sesión con las credenciales que establezca el procedimiento de bootstrap.

## 2. Cuenta y sesión

- Inicia sesión con tu cuenta aprobada y activa.
- Utiliza la opción de cerrar sesión cuando termines.
- La sesión se revoca en el servidor al cerrar sesión.
- Las sesiones de usuarios rechazados o desactivados se revocan desde la administración.

No compartas cookies de sesión ni capturas que las contengan.

## 3. Chat

El chat permite enviar mensajes al modelo configurado, continuar conversaciones existentes y conservar historial.

El flujo de chat admite:
- Mensaje nuevo.
- Continuación de una conversación.
- Respuesta en streaming.
- Selección de agente.
- Consulta de documentos de una organización cuando el agente dispone de la herramienta documental y el usuario tiene permiso.

La aplicación utiliza el modelo configurado en el servidor. La selección de modelo desde la interfaz no está implementada en el estado documentado.

## 4. Agentes

Los agentes disponibles documentados son:

- `general`: asistente general.
- `developer`: tareas de desarrollo.
- `security`: seguridad.
- `research`: investigación.
- `productivity`: productividad.
- `data`: análisis y trabajo con datos.
- `tutor`: aprendizaje y explicación.

Los agentes pueden tener herramientas permitidas. Actualmente la herramienta documentada es la consulta de documentos. El acceso a una herramienta se controla por agente y por permisos del usuario; los usos y denegaciones quedan registrados como eventos de auditoría sin guardar el contenido de la herramienta.

## 5. Documentos y búsqueda

Los documentos se gestionan dentro de una organización.

Formatos admitidos:
- Texto enviado mediante API.
- PDF con texto seleccionable.

Los PDFs escaneados sin capa de texto no admiten OCR en la versión actual.

El flujo de trabajo:
1. Selecciona una organización.
2. Añade un documento.
3. Comprueba que aparece en la lista.
4. Usa la búsqueda para encontrar fragmentos relevantes.
5. Formula una pregunta al sistema documental.

La búsqueda lexical utiliza BM25. Las respuestas se acompañan de fuentes. Si no encuentra fragmentos relevantes, el sistema no consulta al modelo y devuelve un mensaje de ausencia de información.

Límites documentados:
- 200.000 caracteres por documento.
- Máximo de 100 documentos por organización.
- PDF: máximo 300 páginas y 200.000 caracteres.
- Tamaño de petición PDF por defecto: 2 MiB.

## 6. Organizaciones y miembros

Las organizaciones agrupan recursos y usuarios. La lista muestra las organizaciones de las que el usuario es miembro y su rol.

Los roles y permisos limitan operaciones como:
- Consultar miembros.
- Gestionar miembros.
- Gestionar claves de API.
- Consultar uso.
- Leer o escribir documentos.
- Gestionar gastos.

La creación de organizaciones está restringida al administrador de plataforma en el comportamiento documentado.

## 7. Developer: claves de API

1. Accede a una organización donde tengas permiso de gestión de claves.
2. Crea una clave con nombre, expiración y scopes.
3. Copia y guarda el secreto en un gestor seguro: se muestra una sola vez.
4. Utiliza la clave mediante `Authorization: Bearer`.
5. Revoca las claves que ya no necesites.

Scopes documentados:
- `chat:write`
- `conversations:read`

La API aplica un límite de 60 solicitudes por minuto por clave, configurable mediante entorno. No incluyas claves en repositorios, capturas o logs.

Ejemplo usando una variable de entorno para no escribir el token directamente en el comando:

```bash
export NEXARO_API_TOKEN="your-local-token"

curl -X POST http://127.0.0.1:8001/api/v1/chat \
  -H "Authorization: Bearer ${NEXARO_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hola"}'
```

## 8. Finanzas: gastos

El módulo de gastos permite registrar, consultar, modificar y eliminar gastos, obtener un resumen mensual y exportar CSV.

El acceso está limitado a propietario y administrador de organización. Los importes se almacenan en céntimos; el importe incluye IVA y el campo IVA representa la parte correspondiente.

## 9. Administración

Solo administradores de plataforma pueden acceder a las funciones de administración documentadas:

- Listar y crear usuarios.
- Aprobar o rechazar solicitudes.
- Activar o desactivar cuentas.
- Abrir o cerrar el registro público.
- Consultar auditoría.
- Consultar resumen de seguridad.
- Revisar modelos y rutas del gateway.
- Consultar uso y métricas de inferencia.

La aplicación protege al último administrador y evita que un administrador se desactive o rechace a sí mismo en operaciones restringidas.

## 10. Notificaciones

Los avisos se derivan del estado actual y no se guardan como registros independientes. Incluyen disponibilidad del modelo y, para administradores, solicitudes pendientes, intentos fallidos y estado del registro público.

## 11. Privacidad y uso responsable

- No introduzcas datos personales innecesarios en prompts.
- Trata las respuestas de IA como contenido que debe verificarse.
- Los documentos son contexto, no instrucciones confiables para el modelo.
- No cargues documentos que no tengas derecho a procesar.
- Protege las claves API y las credenciales.
