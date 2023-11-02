from unittest.mock import Mock

import httpx
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from pytest import fixture
from sqlalchemy import text


@fixture(scope="module", autouse=True)
def setup_tear_down(engine):
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS public.user (
                       id integer primary key,
                       first_name varchar,
                       last_name varchar
                    )
                    """
                )
            )
        yield
        with connection.begin():
            connection.execute(text("DROP TABLE public.user"))


@fixture
def User():
    from fastapi_sqla import Base

    class User(Base):
        __tablename__ = "user"

    return User


@fixture
def app(User):
    from fastapi_sqla import Session, SessionDependency, SqlaSession, setup

    app = FastAPI()
    setup(app)

    class UserIn(BaseModel):
        id: int
        first_name: str
        last_name: str

    @app.post("/users")
    def create_user(user: UserIn, session: Session):
        session.add(User(**dict(user)))

    @app.get("/404")
    def get_users(session: SqlaSession = Depends(SessionDependency())):
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
async def client(app, mock_middleware):
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://example.local"
        ) as client:
            yield client
