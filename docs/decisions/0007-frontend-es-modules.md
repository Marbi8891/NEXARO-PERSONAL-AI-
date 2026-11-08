# ADR-0007: Frontend con ES Modules nativos, sin framework ni build, bajo CSP estricta

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto
El frontend original era un único `index.html` de ~730 líneas con script y estilos en línea. Se
exige mantener HTML/CSS/ES Modules (sin React/Next.js), añadir registro, administración y
organizaciones, ser responsive y PWA, y no debilitar la seguridad.

## Opciones
- **A. Mantener el fichero único y ampliarlo.** Inmanejable y obliga a `'unsafe-inline'` en la CSP.
- **B. ES Modules nativos + CSS en ficheros + router por hash, sin build.** Sin dependencias ni
  paso de compilación; permite CSP sin `'unsafe-inline'`.
- **C. Framework con bundler.** Prohibido por el requisito y añade cadena de herramientas.

## Decisión
**B.** `frontend/js/` (`api`, `dom`, `state`, `router`, `shell`, `views/*`) y `frontend/css/`
(`base`, `layout`, `components`). El DOM se construye con `h()` usando solo nodos de texto: no se
usa `innerHTML` ni equivalentes (un test lo prohíbe). Router por hash: no requiere reglas de
servidor. La API aplica la CSP `script-src 'self'; style-src 'self'` salvo en `/docs` fuera de
producción. Los permisos se imponen siempre en el servidor; las guardas del cliente son solo UX.

## Trade-offs
- Sin tipado ni componentes reutilizables más allá de `h()`; aceptable con 5 vistas.
- Hash en la URL en lugar de rutas limpias.
- Service worker "red primero": la PWA es instalable pero no funciona sin conexión (la app depende
  de la API).

## Consecuencias
- Documentos, agentes, automatizaciones y configuración de modelos **no tienen pantalla**: solo
  existe su esquema, no su API. No se crean pantallas vacías.
- Pruebas: `tests/security/test_frontend_policy.py` (sin inline/`innerHTML`, CSP servida) y
  `tests/frontend/run.sh` (jsdom contra la API real; requiere Node, no se ejecuta con `pytest`).
- VERIFY: instalabilidad PWA y comportamiento en navegador real (solo se probó con jsdom).
