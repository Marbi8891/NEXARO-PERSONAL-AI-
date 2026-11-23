# NEXARO Enterprise Design System

## Positioning

NEXARO is an enterprise software platform for private AI infrastructure. Its visual identity should
communicate operational reliability, privacy, control and technical competence. It is designed for
organisations, IT teams and security-conscious users.

**Brand line:** Intelligence under your control.

**Product descriptor:** Private AI infrastructure for organisations.

## Logo

The primary lockup combines a geometric N monogram, the NEXARO wordmark and the descriptor
INTELLIGENCE PLATFORM. Use `frontend/icons/symbol.svg` as the canonical mark.

The mark uses a square-cornered deep-navy field, a white N and a restrained steel-blue signal detail.
Do not add gradients, glow, shadows, decorative circuit patterns or rounded app-store styling.
Preserve proportions and clear space equal to at least one quarter of the mark width.

## Corporate palette

| Token | Light | Dark | Purpose |
|---|---|---|---|
| `--bg` | `#f3f5f8` | `#101a2b` | Workspace |
| `--panel` | `#ffffff` | `#172438` | Cards and primary surfaces |
| `--panel-2` | `#e9edf2` | `#202f43` | Secondary surfaces |
| `--text` | `#172334` | `#edf1f6` | Primary text |
| `--muted` | `#4c5b6d` | `#aeb9c7` | Secondary text |
| `--primary` | `#344f70` | `#91a8c4` | Primary action |
| `--accent` | `#43658e` | `#a0b5ce` | Links and emphasis |
| `--sidebar` | `#101a2b` | `#0b1422` | Navigation shell |

State colours communicate status only. Module colours are muted, reserved for small identifiers and
never used as large decorative blocks. All palette definitions remain in `frontend/css/tokens.css`.

## Typography and layout

Inter remains the main typeface. System monospace is used for code, IDs and technical values.
The layout uses compact enterprise spacing, restrained 5/8/11px radii, subtle borders and low-elevation
shadows. Avoid oversized promotional headings inside the operational application.

## Interface principles

1. Prefer neutral surfaces and clear information hierarchy.
2. Use steel blue sparingly for actions and selected states.
3. Keep status colours semantic and consistent.
4. Use real API data only; do not introduce decorative or simulated metrics.
5. Preserve keyboard navigation, reduced motion and WCAG AA contrast requirements.
6. The identity refresh does not change API contracts, routing, authentication, data model or deployment.

## Brand family

NEXARO is the master brand. Product names retain the same wordmark and symbol, with a descriptor and a restrained accent. Current naming and governance rules are documented in [Brand Architecture](brand-architecture.md). Future product identities must not imply functionality that has not shipped.

## Implementation

- Tokens: `frontend/css/tokens.css`
- Symbol: `frontend/icons/symbol.svg`
- Wordmark lockup: `frontend/js/components/brand.js`
- Browser metadata: `frontend/index.html`
- PWA metadata: `frontend/manifest.webmanifest`

No new runtime dependencies or framework migration are introduced.
