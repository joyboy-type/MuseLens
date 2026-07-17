.PHONY: install test lint build dev-api dev-web

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'
	cd frontend && npm ci

test:
	.venv/bin/pytest -q
	cd frontend && npm test

lint:
	.venv/bin/ruff check src tests scripts
	cd frontend && npm run lint

build:
	cd frontend && npm run build

dev-api:
	.venv/bin/uvicorn muselens.api:app --reload

dev-web:
	cd frontend && npm run dev
