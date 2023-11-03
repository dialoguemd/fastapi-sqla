from unittest.mock import patch

from pytest import fixture, mark
from sqlalchemy import text
from structlog.testing import capture_logs


async def test_session_dependency(client, faker, session):
    userid = faker.unique.random_int()
    first_name = faker.first_name()
    last_name = faker.last_name()
    res = await client.post(
        "/users", json={"id": userid, "first_name": first_name, "last_name": last_name}
    )
    assert res.status_code == 200, res.json()
    row = session.execute(
        text(f"select * from public.user where id = {userid}")
    ).fetchone()
    assert row == (userid, first_name, last_name)


@fixture
def user_1(sqla_connection):
    with sqla_connection.begin():
        sqla_connection.execute(
            text("INSERT INTO public.user VALUES (1, 'bob', 'morane') ")
        )
    yield
    with sqla_connection.begin():
        sqla_connection.execute(text("DELETE FROM public.user WHERE id = 1"))


async def test_commit_error_returns_500(client, user_1, mock_middleware):
    with capture_logs() as caplog:
        res = await client.post(
            "/users",
            json={"id": 1, "first_name": "Bob", "last_name": "Morane"},
            headers={"origin": "localhost"},
        )

    assert res.status_code == 500

    assert {
        "event": "commit failed, returning http error",
        "exc_info": True,
        "log_level": "error",
    } in caplog

    assert {
        "event": "http error, rolling back possibly uncommitted changes",
        "log_level": "warning",
        "status_code": 500,
    } in caplog

    mock_middleware.assert_called_once()


async def test_rollback_on_http_exception(client, mock_middleware):
    with patch("fastapi_sqla.sqla.open_session") as open_session:
        session = open_session.return_value.__enter__.return_value

        await client.get("/404")

        session.rollback.assert_called_once_with()
        mock_middleware.assert_called_once()


async def test_rollback_on_http_exception_silent(client, mock_middleware):
    with capture_logs() as caplog:
        await client.get("/404")

    mock_middleware.assert_called_once()

    assert {
        "event": "http error, rolling back possibly uncommitted changes",
        "log_level": "warning",
        "status_code": 404,
    } not in caplog
