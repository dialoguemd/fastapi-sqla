import importlib
from unittest.mock import patch

from pytest import fixture
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import close_all_sessions

pytest_plugins = ["fastapi_sqla._pytest_plugin"]


@fixture(scope="session", autouse=True)
def environ(db_url):
    values = {"sqlalchemy_url": db_url}
    with patch.dict("os.environ", values=values, clear=True):
        yield values


@fixture(scope="session")
def engine(environ):
    engine = engine_from_config(environ, prefix="sqlalchemy_")
    return engine


@fixture(autouse=True)
def tear_down():
    import fastapi_sqla

    yield

    close_all_sessions()
    # reload fastapi_sqla to clear sqla deferred reflection mapping stored in Base
    importlib.reload(fastapi_sqla)


@fixture
def sqla_modules():
    pass
