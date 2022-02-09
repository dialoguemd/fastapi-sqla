from unittest.mock import Mock, patch

import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pytest import fixture, mark, raises
from sqlalchemy import text


@fixture(params=[True, False])
def case_sensitive_environ(environ, request):
    values = (
        {k.upper(): v for k, v in environ.items()} if request.param else environ.copy()
    )
    with patch.dict("os.environ", values=values, clear=True):
        yield values


@fixture()
def boto_session(boto_client_mock):
    boto_session_mock = Mock()
    boto_session_mock.client.return_value = boto_client_mock

    with patch("boto3.Session", return_value=boto_session_mock):
        yield boto_session_mock


@fixture()
def boto_client_mock():
    return Mock()


@mark.dont_patch_engines
def test_startup(case_sensitive_environ):
    from fastapi_sqla import _Session, startup

    startup()

    session = _Session()

    assert session.execute(text("SELECT 1")).scalar() == 1


@mark.asyncio
async def test_fastapi_integration():
    from fastapi_sqla import _Session, setup

    app = FastAPI()
    setup(app)

    @app.get("/one")
    def now():
        session = _Session()
        result = session.execute(text("SELECT 1")).scalar()
        session.close()
        return result

    async with LifespanManager(app):
        async with httpx.AsyncClient(
            app=app, base_url="http://example.local"
        ) as client:
            res = await client.get("/one")

    assert res.json() == 1


@mark.dont_patch_engines
def test_startup_fail_on_bad_sqlalchemy_url(monkeypatch):
    from fastapi_sqla import startup

    monkeypatch.setenv("sqlalchemy_url", "postgresql://postgres@localhost/notexisting")

    with raises(Exception):
        startup()


@mark.asyncio
@mark.dont_patch_engines
async def test_async_startup_fail_on_bad_async_sqlalchemy_url(monkeypatch):
    from fastapi_sqla import asyncio_support

    monkeypatch.setenv(
        "async_sqlalchemy_url", "postgresql+asyncpg://postgres@localhost/notexisting"
    )

    with raises(Exception):
        await asyncio_support.startup()


@mark.require_boto3
@mark.dont_patch_engines
def test_sync_startup_with_aws_rds_iam_enabled(
    monkeypatch, boto_session, boto_client_mock, db_host, db_user
):
    from fastapi_sqla import startup

    monkeypatch.setenv("fastapi_sqla_aws_rds_iam_enabled", True)

    startup()

    boto_client_mock.generate_db_auth_token.assert_called_once_with(
        DBHostname=db_host, Port=5432, DBUsername=db_user
    )


@mark.require_boto3
@mark.require_asyncpg
@mark.sqlalchemy("1.4")
@mark.asyncio
@mark.dont_patch_engines
async def test_async_startup_with_aws_rds_iam_enabled(
    monkeypatch, async_sqlalchemy_url, boto_session, boto_client_mock, db_host, db_user
):
    from fastapi_sqla.asyncio_support import startup

    monkeypatch.setenv("fastapi_sqla_aws_rds_iam_enabled", True)
    monkeypatch.setenv("async_sqlalchemy_url", async_sqlalchemy_url)

    await startup()

    boto_client_mock.generate_db_auth_token.assert_called_once_with(
        DBHostname=db_host, Port=5432, DBUsername=db_user
    )
