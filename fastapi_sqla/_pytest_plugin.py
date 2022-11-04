import os
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

from alembic import command
from alembic.config import Config
from pytest import fixture
from sqlalchemy import create_engine, text

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
def sqla_connection(db_url):
    engine = create_engine(db_url)
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
def sqla_reflection(sqla_modules, sqla_connection, db_url):
    import fastapi_sqla

    fastapi_sqla.Base.metadata.bind = sqla_connection
    fastapi_sqla.Base.prepare(sqla_connection)


@fixture
def patch_engine_from_config(request, db_url, sqla_connection, sqla_transaction):
    """So that all DB operations are never written to db for real."""
    from fastapi_sqla.sqla import _Session

    if "dont_patch_engines" in request.keywords:
        yield

    else:
        with patch("fastapi_sqla.sqla.engine_from_config") as engine_from_config:
            engine_from_config.return_value = sqla_connection
            _Session.configure(bind=sqla_connection)
            yield engine_from_config


@fixture
def sqla_transaction(sqla_connection):
    transaction = sqla_connection.begin()
    yield transaction
    transaction.rollback()


@fixture
def session(
    sqla_transaction, sqla_connection, sqla_reflection, patch_engine_from_config
):
    """Sqla session to use when creating db fixtures.

    While it does not write any record in DB, the application will still be able to
    access any record committed with that session.
    """
    import fastapi_sqla.sqla

    yield fastapi_sqla.sqla._Session(bind=sqla_connection)


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
    async def async_engine(async_sqlalchemy_url):
        return create_async_engine(async_sqlalchemy_url)

    @fixture
    async def async_sqla_connection(async_engine, event_loop):
        async with async_engine.begin() as connection:
            yield connection
            await connection.rollback()

    @fixture
    async def patch_new_engine(async_sqlalchemy_url, async_sqla_connection, request):
        """So that all async DB operations are never written to db for real."""
        from fastapi_sqla.asyncio_support import _AsyncSession

        if "dont_patch_engines" in request.keywords:
            yield

        else:
            with patch("fastapi_sqla.asyncio_support.new_engine") as new_engine:
                new_engine.return_value = async_sqla_connection
                _AsyncSession.configure(
                    bind=async_sqla_connection, expire_on_commit=False
                )
                yield new_engine

    @fixture
    async def async_session(async_sqla_connection, sqla_reflection, patch_new_engine):
        from fastapi_sqla.asyncio_support import _AsyncSession

        session = _AsyncSession(bind=async_sqla_connection)
        yield session
        await session.close()

else:

    @fixture
    async def patch_new_engine():
        pass
