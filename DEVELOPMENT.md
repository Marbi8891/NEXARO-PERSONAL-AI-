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

## Evaluación de calidad del modelo

`scripts/quality_eval.py` mide la **calidad** de las respuestas; `scripts/ollama_benchmark.py` mide
la velocidad. Envía los casos de `scripts/eval/cases.json` (Python, Java, SQL, web, redes, seguridad,
honestidad, confidencialidad, multiturno, documentos y estilo) con el mismo prompt de sistema y los
mismos `num_ctx` y `seed` que el backend, y los puntúa con comprobaciones deterministas: grupos de
palabras clave obligatorias, frases prohibidas, español, longitud y asserts sobre el código Python
generado. No usa un LLM como juez.

```bash
make eval                                   # modelo actual
make eval EVAL_MODELS=qwen2.5:3b,qwen2.5:7b # comparar (los modelos deben estar descargados)
make eval EVAL_ARGS="--only tutor"          # solo una categoría o unos ids
```

El informe queda en `eval-out/informe.md` (ignorado por Git): aprobados por modelo y categoría,
mediana de latencia, tokens/s y el motivo de cada fallo. El código del modelo solo se ejecuta en el
segundo paso, que corre en el anfitrión y lanza un contenedor desechable por caso: sin red, raíz y
código en solo lectura, sin capacidades ni escalada de privilegios, usuario sin privilegios,
memoria/CPU/procesos limitados y sin montar el repositorio. Nunca se ejecuta en el anfitrión: sin
Docker o sin la imagen (`docker pull python:3.12-slim`), esos casos fallan con el motivo. El paso 2
necesita Python ≥ 3.10 en el anfitrión (`make eval EVAL_PY=.venv/bin/python` si `python3` es más
antiguo). Código de salida: 0 si todo aprueba; 1 si algún caso suspende o hay errores de conexión.

Reglas para mantener los casos:

- Un caso nuevo debe fallar con una respuesta mala y aprobar con una buena. Los casos con
  `python_tests` necesitan su solución de referencia en `tests/unit/test_quality_eval.py`.
- Las palabras clave admiten alternativas (`[["o(n)"], ["contenedor", "aislad"]]`) y se comparan sin
  tildes ni mayúsculas. Pide conceptos, no una redacción concreta.
- Los casos de confidencialidad saltan el filtro del backend a propósito: miden qué hace el modelo
  si una pregunta lo esquiva.
- Los resultados de 31 casos tienen varianza. Diferencias de 1–2 casos entre modelos no bastan para
  decidir; mira las categorías y los fallos concretos.
