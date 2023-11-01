from unittest.mock import AsyncMock, Mock, patch

from pytest import fixture, mark, raises
from sqlalchemy import text

pytestmark = [mark.sqlalchemy("1.4"), mark.require_asyncpg]


@fixture
async def startup(environ):
    from fastapi_sqla.async_sqla import startup

    await startup()
    yield


async def test_startup_configure_async_session(startup):
    from fastapi_sqla.async_sqla import _async_session_factories
    from fastapi_sqla.base import _DEFAULT_SESSION_KEY

    async with _async_session_factories[_DEFAULT_SESSION_KEY]() as session:
        res = await session.execute(text("SELECT 123"))

    assert res.scalar() == 123


async def test_open_async_session(startup):
    from fastapi_sqla.async_sqla import open_session

    async with open_session() as session:
        res = await session.execute(text("select 123"))

    assert res.scalar() == 123


async def test_new_async_engine_without_async_alchemy_url(
    monkeypatch, async_sqlalchemy_url
):
    from fastapi_sqla.async_sqla import new_async_engine

    monkeypatch.delenv("async_sqlalchemy_url")
    monkeypatch.setenv("sqlalchemy_url", async_sqlalchemy_url)

    assert new_async_engine()


@fixture
def async_session_mock():
    from fastapi_sqla.base import _DEFAULT_SESSION_KEY

    sessionmaker_mock = Mock()
    session_mock = AsyncMock()
    sessionmaker_mock.return_value = session_mock

    with patch.dict(
        "fastapi_sqla.async_sqla._async_session_factories",
        {_DEFAULT_SESSION_KEY: sessionmaker_mock},
    ):
        yield sessionmaker_mock


async def test_context_manager_rollbacks_on_error(async_session_mock):
    from fastapi_sqla.async_sqla import open_session

    session = async_session_mock.return_value
    with raises(Exception) as raise_info:
        async with open_session():
            raise Exception("boom!")

    session.rollback.assert_awaited_once_with()
    assert raise_info.value.args == ("boom!",)
