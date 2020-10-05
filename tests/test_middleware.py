from unittest.mock import patch

import httpx
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from pytest import fixture, mark
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import close_all_sessions
from structlog.testing import capture_logs

pytestmark = mark.asyncio


@fixture
def engine(environ):
    engine = engine_from_config(environ, prefix="sqlalchemy_")
    return engine


@fixture(autouse=True)
def setup_tear_down(engine):
    engine.execute(
        """
        CREATE TABLE IF NOT EXISTS public.user (
           id integer primary key,
           first_name varchar,
           last_name varchar
        )
    """
    )
    yield
    close_all_sessions()
    engine.execute("DROP TABLE public.user")


@fixture
def User():
    from fastapi_sqla import Base

    class User(Base):
        __tablename__ = "user"

    return User


@fixture
def app(User):
    from fastapi_sqla import setup, with_session

    app = FastAPI()
    setup(app)

    class UserIn(BaseModel):
        id: int
        first_name: str
        last_name: str

    @app.post("/400")
    def raise_http_exception(session=Depends(with_session)):
        raise HTTPException(status_code=400)

    @app.post("/users")
    def create_user(user: UserIn, session=Depends(with_session)):
        session.add(User(**user.dict()))
        return {}

    return app


@fixture
async def client(app):

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://example.local"
        ) as client:
            yield client


async def test_session_dependency(client):
    res = await client.post(
        "/users", json={"id": 1, "first_name": "Bob", "last_name": "Morane"}
    )
    assert res.status_code == 200


@fixture
def user_1(engine):
    engine.execute("INSERT INTO public.user VALUES (1, 'bob', 'morane') ")
    yield


async def test_commit_error_returns_500(client, user_1):
    with capture_logs() as caplog:
        res = await client.post(
            "/users", json={"id": 1, "first_name": "Bob", "last_name": "Morane"}
        )

    assert res.status_code == 500
    assert {"event": "commit failed", "log_level": "exception"} in caplog


async def test_rollback_on_http_exception(client):
    with patch("fastapi_sqla._Session") as _Session:
        session = _Session.return_value

        await client.post("/400")

        assert session.commit.called is False
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()
