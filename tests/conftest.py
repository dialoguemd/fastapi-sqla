import importlib
import os
from unittest.mock import patch

from pytest import fixture
from sqlalchemy.orm.session import close_all_sessions


@fixture(scope="session")
def db_url():
    host = "postgres" if "CIRCLECI" in os.environ else "localhost"
    return f"postgresql://postgres@{host}/postgres"


@fixture(autouse=True)
def environ(db_url):
    values = {"sqlalchemy_url": db_url}
    with patch.dict("os.environ", values=values, clear=True):
        yield values


@fixture(autouse=True)
def tear_down():
    import fastapi_sqla

    yield

    close_all_sessions()
    # reload fastapi_sqla to clear sqla deferred reflection mapping stored in Base
    importlib.reload(fastapi_sqla)
