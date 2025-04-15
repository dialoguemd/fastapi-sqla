from pytest import fixture, mark
from sqlalchemy import text


@fixture(scope="module", autouse=True)
def setup_tear_down(sqla_connection):
    with sqla_connection.begin():
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
    with sqla_connection.begin():
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
@mark.sqlalchemy("1.4")
async def test_async_session_fixture_does_not_write_in_db(
    async_session, singer_cls, async_engine
):
    async_session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    await async_session.commit()
    async with async_engine.connect() as connection:
        assert (
            await connection.execute(text("select count(*) from singer"))
        ).scalar() == 0


@fixture
def truncate_table_tear_down(sqla_connection):
    yield
    with sqla_connection.begin():
        sqla_connection.execute(text("TRUNCATE TABLE singer"))


@mark.dont_patch_engines
def test_session_fixture_dont_patch_engine_writes_in_db(
    session, singer_cls, engine, truncate_table_tear_down
):
    session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    session.commit()
    with engine.connect() as connection:
        assert connection.execute(text("select count(*) from singer")).scalar() == 1


@mark.dont_patch_engines
@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_async_session_fixture_dont_patch_engine_writes_in_db(
    async_session, singer_cls, async_engine, truncate_table_tear_down
):
    async_session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    await async_session.commit()
    async with async_engine.connect() as connection:
        assert (
            await connection.execute(text("select count(*) from singer"))
        ).scalar() == 1


@mark.sqlalchemy("1.4")
def test_all_opened_sessions_are_within_the_same_transaction(
    sqla_connection, session, session_factory, singer_cls
):
    session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    session.commit()

    other_session = session_factory(bind=sqla_connection)

    assert other_session.get(singer_cls, 1)


def test_sqla_13_all_opened_sessions_are_within_the_same_transaction(
    sqla_connection, session, session_factory, singer_cls
):
    session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    session.commit()

    other_session = session_factory(bind=sqla_connection)

    assert other_session.query(singer_cls).get(1)


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_all_opened_async_sessions_are_within_the_same_transaction(
    async_sqla_connection, async_session, async_session_factory, singer_cls
):
    async_session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    await async_session.commit()

    other_session = async_session_factory(bind=async_sqla_connection)
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


async def test_session_fixture_patch_startup(session, singer_cls):
    from fastapi_sqla import open_session, startup

    await startup()

    with open_session() as new_session:
        new_session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))

    assert session.query(singer_cls).get(1)


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
async def test_async_session_fixture_patch_startup(async_session, singer_cls):
    from fastapi_sqla import open_async_session
    from fastapi_sqla.async_sqla import startup

    await startup()

    async with open_async_session() as new_session:
        new_session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))

    assert await async_session.get(singer_cls, 1)
