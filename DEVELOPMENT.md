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
- Los tests de PostgreSQL usan `pgserver` (PostgreSQL embebido): no necesitas instalar nada. En CI son obligatorios.
- No se modifican tests existentes para hacerlos pasar.
- `pre-commit install` activa ruff y gitleaks.
- Nunca ejecutes `docker compose down -v` ni borres el volumen `nexaro-personal-ai_nexaro_data`.

## Frontend

No hay paso de compilación: edita `frontend/` y recarga. Pruebas:

```bash
bash tests/frontend/run.sh            # E2E con jsdom contra la API real (no necesita navegador)
BROWSER=1 bash tests/frontend/run.sh  # además, Chromium real: comportamiento, teclado, móvil y capturas
```

La primera vez ejecuta `npm install` en `tests/frontend` (jsdom; con `BROWSER=1`, Chromium ≈70 MB). Las
capturas de `docs/design/screenshots/` se regeneran con `BROWSER=1` y usan datos de prueba. Antes de
confirmar un cambio de interfaz: `ruff`, `mypy`, `pytest` y la E2E.
