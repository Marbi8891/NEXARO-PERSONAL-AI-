# NEXARO — Descripción del producto

## 1. Resumen

NEXARO es una plataforma de IA personal y extensible con enfoque **local-first**. Permite utilizar modelos de lenguaje a través de Ollama y dispone de una arquitectura preparada para integrar proveedores de IA adicionales mediante un AI Gateway.

El backend es un monolito modular en Python/FastAPI. El frontend es HTML, CSS y JavaScript en módulos ES, servido por el backend sin un proceso de compilación.

## 2. Objetivos

- Utilizar IA local con control sobre los datos y el entorno.
- Centralizar el acceso a modelos y proveedores.
- Ofrecer chat, agentes especializados y recuperación de información desde documentos.
- Administrar cuentas, sesiones, organizaciones, permisos y claves API.
- Registrar actividad relevante para auditoría y seguimiento.
- Mantener módulos separados para facilitar evolución y pruebas.

## 3. Usuarios y roles

### Usuario de plataforma
Puede utilizar la aplicación si su cuenta está activa y aprobada. El acceso a la administración de plataforma está reservado al rol administrador.

### Administrador de plataforma
Gestiona cuentas, aprobación, activación, registro público, auditoría, indicadores de seguridad, modelos y uso.

### Miembros de organización
El acceso a recursos organizacionales depende de la pertenencia a la organización y del rol asignado. Los roles documentados incluyen propietario, administrador, miembro y visor; los permisos concretos se aplican mediante controles de autorización.

### Consumidores de API
Aplicaciones externas pueden utilizar claves de API asociadas a una organización y con scopes específicos. La clave se muestra completa únicamente al crearla.

## 4. Funcionalidades implementadas

| Área | Funcionalidad |
|---|---|
| Cuenta y autenticación | Registro (cerrado por defecto), login, sesiones, logout y aprobación |
| Chat | Conversaciones, historial, respuesta normal y streaming |
| Agentes | Agentes especializados: general, developer, security, research, productivity, data y tutor |
| AI Gateway | Políticas, proveedores, respaldo, circuit breakers y registro de uso |
| Modelos | Ollama; integraciones de gateway con Bedrock y SageMaker |
| Organizaciones | Creación, miembros, roles y permisos |
| Developer | Claves API, scopes, endpoint de chat, lectura de conversaciones y métricas por clave |
| Documentos | Texto y PDF con texto; búsqueda BM25 y preguntas con fuentes |
| Finanzas | Gestión de gastos, resumen mensual y exportación CSV |
| Administración | Usuarios, registro, auditoría, seguridad, modelos y uso |
| Interfaz | Dashboard, tema claro/oscuro, notificaciones, PWA y sistema de diseño |
| Seguridad | Sesiones revocables, hashes, controles de origen, cabeceras, limitación de solicitudes y auditoría |

## 5. Funcionalidades parciales o pendientes

- **PostgreSQL:** existe DDL y validación, pero la aplicación actual opera con SQLite.
- **Agentes y tareas:** los agentes están implementados en el flujo de chat; tablas de tareas y ejecuciones están preparadas, pero no hay API completa de tareas.
- **Embeddings:** esquema disponible; la búsqueda documental actual utiliza BM25, no embeddings.
- **Finance y Business:** identidad de marca, sin módulos funcionales completos adicionales.
- **Selección de modelo:** el modelo se configura mediante entorno; no existe selección dinámica de modelo desde la interfaz.
- **AWS:** Terraform está escrito, pero no validado ni aplicado. La infraestructura cloud está aparcada y no debe crearse sin autorización expresa.
- **Conversaciones:** el chat web es personal. La asociación a organización se usa en el flujo de claves de API.

## 6. Límites conocidos

NEXARO está diseñado para una instancia de aplicación y SQLite en el estado actual. SQLite utiliza WAL y admite un escritor a la vez. Los limitadores de solicitudes son en memoria del proceso, por lo que no se comparten entre réplicas.

Las integraciones cloud de IA no deben considerarse verificadas con servicios reales: el repositorio documenta pruebas con dobles para AWS.

## 7. Roadmap documental y de producto

La evolución debe priorizar estabilidad, pruebas de seguridad, integración coherente de módulos y documentación de las funciones que estén realmente disponibles. Las funcionalidades que no tengan API o flujo de usuario terminado deben permanecer identificadas como pendientes, no presentarse como capacidades disponibles.
