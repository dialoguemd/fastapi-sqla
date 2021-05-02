import math
from typing import List

import httpx
from asgi_lifespan import LifespanManager
from faker import Faker
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from pytest import fixture, mark, param
from sqlalchemy import MetaData, Table, func, select, text
from sqlalchemy.orm import joinedload, relationship
from sqlalchemy.sql import Select


@fixture(scope="module", autouse=True)
def setup_tear_down(sqla_connection):
    faker = Faker(seed=0)
    sqla_connection.execute(
        text(
            "create table if not exists public.user "
            "(id integer primary key, name varchar)"
        )
    )
    sqla_connection.execute(
        text(
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
    )
    metadata = MetaData()
    user = Table("user", metadata, autoload_with=sqla_connection)
    note = Table("note", metadata, autoload_with=sqla_connection)
    user_params = [{"id": i, "name": faker.name()} for i in range(1, 43)]
    note_params = [
        {"user_id": i % 42 + 1, "id": math.ceil(i / 42), "content": faker.text()}
        for i in range(0, 84)
    ]
    sqla_connection.execute(user.insert(), *user_params)
    sqla_connection.execute(note.insert(), *note_params)
    yield
    sqla_connection.execute(text("drop table note cascade"))
    sqla_connection.execute(text("drop table public.user cascade"))


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
    from fastapi_sqla import Paginate

    query = session.query(user_cls).options(joinedload("notes"))
    result = Paginate(session, offset, limit)(query)

    assert result.meta.total_items == 42
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@mark.sqlalchemy("1.3")
@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_pagination_with_legacy_query_count(
    session, user_cls, offset, limit, total_pages, page_number
):
    from fastapi_sqla import Paginate

    query = session.query(user_cls).options(joinedload("notes"))
    result = Paginate(session, offset, limit)(query)

    assert result.meta.total_items == 42
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@mark.sqlalchemy("1.3")
@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_Pagination_with_custom_sqla13_compliant_count(
    session, user_cls, offset, limit, total_pages, page_number
):
    from fastapi_sqla import DbQuery, Pagination, Session

    def query_count(session: Session, query: DbQuery) -> int:
        return (
            session.query(user_cls).statement.with_only_columns([func.count()]).scalar()
        )

    pagination = Pagination(query_count=query_count)
    query = session.query(user_cls).options(joinedload("notes"))
    result = pagination(session, offset, limit)(query)

    assert result.meta.total_items == 42
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@mark.sqlalchemy("1.4")
@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_Pagination_with_custom_sqla14_compliant_count(
    session, user_cls, offset, limit, total_pages, page_number
):
    from fastapi_sqla import DbQuery, Pagination, Session

    def query_count(session: Session, query: DbQuery) -> int:
        return session.execute(select(func.count(user_cls.id))).scalar()

    pagination = Pagination(query_count=query_count)
    query = session.query(user_cls).options(joinedload("notes"))
    result = pagination(session, offset, limit)(query)

    assert result.meta.total_items == 42
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@fixture
def app(user_cls, note_cls):
    from fastapi_sqla import (
        Page,
        Paginate,
        PaginateSignature,
        Pagination,
        Session,
        setup,
    )

    app = FastAPI()
    setup(app)

    class Note(BaseModel):
        id: int
        content: str

        class Config:
            orm_mode = True

    class User(BaseModel):
        id: int
        name: str
        notes: List[Note]

        class Config:
            orm_mode = True

    @app.get("/v1/users", response_model=Page[User])
    def sqla_13_all_users(session: Session = Depends(), paginate: Paginate = Depends()):
        query = (
            session.query(user_cls).options(joinedload("notes")).order_by(user_cls.id)
        )
        return paginate(query)

    @app.get("/v2/users", response_model=Page[User])
    def sqla_14_all_users(paginate: Paginate = Depends()):
        query = select(user_cls).options(joinedload("notes")).order_by(user_cls.id)
        return paginate(query)

    def query_count(session: Session, query: Select) -> int:
        return session.execute(select(func.count()).select_from(user_cls)).scalar()

    CustomPaginate: PaginateSignature = Pagination(query_count=query_count)

    @app.get("/v2/custom/users", response_model=Page[User])
    def sqla_14_all_users_custom_pagination(paginate: CustomPaginate = Depends()):
        query = select(user_cls).options(joinedload("notes")).order_by(user_cls.id)
        return paginate(query)

    return app


@fixture
async def client(app):
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            app=app, base_url="http://example.local"
        ) as client:
            yield client


@mark.require_asyncpg
@mark.asyncio
@mark.parametrize(
    "offset,items_number,path",
    [
        param(0, 10, "/v1/users"),
        param(10, 10, "/v1/users"),
        param(40, 2, "/v1/users"),
        param(0, 10, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(40, 2, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(0, 10, "/v2/custom/users", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/custom/users", marks=mark.sqlalchemy("1.4")),
        param(40, 2, "/v2/custom/users", marks=mark.sqlalchemy("1.4")),
    ],
)
async def test_functional(client, offset, items_number, path):
    result = await client.get(path, params={"offset": offset})

    assert result.status_code == 200, result.json()
    users = result.json()["data"]
    assert len(users) == items_number
    user_ids = [u["id"] for u in users]
    assert user_ids == list(range(offset + 1, offset + 1 + items_number))

    meta = result.json()["meta"]
    assert meta["total_items"] == 42
