from functools import partial
import os
from typing import Union

from fastapi import FastAPI

from fastapi_sqla import sqla
from fastapi_sqla.sqla import (
    Base,
    Collection,
    Item,
    Page,
    Paginate,
    PaginateSignature,
    Pagination,
    Session,
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
    "open_session",
]


try:
    from fastapi_sqla import asyncio_support
    from fastapi_sqla.asyncio_support import (  # noqa
        AsyncPaginate,
        AsyncPagination,
        AsyncSession,
    )
    from fastapi_sqla.asyncio_support import open_session as open_async_session  # noqa

    __all__ += [
        "AsyncPaginate",
        "AsyncPagination",
        "AsyncSession",
        "open_async_session",
    ]
    has_asyncio_support = True

except ImportError as err:
    has_asyncio_support = False
    asyncio_support_err = str(err)


def setup(app: FastAPI, base_cls: Union[type, None] = None):
    engine = sqla.new_engine()

    if not sqla.is_async_dialect(engine):
        bound_startup = partial(sqla.startup, base_cls=base_cls)
        app.add_event_handler("startup", bound_startup)
        app.middleware("http")(sqla.add_session_to_request)

    has_async_config = "async_sqlalchemy_url" in os.environ or sqla.is_async_dialect(
        engine
    )
    if has_async_config:
        assert has_asyncio_support, asyncio_support_err
        bound_startup = partial(asyncio_support.startup, base_cls=base_cls)
        app.add_event_handler("startup", bound_startup)
        app.middleware("http")(asyncio_support.add_session_to_request)
