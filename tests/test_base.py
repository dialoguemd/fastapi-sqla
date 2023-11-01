from pytest import fixture, raises
from sqlalchemy import text


@fixture(autouse=True, scope="module")
def setup_tear_down(engine):
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text("CREATE TABLE IF NOT EXISTS test_table (id integer primary key)")
            )
        yield
        with connection.begin():
            connection.execute(text("DROP TABLE test_table"))


def test_startup_reflect_test_table():
    from fastapi_sqla.models import Base
    from fastapi_sqla.sqla import _Session, startup

    class TestTable(Base):
        __tablename__ = "test_table"

    startup()

    session = _Session()
    session.add(TestTable(id=1))
    session.add(TestTable(id=2))

    assert session.query(TestTable).count() == 2


@fixture
def expected_error(sqla_version_tuple):
    if sqla_version_tuple <= (1, 4):
        from sqlalchemy.exc import NoSuchTableError

        error_cls = NoSuchTableError
    else:
        from sqlalchemy.exc import InvalidRequestError

        error_cls = InvalidRequestError
    return error_cls


def test_startup_fails_when_table_doesnt_exist(expected_error):
    from fastapi_sqla.models import Base
    from fastapi_sqla.sqla import startup

    class TestTable(Base):
        __tablename__ = "does_not_exist"

    with raises(expected_error):
        startup()
