from pytest import fixture


@fixture(scope="module", autouse=True)
def setup_tear_down(engine):
    engine.execute(
        """
        CREATE TABLE IF NOT EXISTS singer (
           id integer primary key,
           name varchar,
           country varchar
        )
    """
    )
    yield
    engine.execute("DROP TABLE singer")


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
    assert engine.execute("select count(*) from singer").scalar() == 0


def test_all_opened_sessions_are_within_the_same_transaction(session, singer_cls):
    from fastapi_sqla import _Session

    session.add(singer_cls(id=1, name="Bob Marley", country="Jamaica"))
    session.commit()

    other_session = _Session()
    assert other_session.query(singer_cls).get(1)


def test_sqla_modules(testdir):
    testdir.makepyfile(
        """
        from pytest import fixture


        @fixture
        def sqla_modules():
            pass


        def test_anything(session):
            session.execute("SELECT 1")
    """
    )
    result = testdir.runpytest()
    result.assert_outcomes(passed=1)


def test_sqla_modules_fixture_raises_exception_when_not_overriden(testdir):
    testdir.makepyfile(
        """
        def test_anything(session):
            session.execute("SELECT 1")
    """
    )
    result = testdir.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*sqla_modules fixture is not defined*"])
