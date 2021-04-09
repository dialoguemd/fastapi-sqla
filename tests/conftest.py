import importlib
from unittest.mock import patch

from faker import Faker
from pytest import fixture, skip
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import close_all_sessions

pytest_plugins = ["fastapi_sqla._pytest_plugin", "pytester"]


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        (
            "sqlalchemy(major.minor): skip test if tests run without the expected "
            "sqlalchemy version"
        ),
    )


@fixture(scope="session")
def sqla_version_tuple():
    from sqlalchemy import __version__

    return tuple(int(i) for i in __version__.split("."))


@fixture(scope="session", autouse=True)
def environ(db_url, sqla_version_tuple):
    values = {"sqlalchemy_url": db_url}

    if sqla_version_tuple >= (1, 4, 0):
        scheme, parts = db_url.split(":")
        values["asyncpg_url"] = f"{scheme}+asyncpg:{parts}"

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
def check_sqlalchemy_version(request, sqla_version_tuple):
    "When test is marked with `mark.sqlalchemy('x.y')`, skip if unexpected sqla version."
    from sqlalchemy import __version__

    marker = request.node.get_closest_marker("sqlalchemy")
    if marker:
        major, minor, _ = sqla_version_tuple
        expected = marker.args[0]
        current = f"{major}.{minor}"
        if expected != current:
            skip(
                f"Marked to run against sqlalchemy=^{expected}.0, but got {__version__}"
            )


@fixture(scope="session")
def faker():
    return Faker()
