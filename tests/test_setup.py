from unittest.mock import Mock

from pytest import mark

from fastapi_sqla import async_sqla


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
def test_setup_with_async_sqlalchemy_url_adds_asyncio_support_startup(
    monkeypatch, async_sqlalchemy_url
):
    from fastapi_sqla import setup

    monkeypatch.delenv("async_sqlalchemy_url")
    monkeypatch.setenv("sqlalchemy_url", async_sqlalchemy_url)

    app = Mock()
    setup(app)

    app.add_event_handler.assert_called_once()
    assert app.add_event_handler.call_args.args[0] == "startup"
    assert app.add_event_handler.call_args.args[1].func == async_sqla.startup

    app.middleware.assert_called_once_with("http")
    app.middleware.return_value.assert_called_once()
    assert (
        app.middleware.return_value.call_args.args[0].func
        == async_sqla.add_session_to_request
    )
