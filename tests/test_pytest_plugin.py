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
