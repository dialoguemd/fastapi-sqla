import os
from collections.abc import AsyncGenerator, Generator
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

from alembic import command
from alembic.config import Config
from pytest import FixtureRequest, fixture
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm.session import Session, sessionmaker

try:
    import asyncpg  # noqa
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        AsyncEngine,
        AsyncConnection,
        AsyncSession,
    )

    asyncio_support = True
except ImportError:
    asyncio_support = False


def pytest_configure(config):
    config.addinivalue_line("markers", "dont_patch_engines: do not patch sqla engines")


@fixture(scope="session")
def db_host() -> str:
    """Default db host used by depending fixtures.

    When CI key is set in environment variables, it uses `postgres` as host name else,
    host used is `localhost`
    """
    return "postgres" if "CI" in os.environ else "localhost"


@fixture(scope="session")
def db_user() -> str:
    """Default db user used by depending fixtures.

    postgres
    """
    return "postgres"


@fixture(scope="session")
def db_url(db_host: str, db_user: str) -> str:
    """Default db url used by depending fixtures.

    db url example postgresql://{db_user}@{db_host}/postgres
    """
    return f"postgresql://{db_user}@{db_host}/postgres"


@fixture(scope="session")
def engine(db_url: str) -> Engine:
    return create_engine(db_url)


@fixture(scope="session")
def sqla_connection(engine: Engine) -> Generator[Connection]:
    with engine.connect() as connection:
        yield connection


@fixture(scope="session")
def alembic_ini_path() -> str:  # pragma: no cover
    """Path for alembic.ini file, defaults to `./alembic.ini`."""
    return "./alembic.ini"


@fixture(scope="session")
def db_migration(db_url: str, sqla_connection: Connection, alembic_ini_path: str):
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
def sqla_reflection(sqla_modules, sqla_connection: Connection):
    import fastapi_sqla

    fastapi_sqla.Base.metadata.bind = sqla_connection  # type: ignore
    fastapi_sqla.Base.prepare(sqla_connection.engine)


@fixture
def patch_new_engine(request: FixtureRequest, sqla_connection: Connection):
    """So that all DB operations are never written to db for real."""
    if "dont_patch_engines" in request.keywords:
        yield
    else:
        with sqla_connection.begin() as transaction:
            with patch("fastapi_sqla.sqla.new_engine", return_value=sqla_connection):
                yield

            transaction.rollback()


@fixture
def session_factory(
    sqla_connection: Connection, sqla_reflection, patch_new_engine
) -> sessionmaker:
    return sessionmaker(bind=sqla_connection)


@fixture
def session(session_factory: sessionmaker) -> Generator[Session]:
    """Sqla session to use when creating db fixtures.

    While it does not write any record in DB, the application will still be able to
    access any record committed with that session.
    """
    session: Session = session_factory()
    yield session
    session.close()


def format_async_async_sqlalchemy_url(url: str) -> str:
    scheme, location, path, query, fragment = urlsplit(url)
    return urlunsplit([f"{scheme}+asyncpg", location, path, query, fragment])


@fixture(scope="session")
def async_sqlalchemy_url(db_url: str) -> str:
    """Default async db url.

    It is the same as `db_url` with `postgresql+asyncpg://` as scheme.
    """
    return format_async_async_sqlalchemy_url(db_url)


if asyncio_support:

    @fixture
    def async_engine(async_sqlalchemy_url: str) -> AsyncEngine:
        return create_async_engine(async_sqlalchemy_url)

    @fixture
    async def async_sqla_connection(
        async_engine: AsyncEngine,
    ) -> AsyncGenerator[AsyncConnection]:
        async with async_engine.connect() as connection:
            yield connection

    @fixture
    async def patch_new_async_engine(
        request: FixtureRequest, async_sqla_connection: AsyncConnection
    ):
        """So that all async DB operations are never written to db for real."""
        if "dont_patch_engines" in request.keywords:
            yield
        else:
            async with async_sqla_connection.begin() as transaction:
                with patch(
                    "fastapi_sqla.async_sqla.new_async_engine",
                    return_value=async_sqla_connection,
                ):
                    yield

                await transaction.rollback()

    @fixture
    async def async_sqla_reflection(
        sqla_modules, async_sqla_connection: AsyncConnection
    ):
        from fastapi_sqla import Base

        await async_sqla_connection.run_sync(lambda conn: Base.prepare(conn.engine))

    @fixture
    def async_session_factory(
        async_sqla_connection: AsyncConnection,
        async_sqla_reflection,
        patch_new_async_engine,
    ) -> sessionmaker:
        # TODO: Use async_sessionmaker once only supporting 2.x+
        return sessionmaker(
            bind=async_sqla_connection, expire_on_commit=False, class_=AsyncSession
        )  # type: ignore

    @fixture
    async def async_session(
        async_session_factory: sessionmaker,
    ) -> AsyncGenerator[AsyncSession]:
        session: AsyncSession = async_session_factory()
        yield session
        await session.close()
