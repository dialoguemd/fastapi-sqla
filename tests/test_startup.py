from unittest.mock import Mock, patch

import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pytest import fixture, mark, raises
from sqlalchemy import exc as sqlalcemy_exception
from sqlalchemy import text


@fixture
def clear_rds_client_cache():
    from fastapi_sqla.aws_rds_iam_support import get_rds_client

    get_rds_client.cache_clear()


@fixture()
def boto_session(boto_client_mock, clear_rds_client_cache):
    boto_session_mock = Mock()
    boto_session_mock.client.return_value = boto_client_mock

    with patch("boto3.Session", return_value=boto_session_mock):
        yield boto_session_mock


@fixture()
def boto_client_mock():
    return Mock()


def test_startup():
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, _session_factories, startup

    startup()

    session = _session_factories[_DEFAULT_SESSION_KEY]()

    assert session.execute(text("SELECT 123")).scalar() == 123


def test_startup_case_insensitive(environ):
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, _session_factories, startup

    values = {k.upper(): v for k, v in environ.items()}
    with patch.dict("os.environ", values=values, clear=True):
        startup()

    session = _session_factories[_DEFAULT_SESSION_KEY]()

    assert session.execute(text("SELECT 123")).scalar() == 123


def test_startup_with_key(monkeypatch, db_url):
    from fastapi_sqla.sqla import _session_factories, startup

    key = "potato"
    monkeypatch.setenv(f"fastapi_sqla__{key}__sqlalchemy_url", db_url)

    startup(key)

    session = _session_factories[key]()

    assert session.execute(text("SELECT 123")).scalar() == 123


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_startup_configure_async_session(async_session_key):
    from fastapi_sqla.async_sqla import _async_session_factories, startup

    await startup(async_session_key)

    async with _async_session_factories[async_session_key]() as session:
        res = await session.execute(text("SELECT 123"))

    assert res.scalar() == 123


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_startup_configure_async_session_with_default_alchemy_url(
    monkeypatch, async_sqlalchemy_url
):
    from fastapi_sqla.async_sqla import _async_session_factories, startup
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    monkeypatch.setenv("sqlalchemy_url", async_sqlalchemy_url)

    await startup()

    async with _async_session_factories[_DEFAULT_SESSION_KEY]() as session:
        res = await session.execute(text("SELECT 123"))

    assert res.scalar() == 123


def test_startup_fail_on_bad_sqlalchemy_url(monkeypatch, db_user, db_host):
    from fastapi_sqla.sqla import startup

    monkeypatch.setenv(
        "sqlalchemy_url", f"postgresql://{db_user}@{db_host}/notexisting"
    )

    with raises(sqlalcemy_exception.OperationalError):
        startup()


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_async_startup_fail_on_bad_async_sqlalchemy_url(
    monkeypatch, db_user, db_host
):
    from asyncpg.exceptions import InvalidCatalogNameError

    from fastapi_sqla.async_sqla import startup

    monkeypatch.setenv(
        "sqlalchemy_url", f"postgresql+asyncpg://{db_user}@{db_host}/notexisting"
    )
    with raises(InvalidCatalogNameError):
        await startup()


@mark.require_boto3
def test_sync_startup_with_aws_rds_iam_enabled(
    monkeypatch, boto_session, boto_client_mock, db_host, db_user
):
    from fastapi_sqla.sqla import startup

    monkeypatch.setenv("fastapi_sqla_aws_rds_iam_enabled", "true")

    startup()

    boto_client_mock.generate_db_auth_token.assert_called_once_with(
        DBHostname=db_host, Port=5432, DBUsername=db_user
    )


@mark.require_boto3
@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_async_startup_with_aws_rds_iam_enabled(
    monkeypatch, async_session_key, boto_session, boto_client_mock, db_host, db_user
):
    from fastapi_sqla.async_sqla import startup

    monkeypatch.setenv("fastapi_sqla_aws_rds_iam_enabled", "true")

    await startup(async_session_key)

    boto_client_mock.generate_db_auth_token.assert_called_with(
        DBHostname=db_host, Port=5432, DBUsername=db_user
    )


async def test_fastapi_integration():
    from fastapi_sqla.base import setup
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, _session_factories

    app = FastAPI()
    setup(app)

    @app.get("/one")
    def now():
        session = _session_factories[_DEFAULT_SESSION_KEY]()
        result = session.execute(text("SELECT 1")).scalar()
        session.close()
        return result

    async with (
        LifespanManager(app),
        httpx.AsyncClient(app=app, base_url="http://example.local") as client,
    ):
        res = await client.get("/one")

    assert res.json() == 1
