from typing import List

import httpx
from asgi_lifespan import LifespanManager
from faker import Faker
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from pytest import fixture, mark
from sqlalchemy import MetaData, Table, func
from sqlalchemy.orm import joinedload, relationship


@fixture(scope="module", autouse=True)
def setup_tear_down(engine):
    faker = Faker(seed=0)
    engine.execute(
        "create table if not exists public.user (id integer primary key, name varchar)"
    )
    engine.execute(
        """
        create table if not exists note (
            user_id integer,
            id integer,
            content text,
            primary key (user_id, id),
            foreign key (user_id) references public.user (id)
        )
    """
    )
    metadata = MetaData(bind=engine)
    user = Table("user", metadata, autoload=True, autoload_with=engine)
    note = Table("note", metadata, autoload=True, autoload_with=engine)

    user_params = []
    note_params = []
    for i in range(1, 43):
        user_params.append({"id": i, "name": faker.name()})
        note_params.extend(
            [
                {"user_id": i, "id": 1, "content": faker.text()},
                {"user_id": i, "id": 2, "content": faker.text()},
            ]
        )

    engine.execute(user.insert(), *user_params)
    engine.execute(note.insert(), *note_params)

    yield
    engine.execute("drop table note cascade")
    engine.execute("drop table public.user cascade")


@fixture
def sqla_modules(user_cls, note_cls):
    pass


@fixture(scope="module")
def user_cls(note_cls):
    from fastapi_sqla import Base

    class User(Base):
        __tablename__ = "user"

        notes = relationship("Note")

    return User


@fixture(scope="module")
def note_cls():
    from fastapi_sqla import Base

    class Note(Base):
        __tablename__ = "note"

    return Note


@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_pagination(session, user_cls, offset, limit, total_pages, page_number):
    from fastapi_sqla import with_pagination

    query = session.query(user_cls).options(joinedload("notes"))
    result = with_pagination(session, offset, limit)(query)

    assert result.meta.total_items == 42
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_new_pagination_with_custom_count(
    session, user_cls, offset, limit, total_pages, page_number
):
    from fastapi_sqla import new_pagination

    query_count = (
        lambda sess, _: session.query(user_cls)
        .statement.with_only_columns([func.count()])
        .scalar()
    )
    with_pagination = new_pagination(query_count=query_count)
    query = session.query(user_cls).options(joinedload("notes"))
    result = with_pagination(session, offset, limit)(query)

    assert result.meta.total_items == 42
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@fixture
def app(user_cls, note_cls):
    from fastapi_sqla import (
        Paginated,
        Session,
        setup,
        with_pagination,
        with_session,
    )
    from sqlalchemy.orm import joinedload

    app = FastAPI()
    setup(app)

    class Note(BaseModel):
        id: int
        content: str

    class User(BaseModel):
        id: int
        name: str
        notes: List[Note]

    @app.get("/users")
    def all_users(
        session: Session = Depends(with_session),
        paginated_result=Depends(with_pagination),
        reponse_model=Paginated[User],
    ):
        query = session.query(user_cls).options(joinedload("notes"))
        return paginated_result(query)

    return app


@fixture
async def client(app):
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            app=app, base_url="http://example.local"
        ) as client:
            yield client


@mark.asyncio
@mark.parametrize(
    "offset,items_number",
    [(0, 10), (10, 10), (40, 2)],
)
async def test_functional(client, offset, items_number):
    result = await client.get("/users", params={"offset": offset})

    assert result.status_code == 200
    users = result.json()["data"]
    assert len(users) == items_number
    user_ids = [u["id"] for u in users]
    assert user_ids == list(range(offset + 1, offset + 1 + items_number))
