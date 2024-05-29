import math
from collections.abc import Awaitable, Callable, Iterator
from typing import Annotated, Optional, Union, cast

from fastapi import Depends, Query
from sqlalchemy.sql import Select, func, select

from fastapi_sqla.async_sqla import AsyncSessionDependency, SqlaAsyncSession
from fastapi_sqla.models import Meta, Page
from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY

QueryCountDependency = Callable[..., Awaitable[int]]
AsyncPaginateSignature = Callable[[Select, Optional[bool]], Awaitable[Page]]
DefaultDependency = Callable[[SqlaAsyncSession, int, int], AsyncPaginateSignature]
WithQueryCountDependency = Callable[
    [SqlaAsyncSession, int, int, int], AsyncPaginateSignature
]
PaginateDependency = Union[DefaultDependency, WithQueryCountDependency]


async def default_query_count(session: SqlaAsyncSession, query: Select) -> int:
    result = await session.execute(select(func.count()).select_from(query.subquery()))
    return cast(int, result.scalar())


async def paginate_query(
    query: Select,
    session: SqlaAsyncSession,
    total_items: int,
    offset: int,
    limit: int,
    *,
    scalars: bool = True,
) -> Page:
    total_pages = math.ceil(total_items / limit)
    page_number = math.floor(offset / limit + 1)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    data = iter(
        cast(Iterator, result.unique().scalars() if scalars else result.mappings())
    )
    return Page(
        data=data,  # type: ignore # Expected to be a list
        meta=Meta(
            offset=offset,
            total_items=total_items,
            total_pages=total_pages,
            page_number=page_number,
        ),
    )


def AsyncPagination(
    session_key: str = _DEFAULT_SESSION_KEY,
    min_page_size: int = 10,
    max_page_size: int = 100,
    query_count: Union[QueryCountDependency, None] = None,
) -> PaginateDependency:
    def default_dependency(
        session: SqlaAsyncSession = Depends(AsyncSessionDependency(key=session_key)),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
    ) -> AsyncPaginateSignature:
        async def paginate(query: Select, scalars=True) -> Page:
            total_items = await default_query_count(session, query)
            return await paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    def with_query_count_dependency(
        session: SqlaAsyncSession = Depends(AsyncSessionDependency(key=session_key)),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
        total_items: int = Depends(query_count),
    ) -> AsyncPaginateSignature:
        async def paginate(query: Select, scalars=True) -> Page:
            return await paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    if query_count:
        return with_query_count_dependency
    else:
        return default_dependency


AsyncPaginate = Annotated[AsyncPaginateSignature, Depends(AsyncPagination())]
