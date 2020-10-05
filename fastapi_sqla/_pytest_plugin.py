from unittest.mock import patch

from pytest import fixture
from sqlalchemy import create_engine


@fixture(scope="session")
def db_url():
    raise Exception(
        "db_url fixture is not defined. Define a db_url fixture in session scope."
    )


@fixture(scope="session")
def sqla_connection(db_url):
    engine = create_engine(db_url)
    connection = engine.connect()
    yield connection
    connection.close()


@fixture(autouse=True)
def sqla_reflection(sqla_connection, db_url):
    import fastapi_sqla

    fastapi_sqla.Base.metadata.bind = sqla_connection
    fastapi_sqla.Base.prepare(sqla_connection)


@fixture(autouse=True)
def patch_sqla_engine(db_url, sqla_connection, sqla_transaction):
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
    import fastapi_sqla

    session = fastapi_sqla._Session(bind=sqla_connection)
    yield session
    session.close()
