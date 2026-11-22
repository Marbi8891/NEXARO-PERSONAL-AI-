# ADR-0008: Sistema de diseño propio con tokens, tema claro/oscuro y módulos solo cuando existen

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
Se pide apariencia de producto SaaS comercial con identidad propia (azul marino, azul acero, blanco y
grises), cinco módulos de marca (Personal AI, Finance, Business, Security, Developer), y la regla de
no mostrar botones sin función ni datos ficticios. Hoy solo existe backend para Personal AI y la
plataforma. La CSP (ADR-0007) prohíbe estilos en línea y recursos de terceros.

## Opciones
**Módulos:**
- A. Solo en la documentación y los tokens; navegación con lo que funciona. *(elegida para el marco)*
- B. Entradas «Próximamente» desactivadas: son placeholders visibles y contradicen la regla.
- C. Construir primero un módulo real. *(elegida además, fase 13; el módulo se decide con el usuario)*

**Tema:** claro por defecto + oscuro opcional *(elegida)*; solo claro; solo oscuro.
**Fuente:** Inter autoalojada *(elegida)* frente a fuentes del sistema (apariencia variable) o CDN (bloqueado por CSP y privacidad).
**Color:** `light-dark()` con una única definición por token *(elegida)* frente a duplicar bloques claro/oscuro.

## Decisión
Tokens en `frontend/css/tokens.css` como única fuente de verdad, validados con tests de contraste AA y
de «sin colores fuera de tokens». Barra lateral siempre oscura. Un módulo entra en la navegación solo cuando
tiene API y pantalla reales. Notificaciones: avisos derivados de datos reales (fase 12), sin tabla nueva.

## Trade-offs
- `light-dark()` exige navegadores de 2024 en adelante.
- Subconjunto latino de Inter: no cubre alfabetos no latinos (el árabe, idioma nativo del usuario, no está cubierto; VERIFY si se necesita).
- Sin entradas «Próximamente» la suite parece más pequeña de lo que se presentará comercialmente.

## Consecuencias
- Añadir un color exige registrar sus pares de contraste.
- El símbolo y los iconos PWA se generan desde el mismo trazado; cambiarlo implica regenerar los PNG.
- Los controles de tema y las capturas se verifican en Chromium real, no solo en jsdom.
