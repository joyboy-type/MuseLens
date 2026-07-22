.PHONY: install test lint build dev-api dev-web package-modelscope smoke-deployment storage clean-generated clean-feature-cache

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

package-modelscope:
	.venv/bin/python scripts/package_modelscope.py /tmp/muselens-modelscope
	.venv/bin/python scripts/publish_modelscope.py /tmp/muselens-modelscope \
		--repo-id "$${MODELSCOPE_STUDIO_ID}" --dry-run

smoke-deployment:
	test -n "$(URL)"
	.venv/bin/python scripts/smoke_deployment.py "$(URL)" --contract quick

storage:
	.venv/bin/python scripts/cleanup_workspace.py --include-feature-cache

clean-generated:
	.venv/bin/python scripts/cleanup_workspace.py --apply

clean-feature-cache:
	.venv/bin/python scripts/cleanup_workspace.py --apply --include-feature-cache
