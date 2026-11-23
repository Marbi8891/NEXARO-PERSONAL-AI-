# Brand identity

← [Documentation home](../README.md) · Related: [Brand architecture](brand-architecture.md) ·
[Design system](design-system.md) · [Assets](../assets/README.md)

## Positioning

| | |
|---|---|
| **Name** | NEXARO, always uppercase |
| **Category** | Self-hosted AI workspace and agent platform |
| **Tagline** | Private AI. Intelligent Agents. Your Infrastructure. |
| **Brand promise** (in-app) | Intelligence under your control. |
| **One-liner** | NEXARO is a self-hosted AI workspace that brings AI models, agents, tools, workflows, knowledge and security controls into a unified environment. |

## Voice

Precise, calm, technical, transparent. State what the software does today; label planned work as
planned. No superlatives, no "revolutionary", no unverified performance claims. Prefer a table or a
command over an adjective.

## Logo

The NEXARO monogram (an "N" in a rounded square) plus the letter-spaced wordmark, as already used in
the application's sidebar. Files are in [`docs/assets/brand/`](../assets/brand/).

- Minimum clear space: the height of the "N" stroke on every side.
- Do not recolour, outline, rotate, add effects or place the light logo on a light background.
- Product names follow `NEXARO + category` (e.g. NEXARO Personal AI); see
  [brand architecture](brand-architecture.md).

## Colour

### Repository and documentation palette

Used for the logo, README and documentation graphics.

| Token | Hex | Use |
|---|---|---|
| Primary blue | `#2563EB` | Monogram, links, single highlights |
| Deep navy | `#0B1220` | Wordmark on light, dark backgrounds |
| Dark surface | `#111827` | Dark panels |
| Slate | `#64748B` | Secondary text |
| Light background | `#F8FAFC` | Light backgrounds, wordmark on dark |
| Success | `#10B981` | Positive states only |
| Warning | `#F59E0B` | Warning states only |

### Application palette

The UI uses the conservative enterprise palette defined in
[`frontend/css/tokens.css`](../../frontend/css/tokens.css) (navy sidebar `#101A2B`, steel-blue actions
`#344F70`, with light and dark themes). It is the single source of UI colour; `tests/unit/test_design_tokens.py`
checks WCAG 2.1 AA contrast in both themes and fails on hard-coded colours outside the tokens. Both palettes share the deep-navy base; the repository palette
adds a brighter blue for small marks only.

Rules: colour carries meaning (state or brand), never decoration. Use at most one accent per graphic.
No gradients, no glow effects, no emoji as icons.

## Typography

**Inter** (variable, self-hosted under the SIL Open Font License in `frontend/fonts/`) for UI and
graphics; the system monospace stack for code. No additional web fonts.
