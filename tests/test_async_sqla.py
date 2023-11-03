from unittest.mock import AsyncMock, Mock, patch

from pytest import fixture, mark, raises
from sqlalchemy import text

pytestmark = [mark.sqlalchemy("1.4"), mark.require_asyncpg]


@fixture
async def startup(async_session_key):
    from fastapi_sqla.async_sqla import startup

    await startup(async_session_key)
    yield


async def test_startup_configure_async_session(startup, async_session_key):
    from fastapi_sqla.async_sqla import _async_session_factories

    async with _async_session_factories[async_session_key]() as session:
        res = await session.execute(text("SELECT 123"))

    assert res.scalar() == 123


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


async def test_open_async_session(startup, async_session_key):
    from fastapi_sqla.async_sqla import open_session

    async with open_session(async_session_key) as session:
        res = await session.execute(text("select 123"))

    assert res.scalar() == 123


@fixture
def async_session_mock():
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

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


async def test_open_async_session_raises_unknown_key():
    from fastapi_sqla.async_sqla import open_session

    with raises(KeyError) as raise_info:
        async with open_session(key="unknown"):
            pass

    assert "No async session with key" in raise_info.value.args[0]
