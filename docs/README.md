# Documentación de NEXARO

Esta carpeta reúne la documentación funcional, de uso y operación del proyecto.

## Para empezar

- [Descripción del producto](PRODUCT.md): qué es NEXARO, objetivos, usuarios y alcance actual.
- [Guía de usuario](USER_GUIDE.md): uso de la interfaz y flujos principales.
- [Arquitectura técnica](../ARCHITECTURE.md): estructura del sistema y reglas de dependencias.
- [API](../API.md): rutas HTTP, autenticación, permisos, formatos y errores.
- [Desarrollo](../DEVELOPMENT.md): instalación del entorno, pruebas y tareas de desarrollo.
- [Despliegue y operación](OPERATIONS.md): Docker, configuración, copias de seguridad y resolución de problemas.
- [Seguridad](../SECURITY.md): configuración segura y controles de la aplicación.
- [Sistema de diseño](design-system.md): componentes, estilos y reglas visuales.
- [Decisiones de arquitectura](decisions/): ADRs que explican decisiones técnicas.

## Estado y alcance

La documentación describe el estado que figura en el repositorio. Las funcionalidades marcadas como «implementadas» en README o API no se consideran certificadas en un despliegue concreto hasta que se ejecuten pruebas allí.

## Convenciones

- Las rutas y comandos se muestran tal como están documentados en el proyecto.
- Los secretos, cookies y claves reales nunca deben copiarse en tickets, capturas ni documentación.
- La documentación de API se mantiene en `API.md`; esta carpeta evita duplicar el inventario completo de endpoints.
