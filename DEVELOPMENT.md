# Desarrollo

Python 3.12 (CI y Docker). Las importaciones funcionan sin instalar el proyecto, con
`PYTHONPATH=.:packages:apps/api` (ADR-0002); `pyproject.toml` solo configura herramientas.

```bash
python3 -m venv .venv && . .venv/bin/activate
make install
make check
```

- Dependencias: `requirements/{base,aws,dev}.txt`, con versiones fijadas.
- Tests: `tests/unit`, `tests/integration`, `tests/security`. Umbral de cobertura 80 %
  (`pyproject.toml`); la cobertura se mide, no se fuerza.
- No se modifican tests existentes para hacerlos pasar.
- `pre-commit install` activa ruff y gitleaks.
- Nunca ejecutes `docker compose down -v` ni borres el volumen `nexaro-personal-ai_nexaro_data`.
