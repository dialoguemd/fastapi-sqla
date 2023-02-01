from pytest import fixture, mark, raises
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
    from fastapi_sqla.sqla import Base, _Session, startup

    class TestTable(Base):
        __tablename__ = "test_table"

    startup()

    session = _Session()
    session.add(TestTable(id=1))
    session.add(TestTable(id=2))

    assert session.query(TestTable).count() == 2


@mark.sqlalchemy("1.3")
@mark.sqlalchemy("1.4")
def test_startup_fails_when_table_doesnt_exist(sqla_version_tuple):
    from sqlalchemy.exc import NoSuchTableError
    from fastapi_sqla.sqla import Base, startup

    class TestTable(Base):
        __tablename__ = "does_not_exist"

    with raises(NoSuchTableError):
        startup()


@mark.sqlalchemy("2.0")
def test_startup_fails_when_table_doesnt_exist_sqla_20(sqla_version_tuple):
    from sqlalchemy.exc import InvalidRequestError
    from fastapi_sqla.sqla import Base, startup

    class TestTable(Base):
        __tablename__ = "does_not_exist"

    with raises(InvalidRequestError):
        startup()
