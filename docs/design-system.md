# NEXARO Visual Identity System

## Brand direction

NEXARO Personal AI is a private, local-first AI assistant. The identity is built around user control,
a calm technical character and clear product hierarchy. It should feel like a dependable desktop
product, not a generic AI chat skin.

**Brand line:** Your intelligence. Your data. Your control.

## Logo

The primary lockup combines the geometric N mark with the NEXARO wordmark and PERSONAL AI descriptor.
The mark uses a deep-navy rounded square, a white geometric N and a small teal signal detail.
Use the SVG in `frontend/icons/symbol.svg` as the only source of truth for the symbol.

Do not redraw, distort, rotate, add a glow, or place the symbol on a low-contrast background.
The minimum clear space around the symbol is one quarter of its width. The wordmark is uppercase
Inter at weight 780 with moderate tracking. The descriptor is smaller and more widely tracked.

## Colour palette

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--bg` | `#edf2f7` | `#0b1220` | App canvas |
| `--panel` | `#ffffff` | `#111d2d` | Cards and surfaces |
| `--panel-2` | `#e3eaf2` | `#17263a` | Secondary surfaces |
| `--text` | `#101b2b` | `#edf3fa` | Main text |
| `--muted` | `#46576c` | `#a6b5c8` | Secondary text |
| `--primary` | `#126e70` | `#63d5d0` | Primary action |
| `--accent` | `#315b91` | `#8aa7e8` | Links and secondary emphasis |
| `--sidebar` | `#0b1220` | `#070d17` | Navigation shell |

Semantic state colours remain separate from brand colours. Module accents are used only for small markers,
labels and icons, not large background areas. All colour values live in `frontend/css/tokens.css`.

## Typography and shape

Inter variable is the product typeface, already self-hosted in `frontend/fonts`. System monospace is
reserved for technical identifiers and code. The existing spacing scale is retained. Surfaces use
12px default and 17px large radii; shadows remain restrained.

## UI principles

1. Dark theme is the primary brand expression; light theme remains fully supported.
2. Use teal for actions, focus and live/connected signals. Do not use it as body text on light surfaces.
3. Maintain clear visual hierarchy and restrained density.
4. Never fabricate operational data, model status or activity.
5. Keep keyboard navigation, reduced-motion support and WCAG AA contrast requirements.
6. The identity refresh must not change API contracts, routing, authentication or product behaviour.

## Implementation

- Tokens: `frontend/css/tokens.css`
- Symbol: `frontend/icons/symbol.svg`
- Lockup: `frontend/js/components/brand.js`
- App metadata: `frontend/index.html` and `frontend/manifest.webmanifest`

No framework migration or additional runtime dependency is required.
