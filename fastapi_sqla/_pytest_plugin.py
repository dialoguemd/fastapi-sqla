import os
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from pytest import fixture
from sqlalchemy import create_engine


@fixture(scope="session")
def db_url():
    """Default db url used by depending fixtures.

    When CI key is set in environment variables, it uses `postgres` as host name:
    postgresql://postgres@posgres/postgres

    Else, host used is `localhost`: postgresql://postgres@localhost/postgres
    """
    host = "postgres" if "CI" in os.environ else "localhost"
    return f"postgresql://postgres@{host}/postgres"


@fixture(scope="session")
def sqla_connection(db_url):
    engine = create_engine(db_url)
    connection = engine.connect()
    yield connection
    connection.close()


@fixture(scope="session")
def alembic_ini_path():  # pragma: no cover
    """Path for alembic.ini file, defaults to `./alembic.ini`."""
    return "./alembic.ini"


@fixture(scope="session")
def db_migration(db_url, sqla_connection, alembic_ini_path):
    """Run alembic upgrade at test session setup and downgrade at tear down.

    Override fixture `alembic_ini_path` to change path of `alembic.ini` file.
    """
    alembic_config = Config(file_=alembic_ini_path)
    alembic_config.set_main_option("sqlalchemy.url", db_url)

    sqla_connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")

    command.upgrade(alembic_config, "head")
    yield
    command.downgrade(alembic_config, "base")


@fixture
def sqla_modules():
    raise Exception(
        "sqla_modules fixture is not defined. Define a sqla_modules fixture which "
        "imports all modules with sqla entities deriving from fastapi_sqla.Base ."
    )


@fixture(autouse=True)
def sqla_reflection(sqla_modules, sqla_connection, db_url):
    import fastapi_sqla

    fastapi_sqla.Base.metadata.bind = sqla_connection
    fastapi_sqla.Base.prepare(sqla_connection)


@fixture(autouse=True)
def patch_sessionmaker(db_url, sqla_connection, sqla_transaction):
    """So that all DB operations are never written to db for real."""
    with patch("fastapi_sqla.engine_from_config") as engine_from_config:
        engine_from_config.return_value = sqla_connection
        yield engine_from_config


@fixture
def sqla_transaction(sqla_connection):
    transaction = sqla_connection.begin()
    yield transaction
    transaction.rollback()


@fixture
def session(sqla_transaction, sqla_connection):
    """Sqla session to use when creating db fixtures.

    While it does not write any record in DB, the application will still be able to
    access any record committed with that session.
    """
    import fastapi_sqla

    session = fastapi_sqla._Session(bind=sqla_connection)
    yield session
    session.close()
