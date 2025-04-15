import functools
import os
import re
from typing import Union

from deprecated import deprecated
from fastapi import FastAPI
from sqlalchemy.engine import Connection, Engine

from fastapi_sqla import sqla

try:
    from fastapi_sqla import async_sqla

    has_asyncio_support = True

except ImportError as err:  # pragma: no cover
    has_asyncio_support = False
    asyncio_support_err = str(err)


_ENGINE_KEYS_REGEX = re.compile(r"fastapi_sqla__(?!_)(.+)(?<!_)__(?!_).+")


async def startup():
    engine_keys = _get_engine_keys()
    engines = {key: sqla.new_engine(key) for key in engine_keys}
    for key, engine in engines.items():
        if not _is_async_dialect(engine):
            sqla.startup(key=key)
        else:
            await async_sqla.startup(key=key)


def setup_middlewares(app: FastAPI):
    engine_keys = _get_engine_keys()
    engines = {key: sqla.new_engine(key) for key in engine_keys}
    for key, engine in engines.items():
        if not _is_async_dialect(engine):
            app.add_middleware(sqla.SessionMiddleware, key=key)
        else:
            app.add_middleware(async_sqla.AsyncSessionMiddleware, key=key)


@deprecated(
    reason="FastAPI events are deprecated. This function will be remove in the upcoming major release."  # noqa: E501
)
def setup(app: FastAPI):
    engine_keys = _get_engine_keys()
    engines = {key: sqla.new_engine(key) for key in engine_keys}
    for key, engine in engines.items():
        if not _is_async_dialect(engine):
            app.add_event_handler("startup", functools.partial(sqla.startup, key=key))
            app.add_middleware(sqla.SessionMiddleware, key=key)
        else:
            app.add_event_handler(
                "startup", functools.partial(async_sqla.startup, key=key)
            )
            app.add_middleware(async_sqla.AsyncSessionMiddleware, key=key)


def _get_engine_keys() -> set[str]:
    keys = {sqla._DEFAULT_SESSION_KEY}

    lowercase_environ = {k.lower(): v for k, v in os.environ.items()}
    for env_var in lowercase_environ:
        match = _ENGINE_KEYS_REGEX.search(env_var)
        if not match:
            continue

        keys.add(match.group(1))

    return keys


def _is_async_dialect(engine: Union[Engine, Connection]):
    return engine.dialect.is_async if hasattr(engine.dialect, "is_async") else False
