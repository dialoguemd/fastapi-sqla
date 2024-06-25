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

    assert app.add_middleware.call_count == 2
    assert all(
        call.args[0] == sqla.SessionMiddleware
        for call in app.add_middleware.call_args_list
    )

    app.add_middleware.assert_any_call(sqla.SessionMiddleware, key=_DEFAULT_SESSION_KEY)
    app.add_middleware.assert_any_call(sqla.SessionMiddleware, key=read_only_key)


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
def test_setup_middlewares_with_sync_and_async_sqlalchemy_url(async_session_key):
    from fastapi_sqla.base import setup_middlewares
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    app = Mock()
    setup_middlewares(app)

    assert app.add_middleware.call_count == 2
    app.add_middleware.assert_any_call(sqla.SessionMiddleware, key=_DEFAULT_SESSION_KEY)
    app.add_middleware.assert_any_call(
        async_sqla.AsyncSessionMiddleware, key=async_session_key
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

    app.add_middleware.assert_called_once_with(
        async_sqla.AsyncSessionMiddleware, key=_DEFAULT_SESSION_KEY
    )
