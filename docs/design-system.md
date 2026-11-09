# Sistema de diseño NEXARO

Fuente de verdad: `frontend/css/tokens.css`. Los componentes solo usan tokens (`var(--…)`); un test
(`tests/unit/test_design_tokens.py`) rechaza cualquier color fijo fuera de ese fichero y valida el
contraste WCAG 2.1 AA de 30 pares de colores en tema claro y oscuro.

## Principios
1. **Sobrio y funcional.** Sin gradientes, sin sombras llamativas, sin decoración sin función.
2. **Un solo sistema para todos los módulos.** Cada módulo aporta un acento propio, nunca una interfaz distinta.
3. **Nada ficticio.** Ninguna pantalla muestra datos o métricas que no vengan de la API; un botón existe solo si hace algo.
4. **Accesible por diseño.** Teclado, foco visible, contraste AA y etiquetas en todo control.

## Identidad
| Elemento | Especificación |
|---|---|
| Símbolo | Cuadrado redondeado (radio 14/64) en azul acero `#2b5c97` con una «N» geométrica blanca. `frontend/icons/symbol.svg` |
| Logotipo | Símbolo + «NEXARO» en Inter 750, `letter-spacing: .16em`, mayúsculas. Componente `js/components/brand.js` |
| Iconos PWA | `icon-192.png`, `icon-512.png` (esquinas redondeadas) e `icon-maskable-512.png` (sin bordes; la plataforma recorta). Generados desde el mismo símbolo |
| Zona libre | Mínimo la mitad del lado del símbolo alrededor del conjunto |
| Prohibido | Cambiar el color del símbolo, estirarlo, añadir efectos o usar el logotipo sin el símbolo en la cabecera |

## Color
Azul marino (acción y barra lateral), azul acero (acento), blanco y grises neutros. Cada token define
claro y oscuro con `light-dark()`.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--bg` | `#f3f5f9` | `#0a1424` | Fondo de página |
| `--panel` | `#ffffff` | `#101f36` | Tarjetas, tablas, cabecera |
| `--panel-2` | `#e9eef5` | `#172a47` | Cabeceras de tabla, hover |
| `--border` / `--border-input` | `#cbd3df` / `#6b7a90` | `#26405f` / `#7390b3` | Separadores / controles de formulario (≥3:1) |
| `--text` / `--muted` | `#0e1a2b` / `#475569` | `#e8eef7` / `#a5b4c8` | Texto principal / secundario |
| `--primary` | `#12305a` | `#7fa9de` | Botón principal, pestaña activa |
| `--accent` | `#2b5c97` | `#8db4e8` | Enlaces, foco |
| `--sidebar*` | `#0b1f3a` | `#07101f` | Barra lateral (siempre oscura: ancla de marca) |
| `--ok` `--warn` `--danger` (+`-bg`) | ver `tokens.css` | | Estados; siempre con texto, nunca solo color |

### Identidad funcional por módulo
Solo se usa en icono, etiqueta y filete de cabecera; nunca como fondo grande.

| Módulo | Token | Claro |
|---|---|---|
| NEXARO Personal AI | `--module-personal-ai` | `#2b5c97` |
| NEXARO Finance | `--module-finance` | `#1d6b6f` |
| NEXARO Business | `--module-business` | `#4a4f9c` |
| NEXARO Security | `--module-security` | `#8e3a3a` |
| NEXARO Developer | `--module-developer` | `#4f6a1f` |

Un módulo aparece en la navegación **solo cuando tiene funcionalidad real** (ADR-0008). Hoy: Personal AI
y la plataforma (organizaciones, administración).

## Tema
Claro por defecto y oscuro opcional. Tres modos: *Sistema* (sigue `prefers-color-scheme`), *Claro* y
*Oscuro*; se guarda en `localStorage` (`nexaro_theme`) y se aplica con `js/theme-init.js`, un script
clásico bloqueante para evitar el parpadeo. `light-dark()` requiere Chrome 123, Safari 17.5 o Firefox 120.

## Tipografía
Inter variable autoalojada (`/fonts`, licencia OFL-1.1 en `frontend/fonts/OFL-1.1.txt`), solo subconjunto
latino (suficiente para español). Escala: 12 / 13 / 15 / 18 / 24 / 32 px (`--fs-xs … --fs-2xl`). Monoespaciada
del sistema para identificadores y fechas técnicas.

## Espacio y forma
Escala de 4 px (`--space-1 … --space-6`), radios 6 / 10 / 14 px y una única sombra (`--shadow`).

## Componentes
CSS en `frontend/css/components.css`; lógica en `frontend/js/components/`. Todos construyen el DOM con `h()` (sin `innerHTML`).

| Componente | Módulo / clases | Comportamiento |
|---|---|---|
| Botón | `.button`, `.secondary`, `.danger`, `.small` | Alto mínimo 40 px (32 px en `.small`) |
| Campo | `form.js` → `field()` | Etiqueta visible, ayuda enlazada con `aria-describedby`; también `select` |
| Tarjeta | `.card` | Un `h2` por tarjeta |
| Tabla de datos | `table.js` → `dataTable()` | Búsqueda, filtros, orden (`aria-sort`), filas por página y paginación; aviso de resultados con `aria-live`. Cliente: pensada para cientos de filas |
| Estados | `states.js` → `loadingState`, `emptyState`, `errorState` | Siempre con texto; el error ofrece «Reintentar» |
| Avisos | `toast.js` → `toast()` | Región `aria-live`; éxito se cierra a los 5 s, error espera al usuario |
| Confirmación | `dialog.js` → `confirmDialog()` | `<dialog>` modal nativo; el foco inicial es «Cancelar»; Escape cancela |
| Menú de usuario | `user-menu.js` | Botón + panel (`aria-expanded`); Escape y clic fuera cierran; Escape devuelve el foco |
| Marca | `brand.js` | Símbolo + logotipo |
| Pestañas | `.tabs` + `role="tab"` | `aria-selected` |
| Etiqueta de estado | `.badge.ok/.warn/.bad` | Color + texto |
| Apilado | `.stack` | Separación uniforme entre bloques |

### Marco de la aplicación (`js/shell.js`)
Barra lateral oscura (marca, estado del modelo, navegación, hueco para contexto de la vista), cabecera con
título de página y menú de usuario, y contenido. En pantallas de hasta 760 px la barra lateral pasa a **cajón**
con botón de menú, botón de cierre, capa de fondo y cierre con Escape o al navegar. Cada vista fija su título con
`shell.setTitle()`. Hueco previsto para los avisos: `shell.topbarActions`.

## Accesibilidad
- Enlace «Saltar al contenido» como primer elemento enfocable; destino `main#view`.
- Tablas con `caption` y `th scope="col"`; columnas ordenables con botón y `aria-sort`.
- Diálogos y menús: foco inicial seguro, Escape, y devolución del foco.
- Foco visible en todo control (`:focus-visible`, `--focus`, ≥3:1).
- `prefers-reduced-motion` desactiva animaciones y transiciones.
- Contraste AA validado automáticamente para cada par texto/fondo declarado.
- VERIFY: lectores de pantalla (VoiceOver/NVDA) sin probar; solo hay verificación automática y de teclado.

## Cómo añadir un componente
1. Usar únicamente tokens; si falta uno, añadirlo a `tokens.css` en claro **y** oscuro y registrar sus pares en `PAIRS`.
2. Construir el DOM con `h()` (sin `innerHTML`) en `js/components/`.
3. Documentarlo en la tabla anterior.
4. Comprobar claro y oscuro: `BROWSER=1 tests/frontend/run.sh` regenera `docs/design/screenshots/`.

## Capturas de referencia
`docs/design/screenshots/` (generadas por `tests/frontend/browser.mjs` con datos de prueba, no reales):
`d-light-*`, `d-dark-*` (escritorio) y `m-light-*` (móvil, 390 px) para login, chat y administración.
