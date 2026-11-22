.PHONY: install lint format typecheck test cov check run up down logs audit eval model model-check smoke

PY ?= python3

install:
	$(PY) -m pip install -r requirements/dev.txt

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy packages apps products

test:
	pytest

cov:
	pytest --cov --cov-report=term-missing

check: lint typecheck cov

run:
	DATABASE_PATH=./data/nexaro.db FRONTEND_PATH=./frontend PYTHONPATH=.:packages:apps/api \
	uvicorn nexaro_api.main:create_app --factory --reload --host 127.0.0.1 --port 8001

# Docker (ADR-0021). El modo de Ollama sale de .env: sin nada, el externo (~/Docker/ollama-local);
# con COMPOSE_PROFILES=ollama y OLLAMA_NETWORK=nexaro_ollama, el incluido. Ver DEPLOYMENT.md.
up:
	scripts/stack.sh preflight
	docker compose up -d --build --wait --wait-timeout 300

# Nunca `down -v`: destruiría los volúmenes con la base de datos y los modelos.
down:
	docker compose down

logs:
	docker compose logs -f

# Descarga el modelo configurado solo si falta (idempotente). Necesita el stack arrancado.
model:
	docker exec -i nexaro-backend sh -c 'python - ensure "$$OLLAMA_MODEL"' < scripts/ollama_model.py

model-check:
	docker exec -i nexaro-backend sh -c 'python - check "$$OLLAMA_MODEL"' < scripts/ollama_model.py

# Prueba de humo contra Docker y Ollama reales (servicios, salud, modelo, respuesta y persistencia).
smoke:
	scripts/stack.sh smoke

audit:
	pip-audit -r requirements/base.txt -r requirements/aws.txt

# Evaluación de calidad (ver DEVELOPMENT.md). Paso 1: genera respuestas en la red de Ollama.
# Paso 2: las puntúa ejecutando el código del modelo en un contenedor sin red ni privilegios.
EVAL_MODELS ?= qwen2.5:3b
EVAL_IMAGE ?= python:3.12-slim
EVAL_ARGS ?=  # p. ej. EVAL_ARGS="--only tutor"
eval:
	mkdir -p eval-out
	docker run --rm --network ollama-local_default -v "$(CURDIR):/repo:ro" -v "$(CURDIR)/eval-out:/out" \
		$(EVAL_IMAGE) python /repo/scripts/quality_eval.py --base-url http://ollama:11434 \
		--models $(EVAL_MODELS) --save-answers /out/respuestas.json --report /out/informe.md $(EVAL_ARGS)
	docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL \
		--security-opt no-new-privileges --memory 512m --pids-limit 128 \
		-v "$(CURDIR):/repo:ro" -v "$(CURDIR)/eval-out:/out" \
		$(EVAL_IMAGE) python /repo/scripts/quality_eval.py --grade-only /out/respuestas.json \
		--run-code --report /out/informe.md $(EVAL_ARGS)
