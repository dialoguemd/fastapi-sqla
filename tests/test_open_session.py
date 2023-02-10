from pytest import fixture, mark, raises
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError


@fixture(autouse=True, scope="module")
def module_setup_tear_down(engine, sqla_connection):
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


@fixture(autouse=True)
def setup(sqla_connection):
    from fastapi_sqla.sqla import _Session

    _Session.configure(bind=sqla_connection)


@fixture
def TestTable(module_setup_tear_down):
    from fastapi_sqla.sqla import Base, startup

    class TestTable(Base):
        __tablename__ = "test_table"

    startup()

    return TestTable


@mark.sqlalchemy("1.4")
def test_open_session():
    from fastapi_sqla import open_session

    with open_session() as session:
        res = session.execute(select(text("'OK'"))).scalar()

    assert res == "OK"


@mark.sqlalchemy("1.4")
def test_open_session_rollback_when_error_occurs_in_context(TestTable, session):
    from fastapi_sqla import open_session

    error = Exception("Error in context")

    class Custom(Exception):
        pass

    with raises(Exception) as raise_info:
        with open_session() as session:
            session.execute(insert(TestTable).values(id=1, value="bobby drop tables"))
            raise error

    assert raise_info.value == error

    res = session.execute(select(TestTable)).fetchall()
    assert res == [], "insert has not been rolled back"


@fixture
def existing_record(TestTable, session):
    id = 1
    session.execute(insert(TestTable).values(id=id, value="bob morane was there."))
    session.flush()
    yield (1, "bob morane was there.")


def test_open_session_re_raise_exception_when_commit_fails(
    TestTable, existing_record, session
):
    from fastapi_sqla import open_session

    with raises(Exception) as raise_info:
        with open_session() as session:
            session.add(TestTable(id=1, value="bobby already exists"))

    assert isinstance(raise_info.value, IntegrityError)
