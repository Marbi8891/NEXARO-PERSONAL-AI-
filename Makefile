.PHONY: install lint format typecheck test cov check run up down logs audit

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
	DATABASE_PATH=./data/nexaro.db uvicorn nexaro_api.main:app --reload --app-dir apps/api

up:
	docker compose up -d --build backend

# Nunca `down -v`: destruiría el volumen con la base de datos.
down:
	docker compose down

logs:
	docker compose logs -f backend

audit:
	pip-audit -r requirements/base.txt -r requirements/aws.txt
