.PHONY: help install lint format typecheck test cov check docs-check run up down logs audit eval model model-check smoke screenshots

PY ?= python3
.DEFAULT_GOAL := help

# `make` sin objetivo muestra la ayuda. Cada objetivo documentado lleva un comentario `## ...`.
help: ## Show this help
	@echo "NEXARO - available commands (documentation: docs/README.md)"
	@echo
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-13s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "First run with Docker: make up && make model && make smoke  (docs/getting-started/installation.md)"

install: ## Install development dependencies (requirements/dev.txt)
	$(PY) -m pip install -r requirements/dev.txt

lint: ## Ruff lint + format check
	ruff check .
	ruff format --check .

format: ## Auto-fix lint issues and format the code
	ruff check --fix .
	ruff format .

typecheck: ## Type-check with mypy
	mypy packages apps products

test: ## Run the test suite
	pytest

cov: ## Run the tests with a coverage report
	pytest --cov --cov-report=term-missing

check: lint typecheck cov ## What CI checks: lint, types, tests with coverage (includes docs links)

docs-check: ## Validate relative links and anchors in every Markdown file
	$(PY) scripts/check_docs_links.py

run: ## Run the API + UI locally with reload on 127.0.0.1:8001
	DATABASE_PATH=./data/nexaro.db FRONTEND_PATH=./frontend PYTHONPATH=.:packages:apps/api \
	uvicorn nexaro_api.main:create_app --factory --reload --host 127.0.0.1 --port 8001

# Docker (ADR-0021). El modo de Ollama sale de .env: sin nada, el externo (~/Docker/ollama-local);
# con COMPOSE_PROFILES=ollama y OLLAMA_NETWORK=nexaro_ollama, el incluido.
# Ver docs/getting-started/installation.md y docs/deployment/deployment-reference.md.
up: ## Docker: preflight checks, build, start and wait until healthy
	scripts/stack.sh preflight
	docker compose up -d --build --wait --wait-timeout 300

# Nunca `down -v`: destruiría los volúmenes con la base de datos y los modelos.
down: ## Docker: stop the containers (data volumes are kept)
	docker compose down

logs: ## Docker: follow the logs
	docker compose logs -f

# Descarga el modelo configurado solo si falta (idempotente). Necesita el stack arrancado.
model: ## Docker: download the configured model only if missing
	docker exec -i nexaro-backend sh -c 'python - ensure "$$OLLAMA_MODEL"' < scripts/ollama_model.py

model-check: ## Docker: check that the configured model is installed
	docker exec -i nexaro-backend sh -c 'python - check "$$OLLAMA_MODEL"' < scripts/ollama_model.py

# Prueba de humo contra Docker y Ollama reales (servicios, salud, modelo, respuesta y persistencia).
smoke: ## Docker: end-to-end check against the real Ollama (answer + persistence)
	scripts/stack.sh smoke

audit: ## Scan runtime dependencies for known vulnerabilities (pip-audit)
	pip-audit -r requirements/base.txt -r requirements/aws.txt

# Evaluación de calidad (ver docs/development/reference.md). Paso 1: genera respuestas en la red de Ollama.
# Paso 2: las puntúa ejecutando el código del modelo en un contenedor sin red ni privilegios.
EVAL_MODELS ?= qwen2.5:3b
EVAL_IMAGE ?= python:3.12-slim
EVAL_ARGS ?=  # p. ej. EVAL_ARGS="--only tutor"
eval: ## Evaluate model answer quality (needs Docker and Ollama)
	mkdir -p eval-out
	docker run --rm --network ollama-local_default -v "$(CURDIR):/repo:ro" -v "$(CURDIR)/eval-out:/out" \
		$(EVAL_IMAGE) python /repo/scripts/quality_eval.py --base-url http://ollama:11434 \
		--models $(EVAL_MODELS) --save-answers /out/respuestas.json --report /out/informe.md $(EVAL_ARGS)
	docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL \
		--security-opt no-new-privileges --memory 512m --pids-limit 128 \
		-v "$(CURDIR):/repo:ro" -v "$(CURDIR)/eval-out:/out" \
		$(EVAL_IMAGE) python /repo/scripts/quality_eval.py --grade-only /out/respuestas.json \
		--run-code --report /out/informe.md $(EVAL_ARGS)

# Capturas del producto (docs/assets/README.md): aplicación real, datos de demostración, Chromium real.
SHOTS_PORT ?= 8766
screenshots: ## Capture product screenshots into docs/assets/screenshots (needs Node >= 20)
	cd tests/frontend && npm install --no-audit --no-fund --silent
	REPO="$(CURDIR)" PYTHONPATH="$(CURDIR):$(CURDIR)/packages:$(CURDIR)/apps/api" \
	NEXARO_DEMO_PORT=$(SHOTS_PORT) LOG_LEVEL=WARNING $(PY) tests/frontend/demo_server.py & server=$$!; \
	trap 'kill $$server 2>/dev/null' EXIT; \
	for i in $$(seq 1 50); do curl -fs http://127.0.0.1:$(SHOTS_PORT)/api/health/live >/dev/null && break; sleep 0.2; done; \
	cd tests/frontend && NEXARO_DEMO_PORT=$(SHOTS_PORT) node screenshots.mjs
