from unittest.mock import AsyncMock, Mock, patch

from pytest import fixture, mark, param

from fastapi_sqla import async_sqla, sqla


@fixture
def async_sqla_startup_mock():
    with patch("fastapi_sqla.async_sqla.startup", new=AsyncMock()) as mock:
        yield mock


@fixture
def sqla_startup_mock():
    with patch("fastapi_sqla.sqla.startup") as mock:
        yield mock


def test_setup_multiple_engines(db_url):
    from fastapi_sqla.base import setup
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
        setup(app)

    assert app.add_event_handler.call_count == 2
    assert any(
        call
        for call in app.add_event_handler.call_args_list
        if call.args[0] == "startup"
        and call.args[1].func == sqla.startup
        and call.args[1].keywords == {"key": _DEFAULT_SESSION_KEY}
    )
    assert any(
        call
        for call in app.add_event_handler.call_args_list
        if call.args[0] == "startup"
        and call.args[1].func == sqla.startup
        and call.args[1].keywords == {"key": read_only_key}
    )

    assert app.add_middleware.call_count == 2
    assert all(
        call.args[0] == sqla.SessionMiddleware
        for call in app.middleware.call_args_list
    )

    assert any(
        call
        for call in app.add_middleware.call_args_list
        if call.args[0] == sqla.SessionMiddleware
        and call.kwargs["key"] == _DEFAULT_SESSION_KEY
    )
    assert any(
        call
        for call in app.add_middleware.call_args_list
        if call.args[0] == sqla.SessionMiddleware
        and call.kwargs["key"] == read_only_key
    )


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
def test_setup_with_sync_and_async_sqlalchemy_url(async_session_key):
    from fastapi_sqla.base import setup
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    app = Mock()
    setup(app)

    assert app.add_event_handler.call_count == 2
    assert any(
        call
        for call in app.add_event_handler.call_args_list
        if call.args[0] == "startup"
        and call.args[1].func == sqla.startup
        and call.args[1].keywords == {"key": _DEFAULT_SESSION_KEY}
    )
    assert any(
        call
        for call in app.add_event_handler.call_args_list
        if call.args[0] == "startup"
        and call.args[1].func == async_sqla.startup
        and call.args[1].keywords == {"key": async_session_key}
    )

    assert app.add_middleware.call_count == 2
    assert any(
        call
        for call in app.add_middleware.call_args_list
        if call.args[0] == sqla.SessionMiddleware
        and call.kwargs["key"] == _DEFAULT_SESSION_KEY
    )
    assert any(
        call
        for call in app.add_middleware.call_args_list
        if call.args[0] == async_sqla.AsyncSessionMiddleware
        and call.kwargs["key"] == async_session_key
    )


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
def test_setup_with_async_default_sqlalchemy_url(async_sqlalchemy_url):
    from fastapi_sqla.base import setup
    from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

    app = Mock()
    with patch.dict(
        "os.environ", values={"sqlalchemy_url": async_sqlalchemy_url}, clear=True
    ):
        setup(app)

    app.add_event_handler.assert_called_once()
    assert app.add_event_handler.call_args.args[0] == "startup"
    assert app.add_event_handler.call_args.args[1].func == async_sqla.startup
    assert app.add_event_handler.call_args.args[1].keywords == {
        "key": _DEFAULT_SESSION_KEY
    }

    app.add_middleware.assert_called_once()
    assert (
        app.add_middleware.call_args.args[0]
        == async_sqla.AsyncSessionMiddleware
    )
    assert app.add_middleware.call_args.kwargs["key"] == _DEFAULT_SESSION_KEY


@mark.parametrize(
    "env_vars, expected_keys",
    [
        param([], {"default"}, id="default always present"),
        param(
            [
                "potato",
                "sqlalchemy__potato__url",
                "fastapi_sqla_potato_url",
                "fastapi_sqla_potato__url",
                "fastapi_sqla__potato_url",
                "fastapi_sqla__potato___url",
                "fastapi_sqla___potato__url",
                "fastapi_sqla___potato___url",
                "fastapi_sqla____url",
            ],
            {"default"},
            id="invalid formats",
        ),
        param(
            ["fastapi_sqla__potato__url", "fastapi_sqla__tomato__url"],
            {"default", "potato", "tomato"},
            id="valid formats",
        ),
        param(
            [
                "fastapi_sqla__read_only__url",
                "fastapi_sqla__read-only__url",
                "fastapi_sqla__potato__pre_ping",
            ],
            {"default", "read_only", "read-only", "potato"},
            id="valid format with underscore or dashes",
        ),
    ],
)
def test_get_engine_keys(env_vars, expected_keys):
    from fastapi_sqla.base import _get_engine_keys

    env_vars = {var: "test" for var in env_vars}
    with patch.dict("os.environ", values=env_vars, clear=True):
        assert _get_engine_keys() == expected_keys
