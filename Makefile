test:
	poetry run pytest
test\:cov:
	poetry run pytest --cov .
checks:
	poetry run ruff check .
fixes:
	poetry run ruff format .
	poetry run ruff check . --fix-only
