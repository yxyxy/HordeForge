.PHONY: install install-dev run test lint format docker-build docker-up docker-down

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

run:
	uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	black .

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down
