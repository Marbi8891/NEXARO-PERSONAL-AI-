# ADR-0002 — Estructura Python y dependencias

- **Estado:** Aceptada
- **Fecha:** 2026-11-08

## Contexto
El objetivo pide `apps/`, `packages/` y `products/`. Python necesita raíces de importación claras y un Docker reproducible.

## Opciones
- **A. Paquete único instalable con `pyproject` y layout `src/`.** Estándar, pero obliga a un único árbol y no refleja la separación pedida.
- **B. Varios paquetes instalables.** Máximo aislamiento; mucho andamiaje (un `pyproject` por paquete) para un solo equipo.
- **C. Raíces de importación (`packages`, `apps/api`, repo) sin instalar; dependencias en `requirements/`.**

## Decisión
**C.** `pyproject.toml` contiene solo configuración de herramientas (pytest, ruff, mypy, coverage). Dependencias fijadas en `requirements/{base,aws,dev}.txt`. En Docker, `PYTHONPATH=/app:/app/packages:/app/apps/api`.

## Razón
Mínimo andamiaje que cumple la estructura pedida; el build de Docker es determinista (versiones fijadas) y la capa de dependencias se cachea.

## Trade-offs
No se puede `pip install nexaro`. Si algún día un paquete se publica, se le añadirá su propio `pyproject` (migración mecánica).

## Consecuencias
Las dependencias de AWS (`boto3`) son opcionales: el contenedor local no las instala si no se usan.
