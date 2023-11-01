from fastapi_sqla.base import setup
from fastapi_sqla.models import Base, Collection, Item, Page
from fastapi_sqla.pagination import Paginate, PaginateSignature, Pagination
from fastapi_sqla.sqla import Session, open_session

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
    "setup",
]


try:
    from fastapi_sqla.async_pagination import AsyncPaginate, AsyncPagination
    from fastapi_sqla.async_sqla import AsyncSession
    from fastapi_sqla.async_sqla import open_session as open_async_session

    __all__ += [
        "AsyncPaginate",
        "AsyncPagination",
        "AsyncSession",
        "open_async_session",
    ]
    has_asyncio_support = True

except ImportError:  # pragma: no cover
    pass
