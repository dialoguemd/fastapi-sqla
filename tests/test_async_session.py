from unittest.mock import AsyncMock, patch

from pytest import fixture, mark, raises
from sqlalchemy import text

pytestmark = [mark.sqlalchemy("1.4"), mark.require_asyncpg]


@fixture
async def startup(environ):
    from fastapi_sqla.async_session import startup

    await startup()
    yield


async def test_startup_configure_async_session(startup):
    from fastapi_sqla.async_session import _AsyncSession

    async with _AsyncSession() as session:
        res = await session.execute(text("SELECT 123"))

    assert res.scalar() == 123


async def test_open_async_session(startup):
    from fastapi_sqla.async_session import open_session

    async with open_session() as session:
        res = await session.execute(text("select 123"))

    assert res.scalar() == 123


async def test_new_async_engine_without_async_alchemy_url(
    monkeypatch, async_sqlalchemy_url
):
    from fastapi_sqla.async_session import new_async_engine

    monkeypatch.delenv("async_sqlalchemy_url")
    monkeypatch.setenv("sqlalchemy_url", async_sqlalchemy_url)

    assert new_async_engine()


@fixture
def AsyncSessionMock():
    with patch("fastapi_sqla.async_session._AsyncSession") as AsyncSessionMock:
        AsyncSessionMock.return_value = AsyncMock()
        yield AsyncSessionMock


async def test_context_manager_rollbacks_on_error(AsyncSessionMock):
    from fastapi_sqla.async_session import open_session

    session = AsyncSessionMock.return_value
    with raises(Exception) as raise_info:
        async with open_session():
            raise Exception("boom!")

    session.rollback.assert_awaited_once_with()
    assert raise_info.value.args == ("boom!",)
