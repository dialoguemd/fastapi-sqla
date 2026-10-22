from unittest.mock import AsyncMock, MagicMock

from pytest import mark, raises
from structlog.testing import capture_logs


@mark.parametrize("commit_failure", [False, True])
def test_session_error_logs_keep_session_context(monkeypatch, commit_failure):
    from fastapi_sqla import sqla

    session = MagicMock()
    error = RuntimeError("session failure")
    if commit_failure:
        session.commit.side_effect = error
    monkeypatch.setitem(sqla._session_factories, "logging", lambda: session)

    with capture_logs() as logs:
        with raises(RuntimeError) as raised, sqla.open_session("logging"):
            if not commit_failure:
                raise error
        sqla.logger.info("outside session")

    assert raised.value is error
    assert logs[0]["db_session"] is session
    assert logs[0]["event"] == (
        "commit failed, rolling back"
        if commit_failure
        else "context failed, rolling back"
    )
    assert "db_session" not in logs[-1]
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
@mark.parametrize("commit_failure", [False, True])
async def test_async_session_error_logs_keep_session_context(
    monkeypatch, commit_failure
):
    from fastapi_sqla import async_sqla

    session = AsyncMock()
    error = RuntimeError("session failure")
    if commit_failure:
        session.commit.side_effect = error
    monkeypatch.setitem(async_sqla._async_session_factories, "logging", lambda: session)

    with capture_logs() as logs:
        with raises(RuntimeError) as raised:
            async with async_sqla.open_session("logging"):
                if not commit_failure:
                    raise error
        async_sqla.logger.info("outside session")

    assert raised.value is error
    assert logs[0]["db_async_session"] is session
    assert logs[0]["event"] == (
        "commit failed, rolling back"
        if commit_failure
        else "context failed, rolling back"
    )
    assert "db_async_session" not in logs[-1]
    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()
