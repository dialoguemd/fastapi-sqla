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
    with patch.dict("os.environ", values=values, clear=True) as environ:
        yield environ
