import os

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from fastapi_sqla import sqla

try:
    from fastapi_sqla import async_sqla

    has_asyncio_support = True

except ImportError as err:  # pragma: no cover
    has_asyncio_support = False
    asyncio_support_err = str(err)


def setup(app: FastAPI):
    engine = sqla.new_engine()

    if not is_async_dialect(engine):
        app.add_event_handler("startup", sqla.startup)
        app.middleware("http")(sqla.add_session_to_request)

    has_async_config = "async_sqlalchemy_url" in os.environ or is_async_dialect(engine)
    if has_async_config:
        assert has_asyncio_support, asyncio_support_err
        app.add_event_handler("startup", async_sqla.startup)
        app.middleware("http")(async_sqla.add_session_to_request)


def is_async_dialect(engine: Engine):
    return engine.dialect.is_async if hasattr(engine.dialect, "is_async") else False
