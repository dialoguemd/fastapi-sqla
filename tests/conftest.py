import importlib
import os
from unittest.mock import patch

from pytest import fixture


@fixture(scope="session")
def db_uri():
    host = "postgres" if "CIRCLECI" in os.environ else "localhost"
    return f"postgresql://postgres@{host}/postgres"


@fixture(autouse=True)
def environ(db_uri):
    values = {"sqlalchemy_url": db_uri}
    with patch.dict("os.environ", values=values, clear=True):
        yield values


@fixture(autouse=True)
def tear_down():
    import fastapi_sqla

    # reload fastapi_sqla to clear sqla deferred reflection mapping stored in Base
    importlib.reload(fastapi_sqla)
