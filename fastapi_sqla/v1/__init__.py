from fastapi_sqla import (
    Base,
    Session,
    SessionDependency,
    SqlaSession,
    open_session,
    setup,
    setup_middlewares,
    startup,
)
from fastapi_sqla.v1.models import Collection, Item, Meta, Page
from fastapi_sqla.v1.pagination import Paginate, PaginateSignature, Pagination

__all__ = [
    "Base",
    "Collection",
    "Item",
    "Meta",
    "Page",
    "Paginate",
    "PaginateSignature",
    "Pagination",
    "Session",
    "SessionDependency",
    "SqlaSession",
    "open_session",
    "setup",
    "setup_middlewares",
    "startup",
]


try:
    from fastapi_sqla import (
        AsyncSession,
        AsyncSessionDependency,
        SqlaAsyncSession,
        open_async_session,
    )
    from fastapi_sqla.v1.async_pagination import (
        AsyncPaginate,
        AsyncPaginateSignature,
        AsyncPagination,
    )

    __all__ += [
        "AsyncPaginate",
        "AsyncPaginateSignature",
        "AsyncPagination",
        "AsyncSession",
        "AsyncSessionDependency",
        "SqlaAsyncSession",
        "open_async_session",
    ]
    has_asyncio_support = True

except ImportError:  # pragma: no cover
    pass
