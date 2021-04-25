from pytest import fixture, mark
from sqlalchemy import text


pytestmark = mark.usefixtures("db_migration")


@fixture(scope="session")
def alembic_ini_path():
    return "./tests/alembic.ini"


def test_it(session):
    session.execute(text("select * from testuser"))
