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
