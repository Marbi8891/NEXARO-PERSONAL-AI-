# ADR-0001 — Monolito modular

- **Estado:** Aceptada
- **Fecha:** 2026-11-08

## Contexto
NEXARO Personal AI es hoy un único proceso FastAPI + SQLite. La visión incluye cinco productos sobre un núcleo común (NEXARO Core), IA local y cloud, y despliegues privados. Un solo desarrollador mantiene el proyecto.

## Opciones
- **A. Microservicios por producto.** Aislamiento fuerte; coste operativo y de coordinación desproporcionado, contratos de red prematuros.
- **B. Monolito sin estructura.** Rápido hoy, ilegible mañana; los productos acabarían acoplados al núcleo.
- **C. Monolito modular.** Un proceso y un despliegue, con límites de módulo explícitos y comprobables.

## Decisión
**C.** Un único proceso desplegable. Reglas de dependencia, aplicadas por tests (`tests/unit/test_architecture.py`):

1. `packages/*` (Core, AI Gateway…) **no importan** de `products/*` ni de `apps/*`.
2. `products/*` importan de `packages/*`, nunca entre productos.
3. `apps/*` ensamblan: routers HTTP finos que llaman a servicios.
4. Dominio y aplicación no conocen FastAPI; la infraestructura (SQLite, Ollama, AWS) se inyecta.

## Razón
"Complexity must be earned": cada módulo extraíble a servicio el día que una métrica real lo exija (carga, equipo, aislamiento), sin reescribir, porque los límites ya existen.

## Trade-offs
Un fallo grave afecta a todo el proceso; el escalado es por réplica completa, no por módulo.

## Consecuencias
Se crean solo los módulos con implementación real. Los productos Finance, Business, Security y Developer **no** tienen carpeta hasta que exista código que la justifique.
