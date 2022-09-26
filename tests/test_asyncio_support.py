from unittest.mock import patch

from pytest import fixture, mark, raises
from sqlalchemy import text

pytestmark = [mark.sqlalchemy("1.4"), mark.require_asyncpg]


@fixture
async def setup(environ):
    from fastapi_sqla.asyncio_support import startup

    await startup()
    yield


async def test_startup_configure_async_session():
    from fastapi_sqla.asyncio_support import _AsyncSession, startup

    await startup()

    async with _AsyncSession() as session:
        res = await session.execute(text("SELECT 123"))

    assert res.scalar() == 123


async def test_open_async_session(setup):
    from fastapi_sqla.asyncio_support import open_session

    async with open_session() as session:
        res = await session.execute(text("select 123"))

    assert res.scalar() == 123


async def test_new_async_engine_without_async_alchemy_url(
    monkeypatch, async_sqlalchemy_url
):
    from fastapi_sqla.asyncio_support import new_async_engine

    monkeypatch.delenv("async_sqlalchemy_url")
    monkeypatch.setenv("sqlalchemy_url", async_sqlalchemy_url)

    assert new_async_engine()


@fixture
def AsyncSessionMock():
    with patch("fastapi_sqla.asyncio_support._AsyncSession") as AsyncSessionMock:
        yield AsyncSessionMock


async def test_context_manager_rollbacks_on_error(AsyncSessionMock):
    from fastapi_sqla.asyncio_support import open_session

    session = AsyncSessionMock.return_value
    with raises(Exception):
        async with open_session():
            raise Exception()

    session.rollback.assert_called_once_with()
