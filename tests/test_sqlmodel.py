import httpx
from asgi_lifespan import LifespanManager
from pytest import fixture, mark

pytestmark = [mark.sqlalchemy("2.0")]


@fixture(scope="module")
def Hero():
    from sqlmodel import Field, SQLModel

    class Hero(SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str
        secret_name: str
        age: int | None = None

    return Hero


@fixture(autouse=True, scope="module")
def module_setup_tear_down(engine, Hero):
    from sqlmodel import Session, SQLModel

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Hero(name="Rusty-Man", secret_name="Tommy Sharp", age=48))
        session.commit()
    yield
    SQLModel.metadata.drop_all(engine)


@fixture
def app(Hero):
    from fastapi import FastAPI
    from fastapi_sqla import Collection, Session, setup
    from sqlmodel import select

    app = FastAPI()
    setup(app)

    @app.get("/heros", response_model=Collection[Hero])
    def list_hero(session: Session) -> Collection[Hero]:
        return {"data": session.exec(select(Hero)).all()}

    return app


@fixture
async def client(app):
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://example.local"
        ) as client:
            yield client


async def test_it(client):
    res = await client.get("/heros")

    assert res.status_code == 200, (res.status_code, res.content)
    data = res.json()["data"]
    assert len(data) == 1

    hero = data[0]
    assert hero == {
        "age": 48,
        "id": 1,
        "name": "Rusty-Man",
        "secret_name": "Tommy Sharp",
    }
