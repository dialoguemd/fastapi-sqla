diff\:v1:
	@for f in models.py pagination.py async_pagination.py; do \
		git diff --no-index fastapi_sqla/$$f fastapi_sqla/v1/$$f || true; \
	done
test:
	poetry run pytest
test\:cov:
	poetry run pytest --cov .
checks:
	poetry run ruff check .
fixes:
	poetry run ruff format .
	poetry run ruff check . --fix-only
