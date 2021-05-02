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
    config.addinivalue_line(
        "markers", "require_asyncpg: skip test if asyncpg is not installed"
    )


@fixture(scope="session")
def sqla_version_tuple():
    from sqlalchemy import __version__

    return tuple(int(i) for i in __version__.split("."))


def is_asyncpg_installed():
    try:
        import asyncpg  # noqa
    except ImportError:
        return False
    else:
        return True


@fixture(scope="session", autouse=True)
def environ(db_url, sqla_version_tuple, async_sqlalchemy_url):
    values = {"sqlalchemy_url": db_url, "PYTHONASYNCIODEBUG": "1"}

    if sqla_version_tuple >= (1, 4, 0) and is_asyncpg_installed():
        scheme, parts = db_url.split(":")
        values["async_sqlalchemy_url"] = async_sqlalchemy_url

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


@fixture(autouse=True)
def check_asyncpg(request):
    "Skip test marked with mark.asyncpg if asyncpg is not installed."
    marker = request.node.get_closest_marker("require_asyncpg")
    if marker and not is_asyncpg_installed():
        skip("This test requires asyncpg. Skipping as asyncpg is not installed.")


@fixture(scope="session")
def faker():
    return Faker()
