from typing import Optional

import httpx
from asgi_lifespan import LifespanManager
from pytest import fixture, mark
from sqlalchemy import text

pytestmark = [mark.sqlalchemy("2.0"), mark.require_sqlmodel]


@fixture(autouse=True, scope="module")
def module_setup_tear_down(sqla_connection):
    with sqla_connection.begin():
        sqla_connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS hero (
                    id integer primary key,
                    name varchar not null,
                    secret_name varchar not null,
                    age integer
                )
                """
            )
        )
        sqla_connection.execute(
            text("INSERT INTO hero VALUES (123, 'Rusty-Man', 'Tommy Sharp', 48)")
        )
    yield
    with sqla_connection.begin():
        sqla_connection.execute(text("DROP TABLE hero"))


@fixture
def app():
    from http import HTTPStatus

    from fastapi import FastAPI, HTTPException
    from sqlmodel import Field, SQLModel, select

    from fastapi_sqla import Item, Page, Paginate, Session, setup

    class Hero(SQLModel, table=True, extend_existing=True):
        __table_args__ = {"extend_existing": True}
        id: Optional[int] = Field(default=None, primary_key=True)
        name: str
        secret_name: str
        age: Optional[int] = None

    app = FastAPI()
    setup(app)

    @app.get("/heros", response_model=Page[Hero])
    def list_hero(paginate: Paginate) -> Page[Hero]:
        return paginate(select(Hero))

    @app.get("/heros/{hero_id}", response_model=Item[Hero])
    def get_hero(hero_id: int, session: Session) -> Item[Hero]:
        hero = session.get(Hero, hero_id)
        if hero is None:
            raise HTTPException(HTTPStatus.NOT_FOUND)
        return {"data": hero}

    return app


@fixture
async def client(app):
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://example.local"
        ) as client:
            yield client


async def test_pagination(client):
    res = await client.get("/heros")

    assert res.status_code == 200, (res.status_code, res.content)
    data = res.json()["data"]
    assert len(data) == 1

    hero = data[0]
    assert hero == {
        "age": 48,
        "id": 123,
        "name": "Rusty-Man",
        "secret_name": "Tommy Sharp",
    }

    meta = res.json()["meta"]
    assert meta == {"offset": 0, "page_number": 1, "total_items": 1, "total_pages": 1}


async def test_get_item(client):
    res = await client.get("/heros/123")
    assert res.status_code == 200, (res.status_code, res.content)

    hero = res.json()["data"]
    assert hero == {
        "age": 48,
        "id": 123,
        "name": "Rusty-Man",
        "secret_name": "Tommy Sharp",
    }
