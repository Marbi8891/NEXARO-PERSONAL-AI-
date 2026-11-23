# NEXARO Brand Architecture

## Master brand

**NEXARO** is the master brand for private AI infrastructure and intelligent enterprise software.

- Brand promise: Intelligence under your control.
- Corporate descriptor: Intelligence Platform.
- Commercial description: Private AI infrastructure for organisations.
- Voice: precise, calm, technical, transparent. Avoid hype and unsupported claims.

The master brand remains visually consistent across products. Product names follow the pattern
`NEXARO + product category`, not separate unrelated brands.

## Product family

| Product | Name | Role | Accent |
|---|---|---|---|
| Personal AI | **NEXARO Personal AI** | Private assistant and local AI workspace | Steel blue |
| Security | **NEXARO Security** | Security posture, risk and findings management | Muted burgundy |
| Developer | **NEXARO Developer** | API, integrations and developer services | Sage |
| Business | **NEXARO Business** | Business workflows and operational tools | Slate indigo |
| Finance | **NEXARO Finance** | Financial tracking and analysis | Muted teal |

These names and accents establish the brand architecture only. A product must not be represented as
implemented or available until the corresponding functionality exists.

## Logo system

Every product uses the same NEXARO monogram and wordmark. A product descriptor may appear beneath
the wordmark or beside it in the same typographic style:

- NEXARO / PERSONAL AI
- NEXARO / SECURITY
- NEXARO / DEVELOPER
- NEXARO / BUSINESS
- NEXARO / FINANCE

Do not create independent product symbols at this stage. Product differentiation is handled by the
descriptor and a restrained accent colour.

## Colour governance

Corporate surfaces, navigation, typography and controls use the master palette in
`frontend/css/tokens.css`. Product accents are reserved for small markers, icons, labels, charts
and section identifiers.

- Personal AI: steel blue `#43658e`
- Security: muted burgundy `#9a5156`
- Developer: sage `#687b50`
- Business: slate indigo `#5b6388`
- Finance: muted teal `#36766b`

Do not let product accents replace the neutral corporate surface palette. Keep state colours
(success, warning, danger) independent from brand colours.

## Naming and UI rules

1. The master brand is always written **NEXARO**, uppercase.
2. Product descriptors use title case in UI labels, uppercase only in logo lockups.
3. Use `NEXARO Personal AI`, not `NexaroAI`, as the product name in the platform.
4. Do not use “Enterprise” as a product name. It describes the target market or edition.
5. Product family names are reserved until the functionality is shipped.
6. Do not add fake dashboards, statistics, feature cards or product navigation for future products.
7. Keep a single design system and shared component library.

## Roadmap use

This architecture makes it possible to add new NEXARO products without redesigning the identity.
When a product ships, it may receive its own descriptor, accent token and documentation page,
but it must retain the NEXARO master mark and corporate layout.
