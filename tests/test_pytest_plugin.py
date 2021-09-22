from pytest import fixture, mark
from sqlalchemy import text


@fixture(scope="module", autouse=True)
def setup_tear_down(sqla_connection):
    sqla_connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS singer (
               id integer primary key,
               name varchar,
               country varchar
            )
        """
        )
    )
    yield
    sqla_connection.execute(text("DROP TABLE singer"))


@fixture
def singer_cls():
    from fastapi_sqla import Base

    class Singer(Base):
        __tablename__ = "singer"

    return Singer


@fixture
def sqla_modules(singer_cls):
    pass


def test_session_fixture_does_not_write_in_db(session, singer_cls, engine):
    session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    session.commit()
    with engine.connect() as connection:
        assert connection.execute(text("select count(*) from singer")).scalar() == 0


@mark.require_asyncpg
@mark.asyncio
@mark.sqlalchemy("1.4")
async def test_async_session_fixture_does_not_write_in_db(
    async_session, singer_cls, async_engine, session
):
    async_session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    await async_session.commit()
    async with async_engine.connect() as connection:
        assert (
            await connection.execute(text("select count(*) from singer"))
        ).scalar() == 0


def test_all_opened_sessions_are_within_the_same_transaction(
    sqla_connection, session, singer_cls
):
    from fastapi_sqla import _Session

    session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    session.commit()

    other_session = _Session()
    assert other_session.query(singer_cls).get(1)


@mark.require_asyncpg
@mark.asyncio
@mark.sqlalchemy("1.4")
async def test_all_opened_async_sessions_are_within_the_same_transaction(
    async_sqla_connection, async_session, singer_cls
):
    from fastapi_sqla.asyncio_support import _AsyncSession

    async_session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    await async_session.commit()

    other_session = _AsyncSession(bind=async_sqla_connection)
    assert await other_session.get(singer_cls, 1)


@fixture
def conftest(db_url, testdir):
    testdir.makeconftest(
        f"""
        from pytest import fixture

        @fixture(scope="session")
        def db_url():
            return "{db_url}"
        """
    )


def test_sqla_modules(testdir, conftest):
    testdir.makepyfile(
        """
        from pytest import fixture
        from sqlalchemy import text


        @fixture
        def sqla_modules():
            pass


        def test_anything(session):
            session.execute(text("SELECT 1"))
    """
    )
    result = testdir.runpytest()
    result.assert_outcomes(passed=1)


def test_sqla_modules_fixture_raises_exception_when_not_overriden(testdir, conftest):
    testdir.makepyfile(
        """
        from sqlalchemy import text


        def test_anything(session):
            session.execute(text("SELECT 1"))
    """
    )
    result = testdir.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*sqla_modules fixture is not defined*"])


@mark.parametrize(
    "url,expected",
    [
        ("postgresql://localhost/db", "postgresql+asyncpg://localhost/db"),
        ("postgresql://u:p@localhost/db", "postgresql+asyncpg://u:p@localhost/db"),
    ],
)
def test_format_async_sqlalchemy_url(monkeypatch, conftest, testdir, url, expected):
    from fastapi_sqla._pytest_plugin import format_async_async_sqlalchemy_url

    assert format_async_async_sqlalchemy_url(url) == expected
