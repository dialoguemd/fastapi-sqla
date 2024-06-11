from unittest.mock import AsyncMock, call, patch

from pytest import fixture, mark


@fixture
def async_sqla_startup_mock():
    with patch("fastapi_sqla.async_sqla.startup", new=AsyncMock()) as mock:
        yield mock


@fixture
def sqla_startup_mock():
    with patch("fastapi_sqla.sqla.startup") as mock:
        yield mock


async def test_startup_multiple_engines(
    db_url, sqla_startup_mock, async_sqla_startup_mock
):
    from fastapi_sqla.base import startup
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    read_only_key = "read_only"

    with patch.dict(
        "os.environ",
        values={
            "sqlalchemy_url": db_url,
            f"fastapi_sqla__{read_only_key}__sqlalchemy_url": db_url,
        },
        clear=True,
    ):
        await startup()

    assert async_sqla_startup_mock.call_count == 0
    assert sqla_startup_mock.call_count == 2

    sqla_startup_mock.assert_has_calls(
        [
            call(key=read_only_key),
            call(key=_DEFAULT_SESSION_KEY),
        ],
        any_order=True,
    )


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
async def test_startup_with_sync_and_async_sqlalchemy_url(
    async_session_key, sqla_startup_mock, async_sqla_startup_mock
):
    from fastapi_sqla.base import startup
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    await startup()

    assert async_sqla_startup_mock.call_count == 1
    async_sqla_startup_mock.assert_awaited_once_with(key=async_session_key)

    assert sqla_startup_mock.call_count == 1
    sqla_startup_mock.assert_called_once_with(key=_DEFAULT_SESSION_KEY)


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
async def test_startup_with_async_default_sqlalchemy_url(
    async_sqlalchemy_url, sqla_startup_mock, async_sqla_startup_mock
):
    from fastapi_sqla.base import startup
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    with patch.dict(
        "os.environ", values={"sqlalchemy_url": async_sqlalchemy_url}, clear=True
    ):
        await startup()

    assert sqla_startup_mock.call_count == 0
    assert async_sqla_startup_mock.call_count == 1
    async_sqla_startup_mock.assert_called_once_with(key=_DEFAULT_SESSION_KEY)
