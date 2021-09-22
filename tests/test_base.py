from pytest import fixture, raises
from sqlalchemy import text
from sqlalchemy.exc import NoSuchTableError


@fixture(autouse=True, scope="module")
def setup_tear_down(engine):
    with engine.connect() as connection:
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS test_table (id integer primary key)")
        )
        yield
        connection.execute(text("DROP TABLE test_table"))


def test_startup_reflect_test_table():
    from fastapi_sqla import Base, _Session, startup

    class TestTable(Base):
        __tablename__ = "test_table"

    startup()

    session = _Session()
    session.add(TestTable(id=1))
    session.add(TestTable(id=2))

    assert session.query(TestTable).count() == 2


def test_startup_fails_when_table_doesnt_exist():
    from fastapi_sqla import Base, startup

    class TestTable(Base):
        __tablename__ = "does_not_exist"

    with raises(NoSuchTableError):
        startup()
