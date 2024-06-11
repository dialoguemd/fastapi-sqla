from unittest.mock import Mock, patch

from pytest import mark

from fastapi_sqla import async_sqla, sqla


def test_setup_middlewares_multiple_engines(db_url):
    from fastapi_sqla.base import setup_middlewares
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    read_only_key = "read_only"

    app = Mock()
    with patch.dict(
        "os.environ",
        values={
            "sqlalchemy_url": db_url,
            f"fastapi_sqla__{read_only_key}__sqlalchemy_url": db_url,
        },
        clear=True,
    ):
        setup_middlewares(app)

    assert app.middleware.call_count == 2
    assert all(call.args[0] == "http" for call in app.middleware.call_args_list)

    assert app.middleware.return_value.call_count == 2
    assert any(
        call
        for call in app.middleware.return_value.call_args_list
        if call.args[0].func == sqla.add_session_to_request
        and call.args[0].keywords == {"key": _DEFAULT_SESSION_KEY}
    )
    assert any(
        call
        for call in app.middleware.return_value.call_args_list
        if call.args[0].func == sqla.add_session_to_request
        and call.args[0].keywords == {"key": read_only_key}
    )


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
def test_setup_middlewares_with_sync_and_async_sqlalchemy_url(async_session_key):
    from fastapi_sqla.base import setup_middlewares
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    app = Mock()
    setup_middlewares(app)

    assert app.middleware.call_count == 2
    assert all(call.args[0] == "http" for call in app.middleware.call_args_list)

    assert app.middleware.return_value.call_count == 2
    assert any(
        call
        for call in app.middleware.return_value.call_args_list
        if call.args[0].func == sqla.add_session_to_request
        and call.args[0].keywords == {"key": _DEFAULT_SESSION_KEY}
    )
    assert any(
        call
        for call in app.middleware.return_value.call_args_list
        if call.args[0].func == async_sqla.add_session_to_request
        and call.args[0].keywords == {"key": async_session_key}
    )


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
def test_setup_middlewares_with_async_default_sqlalchemy_url(async_sqlalchemy_url):
    from fastapi_sqla.base import setup_middlewares
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    app = Mock()
    with patch.dict(
        "os.environ", values={"sqlalchemy_url": async_sqlalchemy_url}, clear=True
    ):
        setup_middlewares(app)

    app.middleware.assert_called_once_with("http")
    app.middleware.return_value.assert_called_once()
    assert (
        app.middleware.return_value.call_args.args[0].func
        == async_sqla.add_session_to_request
    )
    assert app.middleware.return_value.call_args.args[0].keywords == {
        "key": _DEFAULT_SESSION_KEY
    }
