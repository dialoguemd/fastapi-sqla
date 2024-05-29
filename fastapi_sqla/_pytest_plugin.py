import os
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

from alembic import command
from alembic.config import Config
from pytest import fixture
from sqlalchemy import create_engine, text
from sqlalchemy.orm.session import sessionmaker

try:
    import asyncpg  # noqa
    from sqlalchemy.ext.asyncio import create_async_engine

    asyncio_support = True
except ImportError:
    asyncio_support = False


def pytest_configure(config):
    config.addinivalue_line("markers", "dont_patch_engines: do not patch sqla engines")


@fixture(scope="session")
def db_host():
    """Default db host used by depending fixtures.

    When CI key is set in environment variables, it uses `postgres` as host name else,
    host used is `localhost`
    """
    return "postgres" if "CI" in os.environ else "localhost"


@fixture(scope="session")
def db_user():
    """Default db user used by depending fixtures.

    postgres
    """
    return "postgres"


@fixture(scope="session")
def db_url(db_host, db_user):
    """Default db url used by depending fixtures.

    db url example postgresql://{db_user}@{db_host}/postgres
    """
    return f"postgresql://{db_user}@{db_host}/postgres"


@fixture(scope="session")
def engine(db_url):
    return create_engine(db_url)


@fixture(scope="session")
def sqla_connection(engine):
    with engine.connect() as connection:
        yield connection


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

    with sqla_connection.begin():
        sqla_connection.execute(
            text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        )

    command.upgrade(alembic_config, "head")
    yield
    command.downgrade(alembic_config, "base")


@fixture
def sqla_modules():
    raise Exception(
        "sqla_modules fixture is not defined. Define a sqla_modules fixture which "
        "imports all modules with sqla entities deriving from fastapi_sqla.Base ."
    )


@fixture
def sqla_reflection(sqla_modules, sqla_connection):
    import fastapi_sqla

    fastapi_sqla.Base.metadata.bind = sqla_connection
    fastapi_sqla.Base.prepare(sqla_connection.engine)


@fixture
def patch_engine_from_config(request, sqla_connection):
    """So that all DB operations are never written to db for real."""
    if "dont_patch_engines" in request.keywords:
        yield
    else:
        transaction = sqla_connection.begin()

        with patch("fastapi_sqla.sqla.engine_from_config") as engine_from_config:
            engine_from_config.return_value = sqla_connection
            yield

        transaction.rollback()


@fixture
def session_factory():
    return sessionmaker()


@fixture
def session(
    session_factory, sqla_connection, sqla_reflection, patch_engine_from_config
):
    """Sqla session to use when creating db fixtures.

    While it does not write any record in DB, the application will still be able to
    access any record committed with that session.
    """
    session = session_factory(bind=sqla_connection)
    yield session
    session.close()


def format_async_async_sqlalchemy_url(url):
    scheme, location, path, query, fragment = urlsplit(url)
    return urlunsplit([f"{scheme}+asyncpg", location, path, query, fragment])


@fixture(scope="session")
def async_sqlalchemy_url(db_url):
    """Default async db url.

    It is the same as `db_url` with `postgresql+asyncpg://` as scheme.
    """
    return format_async_async_sqlalchemy_url(db_url)


if asyncio_support:

    @fixture
    def async_engine(async_sqlalchemy_url):
        return create_async_engine(async_sqlalchemy_url)

    @fixture
    async def async_sqla_connection(async_engine):
        async with async_engine.connect() as connection:
            yield connection

    @fixture
    async def patch_new_engine(request, async_sqla_connection):
        """So that all async DB operations are never written to db for real."""
        if "dont_patch_engines" in request.keywords:
            yield
        else:
            async with async_sqla_connection.begin() as transaction:
                with patch("fastapi_sqla.async_sqla.new_engine") as new_engine:
                    new_engine.return_value = async_sqla_connection
                    yield

                await transaction.rollback()

    @fixture
    async def async_sqla_reflection(sqla_modules, async_sqla_connection):
        from fastapi_sqla import Base

        await async_sqla_connection.run_sync(lambda conn: Base.prepare(conn.engine))

    @fixture
    def async_session_factory():
        from fastapi_sqla.async_sqla import SqlaAsyncSession

        return sessionmaker(class_=SqlaAsyncSession)

    @fixture
    async def async_session(
        async_session_factory,
        async_sqla_connection,
        async_sqla_reflection,
        patch_new_engine,
    ):
        session = async_session_factory(bind=async_sqla_connection)
        yield session
        await session.close()
