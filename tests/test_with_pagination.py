from pytest import fixture, mark
from sqlalchemy.orm import joinedload, relationship


@fixture(scope="module", autouse=True)
def setup_tear_down(engine):
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
    yield
    engine.execute("drop table note")
    engine.execute("drop table public.user")


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


@fixture(autouse=True)
def tons_of_users(session, user_cls, note_cls, faker):
    for i in range(1, 43):
        session.add(
            user_cls(
                id=i, name=faker.name(), notes=[note_cls(id=i, content=faker.text())]
            )
        )
    session.commit()


@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_pagination(
    session, user_cls, note_cls, offset, limit, total_pages, page_number
):
    from fastapi_sqla import with_pagination

    query = session.query(user_cls).options(joinedload("notes"))
    result = with_pagination(offset, limit)(query)

    assert result.meta.total_items == 42
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number
