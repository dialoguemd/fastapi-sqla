import importlib
from unittest.mock import patch

from pytest import fixture, skip
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import close_all_sessions

pytest_plugins = ["fastapi_sqla._pytest_plugin", "pytester"]


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "sqlalchemy: mark test to run only against sqlalchemy1.3"
    )


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


@fixture(autouse=True)
def check_sqlalchemy_version(request):
    "When test is marked with `mark.sqlalchemy('x.y')`, skip if unexpected sqla version."
    from sqlalchemy import __version__

    marker = request.node.get_closest_marker("sqlalchemy")
    if marker:
        major, minor, _ = __version__.split(".")
        expected = marker.args[0]
        if expected != f"{major}.{minor}":
            skip()
