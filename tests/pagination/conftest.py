import httpx
from asgi_lifespan import LifespanManager
from faker import Faker
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from pytest import fixture
from sqlalchemy import JSON, MetaData, Table, cast, func, select, text
from sqlalchemy.orm import joinedload, relationship


@fixture(scope="session")
def nb_users():
    return 42


@fixture(scope="session")
def nb_notes(nb_users):
    return 22 * nb_users


@fixture(scope="module", autouse=True)
def setup_tear_down(sqla_connection, nb_users, nb_notes):
    faker = Faker(seed=0)
    with sqla_connection.begin():
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
        user_params = [{"name": faker.name()}] * nb_users
        note_params = [
            {"user_id": i % 42 + 1, "content": faker.text()} for i in range(0, nb_notes)
        ]
        sqla_connection.execute(user.insert(), user_params)
        sqla_connection.execute(note.insert(), note_params)
    yield
    with sqla_connection.begin():
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

        user = relationship("User", lazy="raise")

    return Note


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
    notes: list[Note]

    class Config:
        orm_mode = True


class UserWithNotesCount(User):
    notes_count: int


class Meta(BaseModel):
    notes_count: int


class UserWithMeta(User):
    meta: Meta


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

    @app.get("/v1/users", response_model=Page[UserWithNotes])
    def sqla_13_all_users(session: Session = Depends(), paginate: Paginate = Depends()):
        query = (
            session.query(user_cls)
            .options(joinedload(user_cls.notes))
            .order_by(user_cls.id)
        )
        return paginate(query)

    @app.get("/v2/users", response_model=Page[UserWithNotes])
    def sqla_14_all_users(paginate: Paginate = Depends()):
        query = (
            select(user_cls).options(joinedload(user_cls.notes)).order_by(user_cls.id)
        )
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
                    func.format('{"notes_count": %s}', func.count(note_cls.id)), JSON
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
