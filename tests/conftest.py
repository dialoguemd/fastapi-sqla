import importlib
import os
from unittest.mock import patch

from faker import Faker
from pytest import fixture, skip

# Must be done before importing anything from sqlalchemy:
os.environ["SQLALCHEMY_WARN_20"] = "true"

pytest_plugins = ["fastapi_sqla._pytest_plugin", "pytester"]


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        (
            "sqlalchemy(major.minor): skip test if tests run with a lower version than "
            "the expected sqlalchemy version"
        ),
    )
    config.addinivalue_line(
        "markers", "require_asyncpg: skip test if asyncpg is not installed"
    )
    config.addinivalue_line(
        "markers", "require_boto3: skip test if boto3 is not installed"
    )
    config.addinivalue_line(
        "markers", "require_sqlmodel: skip test if sqlmodel is not installed"
    )


@fixture(scope="session")
def sqla_version_tuple():
    """Return sqla version major and minor in a tuple: '1.3.10' -> (1, 3)"""
    from sqlalchemy import __version__

    return tuple(int(i) for i in __version__.split("."))[:2]


def is_asyncpg_installed():
    try:
        import asyncpg  # noqa
    except ImportError:
        return False
    else:
        return True


def is_boto3_installed():
    try:
        import boto3  # noqa
    except ImportError:
        return False
    else:
        return True


def is_sqlmodel_installed():
    try:
        import sqlmodel  # noqa
    except ImportError:
        return False
    else:
        return True


@fixture(scope="session")
def async_session_key():
    return "async"


@fixture(scope="session", autouse=True)
def environ(db_url, sqla_version_tuple, async_session_key, async_sqlalchemy_url):
    values = {
        "PYTHONASYNCIODEBUG": "1",
        "sqlalchemy_url": db_url,
        "SQLALCHEMY_WARN_20": "true",
    }

    if sqla_version_tuple >= (1, 4) and is_asyncpg_installed():
        values[f"fastapi_sqla__{async_session_key}__sqlalchemy_url"] = (
            async_sqlalchemy_url
        )

    with patch.dict("os.environ", values=values, clear=True):
        yield values


@fixture(autouse=True)
def tear_down(environ):
    from sqlalchemy.orm.session import close_all_sessions

    import fastapi_sqla

    yield

    close_all_sessions()
    # reload fastapi_sqla to clear sqla deferred reflection mapping stored in Base
    importlib.reload(fastapi_sqla.models)
    importlib.reload(fastapi_sqla.sqla)
    importlib.reload(fastapi_sqla.async_sqla)
    importlib.reload(fastapi_sqla)


@fixture
def sqla_modules():
    pass


@fixture(autouse=True)
def check_sqlalchemy_version(request, sqla_version_tuple):
    """Mark test with `mark.sqlalchemy('x.y')` to skip on unexpected sqla version."""
    from sqlalchemy import __version__

    marker = request.node.get_closest_marker("sqlalchemy")
    if marker:
        expected = marker.args[0]
        major, minor = tuple(int(i) for i in expected.split("."))
        if sqla_version_tuple < (major, minor):
            skip(
                f"Marked to run against sqlalchemy=^{expected}.0, but got {__version__}"
            )


@fixture(autouse=True)
def check_asyncpg(request):
    """Skip test marked with mark.require_asyncpg if asyncpg is not installed."""
    marker = request.node.get_closest_marker("require_asyncpg")
    if marker and not is_asyncpg_installed():
        skip("This test requires asyncpg. Skipping as asyncpg is not installed.")


@fixture(autouse=True)
def check_bobo3(request):
    """Skip test marked with mark.require_boto3 if boto3  is not installed."""
    marker = request.node.get_closest_marker("require_boto3")
    if marker and not is_boto3_installed():
        skip("This test requires boto3. Skipping as boto3 is not installed.")


@fixture(autouse=True)
def check_sqlmodel(request):
    """Skip test marked with mark.require_sqlmodel if sqlmodel is not installed."""
    marker = request.node.get_closest_marker("require_sqlmodel")
    if marker and not is_sqlmodel_installed():
        skip("This test requires sqlmodel. Skipping as sqlmodel is not installed.")


@fixture(scope="session")
def faker():
    return Faker()
