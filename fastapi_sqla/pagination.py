import math
from collections.abc import Callable, Iterator
from functools import singledispatch
from typing import Annotated, Optional, Union, cast

from fastapi import Depends, Query
from sqlalchemy.orm import Query as LegacyQuery
from sqlalchemy.sql import Select, func, select

from fastapi_sqla.models import Meta, Page
from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, SessionDependency, SqlaSession

DbQuery = Union[LegacyQuery, Select]
QueryCountDependency = Callable[..., int]
PaginateSignature = Callable[[DbQuery, Optional[bool]], Page]
DefaultDependency = Callable[[SqlaSession, int, int], PaginateSignature]
WithQueryCountDependency = Callable[[SqlaSession, int, int, int], PaginateSignature]
PaginateDependency = Union[DefaultDependency, WithQueryCountDependency]


def default_query_count(session: SqlaSession, query: DbQuery) -> int:
    """Default function used to count items returned by a query.

    It is slower than a manually written query could be: It runs the query in a
    subquery, and count the number of elements returned.

    See https://gist.github.com/hest/8798884
    """
    if isinstance(query, LegacyQuery):
        result = query.count()

    elif isinstance(query, Select):
        result = cast(
            int,
            session.execute(
                select(func.count()).select_from(query.subquery())
            ).scalar(),
        )

    else:  # pragma: no cover
        raise NotImplementedError(f"Query type {type(query)!r} is not supported")

    return result


@singledispatch
def paginate_query(
    query: DbQuery,
    session: SqlaSession,
    total_items: int,
    offset: int,
    limit: int,
    scalars: bool = True,
) -> Page:  # pragma: no cover
    """Dispatch on registered functions based on `query` type"""
    raise NotImplementedError(f"no paginate_query registered for type {type(query)!r}")


@paginate_query.register
def _paginate_legacy(
    query: LegacyQuery,
    session: SqlaSession,
    total_items: int,
    offset: int,
    limit: int,
    scalars: bool = True,
) -> Page:
    total_pages = math.ceil(total_items / limit)
    page_number = math.floor(offset / limit + 1)
    return Page(
        data=query.offset(offset).limit(limit).all(),
        meta=Meta(
            offset=offset,
            total_items=total_items,
            total_pages=total_pages,
            page_number=page_number,
        ),
    )


@paginate_query.register
def _paginate(
    query: Select,
    session: SqlaSession,
    total_items: int,
    offset: int,
    limit: int,
    *,
    scalars: bool = True,
) -> Page:
    total_pages = math.ceil(total_items / limit)
    page_number = math.floor(offset / limit + 1)
    query = query.offset(offset).limit(limit)
    result = session.execute(query)
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


def Pagination(
    session_key: str = _DEFAULT_SESSION_KEY,
    min_page_size: int = 10,
    max_page_size: int = 100,
    query_count: Union[QueryCountDependency, None] = None,
) -> PaginateDependency:
    def default_dependency(
        session: SqlaSession = Depends(SessionDependency(key=session_key)),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
    ) -> PaginateSignature:
        def paginate(query: DbQuery, scalars=True) -> Page:
            total_items = default_query_count(session, query)
            return paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    def with_query_count_dependency(
        session: SqlaSession = Depends(SessionDependency(key=session_key)),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
        total_items: int = Depends(query_count),
    ) -> PaginateSignature:
        def paginate(query: DbQuery, scalars=True) -> Page:
            return paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    if query_count:
        return with_query_count_dependency
    else:
        return default_dependency


Paginate = Annotated[PaginateSignature, Depends(Pagination())]
