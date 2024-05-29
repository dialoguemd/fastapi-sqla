import functools
import os
import re

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from fastapi_sqla import sqla

try:
    from fastapi_sqla import async_sqla

    has_asyncio_support = True

except ImportError as err:  # pragma: no cover
    has_asyncio_support = False
    asyncio_support_err = str(err)


_ENGINE_KEYS_REGEX = re.compile(r"fastapi_sqla__(?!_)(.+)(?<!_)__(?!_).+")


def setup(app: FastAPI):
    engine_keys = _get_engine_keys()
    engines = {key: sqla.new_engine(key) for key in engine_keys}
    for key, engine in engines.items():
        if not _is_async_dialect(engine):
            app.add_event_handler("startup", functools.partial(sqla.startup, key=key))
            app.middleware("http")(
                functools.partial(sqla.add_session_to_request, key=key)
            )
        else:
            app.add_event_handler(
                "startup", functools.partial(async_sqla.startup, key=key)
            )
            app.middleware("http")(
                functools.partial(async_sqla.add_session_to_request, key=key)
            )


def _get_engine_keys() -> set[str]:
    keys = {sqla._DEFAULT_SESSION_KEY}

    lowercase_environ = {k.lower(): v for k, v in os.environ.items()}
    for env_var in lowercase_environ:
        match = _ENGINE_KEYS_REGEX.search(env_var)
        if not match:
            continue

        keys.add(match.group(1))

    return keys


def _is_async_dialect(engine: Engine):
    return engine.dialect.is_async if hasattr(engine.dialect, "is_async") else False
