import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI, Depends, Body
from pytest import fixture, mark
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import close_all_sessions


pytestmark = mark.asyncio


@fixture(autouse=True)
def setup_tear_down(environ):
    engine = engine_from_config(environ, prefix="sqlalchemy_")

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
async def client(User):

    import fastapi_sqla

    app = FastAPI()

    app.include_router(fastapi_sqla.router)
    app.middleware("http")(fastapi_sqla.middleware)

    @app.post("/users")
    def create_user(request: Request, session=Depends(fastapi_sqla.with_session)):
        # fmt: off
        import pdb; pdb.set_trace()
        # fmt: on
        session.add(User(**body))
        return body

    async with LifespanManager(app):
        async with httpx.AsyncClient(
            app=app, base_url="http://example.local"
        ) as client:
            yield client


async def test_session_dependency(client):
    res = await client.post(
        "/users", json={"id": 1, "first_name": "Bob", "last_name": "Morane"}
    )
    assert res.status_code == 200
