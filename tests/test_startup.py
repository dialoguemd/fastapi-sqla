import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pytest import fixture, mark


@fixture(autouse=True)
def setup_tear_down():
    from sqlalchemy.orm.session import close_all_sessions

    yield
    close_all_sessions()


def test_startup():
    from fastapi_sqla import _Session, startup

    startup()

    session = _Session()

    assert session.execute("SELECT 1").scalar() == 1


@mark.asyncio
async def test_fastapi_integration():
    from fastapi_sqla import _Session, setup

    app = FastAPI()
    setup(app)

    @app.get("/one")
    def now():
        session = _Session()
        result = session.execute("SELECT 1").scalar()
        session.close()
        return result

    async with LifespanManager(app):
        async with httpx.AsyncClient(
            app=app, base_url="http://example.local"
        ) as client:
            res = await client.get("/one")

    assert res.json() == 1
