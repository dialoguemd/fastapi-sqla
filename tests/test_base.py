from pytest import fixture, raises
from sqlalchemy import engine_from_config
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.orm.session import close_all_sessions


@fixture(autouse=True)
def setup_tear_down(environ):
    engine = engine_from_config(environ, prefix="sqlalchemy_")

    engine.execute("CREATE TABLE IF NOT EXISTS test_table (id integer primary key)")
    yield
    close_all_sessions()
    engine.execute("DROP TABLE test_table")


def test_startup_reflect_test_table():
    from fastapi_sqla import Base, _Session, startup

    class TestTable(Base):
        __tablename__ = "test_table"

    startup()

    session = _Session()
    session.add(TestTable(id=1))
    session.add(TestTable(id=2))
    session.commit()

    assert session.query(TestTable).count() == 2


def test_startup_fails_when_table_doesnt_exist():
    from fastapi_sqla import Base, startup

    class TestTable(Base):
        __tablename__ = "does_not_exist"

    with raises(NoSuchTableError):
        startup()
