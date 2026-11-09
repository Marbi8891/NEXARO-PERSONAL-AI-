# Informe: calidad profesional de NEXARO (fases F10–F14)

Fecha: 2026-11-09 · Rama: `feature/nexaro-design-system` (local, sin publicar) · Base: `refactor/nexaro-platform`

Este informe separa lo **terminado y verificado**, lo **terminado pero no verificado en este entorno** y lo
**pendiente**. Nada de lo que figura como verificado depende de una afirmación sin ejecutar.

## 1. Resultado por fase

| Fase | Entregable | Commit |
|---|---|---|
| F10 | Identidad visual, tokens claro/oscuro, Inter autoalojada, símbolo y logotipo, iconos PWA, ADR-0008 | `38821ec` |
| F11 | Marco (barra lateral, cabecera, menú de usuario, perfil), tabla, formularios, estados, avisos, confirmación, cajón móvil | `74397a2` |
| F12 | Panel con datos reales, avisos derivados, campana en la cabecera, gráfico accesible | `f80d5e9` |
| F13 | Módulo Developer: claves de API por organización, `POST /api/v1/chat`, uso por clave, migración 3, ADR-0009 | `aad4259` |
| F14 | Documentación (API, arquitectura, despliegue, seguridad, desarrollo) y este informe | (siguiente commit) |

## 2. Requisitos del encargo

| Requisito | Estado | Evidencia / límite |
|---|---|---|
| Identidad visual propia (azul marino, azul acero, blanco, grises; logotipo tipográfico + símbolo geométrico) | Hecho | `docs/design-system.md`, `frontend/css/tokens.css`, `frontend/icons/` |
| Sin efectos ni degradados innecesarios | Hecho | Un test impide colores fuera de `tokens.css` |
| Tipografía moderna y legible | Hecho (límite) | Inter autoalojada, subconjunto latino: **no cubre árabe** (VERIFY si hace falta) |
| Tema claro por defecto y oscuro opcional | Hecho | Selector en Perfil; sigue al sistema si se elige «Sistema» |
| Panel profesional | Hecho | `#/dashboard`: solo cifras reales; lo que no existe es 0 o vacío |
| Barra lateral con módulos | Hecho | Solo entradas con funcionalidad real |
| Cabecera con usuario, perfil y avisos | Hecho | Avisos derivados del estado real; no hay avisos de relleno |
| Responsive escritorio / tablet / móvil | **Parcial** | Verificado a 1280 px y 390 px (sin desbordamiento horizontal). **Tablet (≈768 px) no se ha capturado ni probado explícitamente**; el cajón se activa a ≤760 px |
| Formularios coherentes | Hecho | `components/form.js` (etiqueta visible, ayuda enlazada) |
| Tablas con búsqueda, filtro, orden y paginación | Hecho (límite) | En el cliente: pensada para cientos de filas, no para miles (paginación en servidor pendiente) |
| Gráficos solo cuando informan | Hecho | Dos gráficos de barras diarias, con resumen textual y tabla de datos |
| Estados de carga, error, confirmación y vacío | Hecho | `components/states.js`, `dialog.js`, `toast.js` |
| Accesibilidad por teclado, contraste y etiquetas | Hecho (límite) | Contraste AA validado por test; teclado probado en Chromium; **lectores de pantalla (VoiceOver/NVDA) no probados** |
| Módulos con identidad funcional propia | **Parcial** | Personal AI y Developer son reales. **Finance, Business y Security no existen** (solo acento de marca; no aparecen en la navegación a propósito, ADR-0008) |
| Sin interfaces de demostración, botones sin función ni métricas inventadas | Hecho | Los datos de ejemplo solo existen en los tests |
| Errores comprensibles, pocos pasos, navegación predecible | Hecho | Mensajes en español sin detalles internos; rutas por hash con guardas |
| Stack: FastAPI/Python, HTML/CSS/ES Modules, Docker Compose, sin React/Next | Hecho | Sin paso de compilación |
| Componentes, servicios, lógica y estilos separados | Hecho | Ver `ARCHITECTURE.md` (sección Frontend) |
| API y arquitectura documentadas | Hecho | `API.md`, `ARCHITECTURE.md` |
| Pruebas automatizadas | Hecho | Sección 3 |
| Controles de seguridad | Hecho (límites) | `SECURITY.md` |
| Ollama local y proveedores en la nube futuros | Hecho (límite) | Ollama real; Bedrock/SageMaker implementados y probados **solo con dobles** |
| Guía de instalación y despliegue | Hecho (no ejecutada) | `DEPLOYMENT.md`; ver sección 4 |

## 3. Verificación ejecutada (2026-11-09)

- `ruff format --check`, `ruff check`, `mypy .` (58 archivos): limpios.
- `pytest` con PostgreSQL embebido obligatorio: **280 pasan**; cobertura total **89 %** (el CLI
  `bootstrap_admin` se prueba por subproceso y no cuenta).
- E2E con jsdom contra la API real: **25 comprobaciones**.
- Chromium real (`BROWSER=1`): escenarios de flujo (claro, oscuro, móvil), menú y tema, tabla y confirmación,
  panel y campana, panel móvil sin desbordamiento, Developer, cajón y teclado.
- Migración 3 aplicada sobre una base ya en la versión 2 con filas de uso: se conservan, es idempotente.
- Los tests existentes no se han modificado para hacerlos pasar; los cambios en E2E añaden comprobaciones.

## 4. No verificado en este entorno

El entorno de desarrollo no tiene Docker ni acceso a AWS. Por tanto **no está verificado**: construir la imagen y
`docker compose up`, el job de CI (GitHub Actions), `terraform validate/plan` (y todo AWS, aparcado por
decisión tuya), la aplicación ejecutando sobre PostgreSQL (solo el DDL), Bedrock y SageMaker reales, Firefox y
Safari (solo Chromium; `light-dark()` exige Chrome 123 / Safari 17.5 / Firefox 120 o posteriores), lectores de
pantalla, tablet, y la migración 3 sobre **tu base viva** (se aplicará al reconstruir el backend).
También UNKNOWN: que `client_ip` sea la IP real tras un proxy.

## 5. Pendiente

1. Finance, Business y Security (decidir cuál y con qué datos reales; ver valor/coste antes de construir).
2. Permisos por clave de API (scopes) y más endpoints públicos versionados.
3. Limitador de intentos compartido entre instancias (hoy en memoria del proceso).
4. Paginación en servidor para tablas grandes; descartar avisos; elegir «Panel» como entrada por defecto
   (hoy es el chat, para no alterar el flujo probado).
5. Fuente con cobertura árabe si se necesita interfaz en árabe.
6. Ejecutar en Docker y PostgreSQL cuando se retome AWS/producción (ADR-0005, ADR-0006).

## 6. Siguiente paso tuyo (en tu Mac, no ejecutado por mí)

```bash
git remote add origin https://github.com/Marbi8891/NEXARO-PERSONAL-AI-.git   # si aún no existe
git push -u origin refactor/nexaro-platform feature/nexaro-design-system        # sin main, sin --force
scripts/rebuild_backend.sh        # nunca `down -v`; conserva el volumen y hace copia previa
```

Después, inicia sesión y comprueba el panel y Developer. Si la migración 3 fallase, el arranque aborta sin
dejar estado parcial y puedes volver a la imagen `rollback-<fecha>` o restaurar la copia previa.
