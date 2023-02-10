from unittest.mock import Mock, patch

import httpx
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from pytest import fixture, mark
from sqlalchemy import text
from structlog.testing import capture_logs


@fixture(scope="module", autouse=True)
def setup_tear_down(engine):
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS test_middleware_user (
                       id integer primary key,
                       first_name varchar,
                       last_name varchar
                    )
                    """
                )
            )
    yield
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("DROP TABLE test_middleware_user"))


@fixture
def User():
    from fastapi_sqla import Base

    class User(Base):
        __tablename__ = "test_middleware_user"

    return User


@fixture
def app(User):
    from fastapi_sqla import Session, setup

    try:
        from fastapi_sqla import AsyncSession
    except ImportError:
        AsyncSession = False

    app = FastAPI()
    setup(app)

    class UserIn(BaseModel):
        id: int
        first_name: str
        last_name: str

    @app.post("/users")
    def create_user(user: UserIn, session: Session = Depends()):
        session.add(User(**user.dict()))

    if AsyncSession:

        @app.post("/async/users")
        def create_user_with_async_session(
            user: UserIn, session: AsyncSession = Depends()
        ):
            session.add(User(**user.dict()))

    @app.get("/404")
    def get_users(session: Session = Depends(Session)):
        raise HTTPException(status_code=404, detail="YOLO")

    return app


@fixture
def mock_middleware(app: FastAPI):
    mock_middleware = Mock()

    @app.middleware("http")
    async def a_middleware(request, call_next):
        res = await call_next(request)
        mock_middleware()
        return res

    return mock_middleware


@fixture
async def client(app):

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://example.local"
        ) as client:
            yield client


async def test_session_dependency(client, faker, session):
    userid = faker.unique.random_int()
    first_name = faker.first_name()
    last_name = faker.last_name()
    res = await client.post(
        "/users", json={"id": userid, "first_name": first_name, "last_name": last_name}
    )
    assert res.status_code == 200, res.json()
    row = session.execute(
        text(f"select * from test_middleware_user where id = {userid}")
    ).fetchone()
    assert row == (userid, first_name, last_name)


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_async_session_dependency(client, faker, async_session):
    userid = faker.unique.random_int()
    first_name = faker.first_name()
    last_name = faker.last_name()
    res = await client.post(
        "/async/users",
        json={"id": userid, "first_name": first_name, "last_name": last_name},
    )
    assert res.status_code == 200, res.json()
    row = (
        await async_session.execute(
            text(f"select * from test_middleware_user where id = {userid}")
        )
    ).fetchone()
    assert row == (userid, first_name, last_name)


@fixture
def user_1(sqla_connection):
    with sqla_connection.begin():
        sqla_connection.execute(
            text("INSERT INTO test_middleware_user VALUES (1, 'bob', 'morane') ")
        )
    yield
    with sqla_connection.begin():
        sqla_connection.execute(text("DELETE FROM test_middleware_user WHERE id = 1"))


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
