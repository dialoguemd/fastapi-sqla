from pytest import fixture, mark

pytestmark = mark.usefixtures("db_migration")


@fixture(scope="session")
def alembic_ini_path():
    return "./tests/alembic.ini"


def test_it(session):
    session.execute("select * from testuser")
