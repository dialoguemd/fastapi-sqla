from fastapi import Depends, FastAPI, HTTPException
from pytest import fixture, mark
from sqlalchemy import select

pytestmark = [mark.sqlalchemy("1.4"), mark.require_asyncpg]


@fixture(
    autouse=True,
    params=[
        {"sqlalchemy_url": "async_sqlalchemy_url"},
        {"sqlalchemy_url": "db_url", "async_sqlalchemy_url": "async_sqlalchemy_url"},
    ],
)
def override_environ(setup_tear_down, async_sqlalchemy_url, monkeypatch, request):
    """Override environ to test the 2 cases.

    In async mode, 2 environ are possible:
    - Only sqlalchemy_url envvar is defined with an async driver
    - Both sqlalchemy_url and async_sqlalchemy_url are defined
        * sqlalchemy_url with a sync driver;
        * async_sqlalchemy_url with an async one;

    This fixture allows testing in both case.
    """
    monkeypatch.delenv("sqlalchemy_url")
    monkeypatch.delenv("async_sqlalchemy_url")
    monkeypatch.setenv("sqlalchemy_url", async_sqlalchemy_url)

    for envvar, fixture_name in request.param.items():
        monkeypatch.setenv(envvar, request.getfixturevalue(fixture_name))


@fixture
def app(sqla, model):
    from fastapi_sqla import AsyncPaginate, AsyncSession, Item, Page, setup

    app = FastAPI()
    setup(app)

    @app.post("/users", response_model=Item[model.User], status_code=201)
    async def create_user(user: model.UserIn, session: AsyncSession = Depends()):
        new_user = sqla.User(**user.dict())
        session.add(new_user)
        await session.flush()
        return {"data": new_user}

    @app.get("/users/{id}", response_model=Item[model.User])
    async def get_user(id: int, session: AsyncSession = Depends()):
        user = await session.get(sqla.User, id)
        if user is None:
            raise HTTPException(404)
        return {"data": user}

    @app.get("/users", response_model=Page[model.User])
    async def list_users(paginate: AsyncPaginate = Depends()):
        return await paginate(select(sqla.User))

    return app


async def test_create_user(client, async_session, sqla):
    res = await client.post(
        "/users", json={"first_name": "Jacob", "last_name": "Miller"}
    )
    assert res.status_code == 201, (res.status_code, res.content)
    data = res.json()["data"]
    user = await async_session.get(sqla.User, data["id"])
    assert user is not None


async def test_get_user(client, async_session, sqla):
    user = (await async_session.execute(select(sqla.User).limit(1))).scalar()
    res = await client.get(f"/users/{user.id}")
    assert res.status_code == 200, (res.status_code, res.content)


async def test_list_users(client, async_session, sqla):
    res = await client.get("/users")
    assert res.status_code == 200, (res.status_code, res.content)
