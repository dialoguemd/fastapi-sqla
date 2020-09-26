import httpx
from asgi_lifespan import LifespanManager
from pytest import fixture, mark
from sqlalchemy.orm.session import close_all_sessions


@fixture(autouse=True)
def setup_tear_down():
    from fastapi_sqla import _Session

    yield
    _Session.configure(bind=None)
    close_all_sessions()


def test_startup():
    from fastapi_sqla import _Session, startup

    startup()

    session = _Session()

    assert session.execute("SELECT 1").scalar() == 1


@mark.asyncio
async def test_fastapi_integration():
    from fastapi import FastAPI

    from fastapi_sqla import _Session, router

    app = FastAPI()

    app.include_router(router)

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
