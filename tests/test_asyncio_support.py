from pytest import fixture, mark
from sqlalchemy import text

pytestmark = [mark.asyncio, mark.sqlalchemy("1.4"), mark.require_asyncpg]


@fixture(autouse=True)
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


async def test_open_async_session():
    from fastapi_sqla.asyncio_support import open_session

    async with open_session() as session:
        res = await session.execute(text("select 123"))

    assert res.scalar() == 123
