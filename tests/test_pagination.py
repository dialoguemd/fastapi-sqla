from typing import List

import httpx
from asgi_lifespan import LifespanManager
from faker import Faker
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from pytest import fixture, mark, param
from sqlalchemy import JSON, MetaData, Table, cast, func, select, text
from sqlalchemy.orm import joinedload, relationship


@fixture(scope="module", autouse=True)
def setup_tear_down(sqla_connection):
    faker = Faker(seed=0)
    sqla_connection.execute(
        text(
            "create table if not exists public.user "
            "(id serial primary key, name varchar)"
        )
    )
    sqla_connection.execute(
        text(
            """
        create table if not exists note (
            user_id integer,
            id serial,
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
    user_params = [{"name": faker.name()} for _ in range(1, 43)]
    note_params = [
        {"user_id": i % 42 + 1, "content": faker.text()} for i in range(0, 22 * 42)
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

        class Config:
            orm_mode = True

    class UserWithNotes(User):
        notes: List[Note]

        class Config:
            orm_mode = True

    class UserWithNotesCount(User):
        notes_count: int

    class Meta(BaseModel):
        notes_count: int

    class UserWithMeta(User):
        meta: Meta

    @app.get("/v1/users", response_model=Page[UserWithNotes])
    def sqla_13_all_users(session: Session = Depends(), paginate: Paginate = Depends()):
        query = (
            session.query(user_cls).options(joinedload("notes")).order_by(user_cls.id)
        )
        return paginate(query)

    @app.get("/v2/users", response_model=Page[UserWithNotes])
    def sqla_14_all_users(paginate: Paginate = Depends()):
        query = select(user_cls).options(joinedload("notes")).order_by(user_cls.id)
        return paginate(query)

    @app.get("/v2/users-with-notes-count", response_model=Page[UserWithNotesCount])
    def sqla_14_all_users_with_notes_count(paginate: Paginate = Depends()):
        query = (
            select(
                user_cls.id, user_cls.name, func.count(note_cls.id).label("notes_count")
            )
            .join(note_cls)
            .order_by(user_cls.id)
            .group_by(user_cls)
        )
        return paginate(query, scalars=False)

    @app.get("/v2/query-with-json-result", response_model=Page[UserWithMeta])
    def query_with_JSON_result(paginate: Paginate = Depends()):
        query = (
            select(
                user_cls.id,
                user_cls.name,
                cast(
                    func.format('{"notes_count": %s}', func.count(note_cls.id)),
                    JSON,
                ).label("meta"),
            )
            .join(note_cls)
            .order_by(user_cls.id)
            .group_by(user_cls)
        )
        return paginate(query, scalars=False)

    def count_user_notes(user_id: int, session: Session = Depends()) -> int:
        return session.execute(
            select(func.count(note_cls.id)).where(note_cls.user_id == user_id)
        ).scalar()

    CustomPaginate: PaginateSignature = Pagination(query_count=count_user_notes)

    @app.get("/v2/users/{user_id}/notes", response_model=Page[Note])
    def list_user_notes_with_custom_pagination(
        user_id: int, paginate: CustomPaginate = Depends()
    ):
        return paginate(select(note_cls).where(note_cls.user_id == user_id))

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
    "offset,items_number,path",
    [
        param(0, 10, "/v1/users"),
        param(10, 10, "/v1/users"),
        param(40, 2, "/v1/users"),
        param(0, 10, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(40, 2, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(0, 10, "/v2/users-with-notes-count", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/users-with-notes-count", marks=mark.sqlalchemy("1.4")),
        param(40, 2, "/v2/users-with-notes-count", marks=mark.sqlalchemy("1.4")),
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


@mark.asyncio
@mark.parametrize(
    "offset,items_number,path",
    [
        param(0, 10, "/v2/users/1/notes", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/users/1/notes", marks=mark.sqlalchemy("1.4")),
        param(20, 2, "/v2/users/1/notes", marks=mark.sqlalchemy("1.4")),
    ],
)
async def test_custom_pagination(client, offset, items_number, path):
    result = await client.get(path, params={"offset": offset})

    assert result.status_code == 200, result.json()
    notes = result.json()["data"]
    assert len(notes) == items_number

    meta = result.json()["meta"]
    assert meta["total_items"] == 22


@mark.asyncio
@mark.sqlalchemy("1.4")
async def test_json_result(client):
    result = await client.get("/v2/query-with-json-result")

    assert result.status_code == 200, result.json()
