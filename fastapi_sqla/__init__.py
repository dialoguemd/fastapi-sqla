import functools
import os
import re

from fastapi import FastAPI

from fastapi_sqla import sqla
from fastapi_sqla.models import Collection, Item, Page
from fastapi_sqla.sqla import (
    Base,
    Paginate,
    PaginateSignature,
    Pagination,
    Session,
    SessionDependency,
    SqlaSession,
    open_session,
)

__all__ = [
    "Base",
    "Collection",
    "Item",
    "Page",
    "Paginate",
    "PaginateSignature",
    "Pagination",
    "Session",
    "SessionDependency",
    "SqlaSession",
    "open_session",
]


try:
    from fastapi_sqla import asyncio_support
    from fastapi_sqla.asyncio_support import (
        AsyncPaginate,
        AsyncPagination,
        AsyncSession,
        AsyncSessionDependency,
        SqlaAsyncSession,
    )
    from fastapi_sqla.asyncio_support import open_session as open_async_session

    __all__ += [
        "AsyncPaginate",
        "AsyncPagination",
        "AsyncSession",
        "AsyncSessionDependency",
        "SqlaAsyncSession",
        "open_async_session",
    ]
    has_asyncio_support = True

except ImportError as err:  # pragma: no cover
    has_asyncio_support = False
    asyncio_support_err = str(err)

ENGINE_KEYS_REGEX = re.compile(r"fastapi_sqla__(.+)__.+")


def _get_engine_keys() -> set[str]:
    keys = {sqla._DEFAULT_SESSION_KEY}

    lowercase_environ = {k.lower(): v for k, v in os.environ.items()}
    for env_var in lowercase_environ:
        match = ENGINE_KEYS_REGEX.search(env_var)
        if not match:
            continue

        try:
            key = match.group(1)
        except IndexError:
            continue

        if key:
            keys.add(key)

    return keys


def setup(app: FastAPI):
    engine_keys = _get_engine_keys()
    engines = {key: sqla.new_engine(key) for key in engine_keys}
    for key, engine in engines.items():
        if not sqla.is_async_dialect(engine):
            app.add_event_handler("startup", functools.partial(sqla.startup, key=key))
            app.middleware("http")(
                functools.partial(sqla.add_session_to_request, key=key)
            )

        # TODO: Check if we can get rid of it. I think so
        has_async_config = (
            key == sqla._DEFAULT_SESSION_KEY and "async_sqlalchemy_url" in os.environ
        )
        if sqla.is_async_dialect(engine) or has_async_config:
            assert has_asyncio_support, asyncio_support_err
            app.add_event_handler(
                "startup", functools.partial(asyncio_support.startup, key=key)
            )
            app.middleware("http")(
                functools.partial(asyncio_support.add_session_to_request, key=key)
            )
