testdb\:run:
	docker run --rm --name fastapi-sqla-postgres -e POSTGRES_DB=postgres -e POSTGRES_USER=postgres -e POSTGRES_HOST_AUTH_METHOD=trust -p 5432:5432 postgres:14
