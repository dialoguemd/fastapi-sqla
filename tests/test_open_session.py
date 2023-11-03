from pytest import fixture, mark, raises
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError


@fixture(autouse=True, scope="module")
def module_setup_tear_down(sqla_connection):
    with sqla_connection.begin():
        sqla_connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS test_table   "
                "(id integer primary key, value varchar) "
            )
        )
    yield
    with sqla_connection.begin():
        sqla_connection.execute(text("DROP TABLE test_table"))


@fixture(scope="module")
def test_table_cls():
    from fastapi_sqla import Base
    from fastapi_sqla.sqla import startup

    class TestTable(Base):
        __tablename__ = "test_table"

    startup()

    return TestTable


@fixture
def startup(sqla_connection):
    from fastapi_sqla.sqla import _Session, startup

    startup()
    _Session.configure(bind=sqla_connection)


@fixture
async def async_startup(async_sqla_connection):
    from fastapi_sqla.async_sqla import _AsyncSession, startup

    await startup()
    _AsyncSession.configure(bind=async_sqla_connection)


@mark.sqlalchemy("1.4")
def test_open_session(startup):
    from fastapi_sqla.sqla import open_session

    with open_session() as session:
        res = session.execute(select(text("'OK'"))).scalar()

    assert res == "OK"


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
async def test_open_async_session(async_startup):
    from fastapi_sqla.async_sqla import open_session

    async with open_session() as session:
        res = await session.execute(text("select 123"))

    assert res.scalar() == 123


@mark.sqlalchemy("1.4")
def test_open_session_rollback_when_error_occurs_in_context(startup, test_table_cls):
    from fastapi_sqla.sqla import open_session

    error = Exception("Error in context")

    class Custom(Exception):
        pass

    with raises(Exception) as raise_info:
        with open_session() as session:
            session.execute(
                insert(test_table_cls).values(id=1, value="bobby drop tables")
            )
            raise error

    assert raise_info.value == error

    res = session.execute(select(test_table_cls)).fetchall()
    assert res == [], "insert has not been rolled back"


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
async def test_open_async_session_rollback_when_error_occurs_in_context(
    async_startup, test_table_cls
):
    from fastapi_sqla.async_sqla import open_session

    error = Exception("Error in context")

    with raises(Exception) as raise_info:
        async with open_session() as session:
            await session.execute(
                insert(test_table_cls).values(id=1, value="bobby drop tables")
            )
            raise error

    assert raise_info.value == error

    res = (await session.execute(select(test_table_cls))).fetchall()
    assert res == [], "insert has not been rolled back"


def test_open_session_re_raise_exception_when_commit_fails(
    startup, test_table_cls, session
):
    from fastapi_sqla.sqla import open_session

    existing_record_id = 1
    session.execute(
        insert(test_table_cls).values(
            id=existing_record_id, value="bob morane was there."
        )
    )
    session.flush()

    with raises(Exception) as raise_info:
        with open_session() as session:
            session.add(
                test_table_cls(id=existing_record_id, value="bobby already exists")
            )

    assert isinstance(raise_info.value, IntegrityError)


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
async def test_open_async_session_re_raise_exception_when_commit_fails(
    async_startup, test_table_cls, async_session
):
    from fastapi_sqla.async_sqla import open_session

    existing_record_id = 1
    await async_session.execute(
        insert(test_table_cls).values(
            id=existing_record_id, value="bob morane was there."
        )
    )
    await async_session.flush()

    with raises(Exception) as raise_info:
        async with open_session() as session:
            session.add(
                test_table_cls(id=existing_record_id, value="bobby already exists")
            )

    assert isinstance(raise_info.value, IntegrityError)
