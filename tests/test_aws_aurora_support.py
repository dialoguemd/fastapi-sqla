from unittest.mock import Mock

from pytest import mark, raises
from sqlalchemy import text


@mark.sqlalchemy("1.4")
@mark.dont_patch_engines
def test_sync_disconnects_on_readonly_error(monkeypatch):
    from fastapi_sqla.sqla import _Session, startup

    monkeypatch.setenv("fastapi_sqla_aws_aurora_enabled", "true")

    startup()

    connection = _Session().connection(execution_options={"postgresql_readonly": True})
    with raises(Exception):
        connection.execute(text("CREATE TABLE fail(id integer)"))

    assert connection.invalidated


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
@mark.dont_patch_engines
async def test_async_disconnects_on_readonly_error(monkeypatch, async_sqlalchemy_url):
    from fastapi_sqla.async_session import _AsyncSession, startup

    monkeypatch.setenv("fastapi_sqla_aws_aurora_enabled", "true")
    monkeypatch.setenv("async_sqlalchemy_url", async_sqlalchemy_url)

    await startup()

    connection = await _AsyncSession().connection(
        execution_options={"postgresql_readonly": True}
    )
    with raises(Exception):
        await connection.execute(text("CREATE TABLE fail(id integer)"))

    assert connection.invalidated


@mark.parametrize(
    "pgcode, should_disconnect", [("25006", True), ("00000", False), (None, False)]
)
def test_readonly_error_codes(pgcode, should_disconnect):
    from fastapi_sqla.aws_aurora_support import disconnect_on_readonly_error

    exception = Mock()
    exception.pgcode = pgcode
    context = Mock()
    context.original_exception = exception
    context.is_disconnect = False

    disconnect_on_readonly_error(context)

    assert context.is_disconnect == should_disconnect


def test_already_disconnected():
    from fastapi_sqla.aws_aurora_support import disconnect_on_readonly_error

    context = Mock()
    context.is_disconnect = True

    disconnect_on_readonly_error(context)

    assert context.is_disconnect is True
