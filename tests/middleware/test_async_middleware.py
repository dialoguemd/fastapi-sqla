from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from pytest import fixture, mark
from sqlalchemy import text
from structlog.testing import capture_logs

pytestmark = [mark.sqlalchemy("1.4"), mark.require_asyncpg]


@fixture
def app(User, monkeypatch, async_sqlalchemy_url, async_session_key):
    from contextlib import asynccontextmanager

    from fastapi_sqla import (
        AsyncSession,
        AsyncSessionDependency,
        SqlaAsyncSession,
        setup_middlewares,
        startup,
    )

    monkeypatch.setenv("sqlalchemy_url", async_sqlalchemy_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await startup()
        yield

    app = FastAPI(lifespan=lifespan)
    setup_middlewares(app)

    class UserIn(BaseModel):
        id: int
        first_name: str
        last_name: str

    @app.post("/users")
    def create_user(user: UserIn, session: AsyncSession):
        session.add(User(**dict(user)))

    @app.get("/404")
    def get_users(
        session: SqlaAsyncSession = Depends(
            AsyncSessionDependency(key=async_session_key)
        ),
    ):
        raise HTTPException(status_code=404, detail="YOLO")

    @app.get("/unknown_session_key")
    def unknown_session_key(
        session: SqlaAsyncSession = Depends(AsyncSessionDependency(key="unknown")),
    ):
        return "Shouldn't return"

    return app


async def test_async_session_dependency(client, faker, async_session):
    userid = faker.unique.random_int()
    first_name = faker.first_name()
    last_name = faker.last_name()
    res = await client.post(
        "/users", json={"id": userid, "first_name": first_name, "last_name": last_name}
    )
    assert res.status_code == 200, res.json()
    row = (
        await async_session.execute(
            text(f"select * from public.user where id = {userid}")
        )
    ).fetchone()
    assert row == (userid, first_name, last_name)


@fixture
async def user_1(async_sqla_connection):
    async with async_sqla_connection.begin():
        await async_sqla_connection.execute(
            text("INSERT INTO public.user VALUES (1, 'bob', 'morane') ")
        )
    yield
    async with async_sqla_connection.begin():
        await async_sqla_connection.execute(
            text("DELETE FROM public.user WHERE id = 1")
        )


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


async def test_all_sessions_rollback_on_http_exception(client, mock_middleware):
    with patch("fastapi_sqla.async_sqla.open_session") as open_session:
        session = open_session.return_value.__aenter__.return_value

        await client.get("/404")

        # Default and custom session are rolled back
        assert session.rollback.await_count == 2
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


async def test_async_session_dependency_raises_unknown_key(client):
    with capture_logs() as caplog:
        res = await client.get("/unknown_session_key")

    assert res.status_code == 500

    assert {
        "event": "No async session with key 'unknown' found in request, "
        "please ensure you've setup fastapi_sqla.",
        "log_level": "error",
        "exc_info": True,
        "session_key": "unknown",
    } in caplog
