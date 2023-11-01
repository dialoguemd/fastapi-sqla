import math
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Iterator, Optional, Union, cast

import structlog
from fastapi import Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession as SqlaAsyncSession
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.sql import Select, func, select

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support
from fastapi_sqla.models import Page
from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, Base, new_engine

logger = structlog.get_logger(__name__)

_ASYNC_REQUEST_SESSION_KEY = "fastapi_sqla_async_session"

_AsyncSession: dict[str, sessionmaker] = {}


def new_async_engine(key: str = _DEFAULT_SESSION_KEY):
    # NOTE: We don't support this for non-default sessions
    # TODO: Check if we can get rid of it. I think so
    envvar_prefix = None
    if key == _DEFAULT_SESSION_KEY and "async_sqlalchemy_url" in os.environ:
        envvar_prefix = "async_sqlalchemy_"

    engine = new_engine(key, envvar_prefix=envvar_prefix)
    return AsyncEngine(engine)


async def startup(key: str = _DEFAULT_SESSION_KEY):
    engine = new_async_engine(key)
    aws_rds_iam_support.setup(engine.sync_engine)
    aws_aurora_support.setup(engine.sync_engine)

    # Fail early
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 'ok'"))
    except Exception:
        logger.critical(
            f"Failed querying db for key '{key}': "
            "are the the environment variables correctly configured for this key?"
        )
        raise

    async with engine.connect() as connection:
        await connection.run_sync(lambda conn: Base.prepare(conn.engine))

    _AsyncSession[key] = sessionmaker(
        class_=SqlaAsyncSession, bind=engine, expire_on_commit=False
    )

    logger.info("engine startup", engine_key=key, async_engine=engine)


@asynccontextmanager
async def open_session(
    key: str = _DEFAULT_SESSION_KEY,
) -> AsyncGenerator[SqlaAsyncSession, None]:
    """Context manager to open an async session and properly close it when exiting.

    If no exception is raised before exiting context, session is committed when exiting
    context. If an exception is raised, session is rollbacked.
    """
    try:
        session: SqlaAsyncSession = _AsyncSession[key]()
    except KeyError as exc:
        raise Exception(
            f"No async session with key {key} found, "
            "please ensure you've configured the environment variables for this key."
        ) from exc

    logger.bind(db_async_session=session)

    try:
        yield session
        await session.commit()

    except Exception:
        logger.exception("commit failed, rolling back")
        await session.rollback()
        raise

    finally:
        await session.close()


async def add_session_to_request(
    request: Request, call_next, key: str = _DEFAULT_SESSION_KEY
):
    """Middleware which injects a new sqla async session into every request.

    Handles creation of session, as well as commit, rollback, and closing of session.

    Usage::

        import fastapi_sqla
        from fastapi import FastApi

        app = FastApi()

        fastapi_sqla.setup(app)  # includes middleware

        @app.get("/users")
        async def get_users(session: fastapi_sqla.AsyncSession):
            return await session.execute(...) # use your session here
    """
    async with open_session(key) as session:
        request.scope[f"{_ASYNC_REQUEST_SESSION_KEY}_{key}"] = session
        response = await call_next(request)
        if response.status_code >= 400:
            # If ever a route handler returns an http exception, we do not want the
            # session opened by current context manager to commit anything in db.
            await session.rollback()

    return response


class AsyncSessionDependency:
    def __init__(self, key: str = _DEFAULT_SESSION_KEY) -> None:
        self.key = key

    def __call__(self, request: Request) -> SqlaAsyncSession:
        """Yield the sqlalchemy async session for that request.

        It is meant to be used as a FastAPI dependency::

            from fastapi import APIRouter, Depends
            from fastapi_sqla import SqlaAsyncSession, AsyncSessionDependency

            router = APIRouter()

            @router.get("/users")
            async def get_users(
                session: SqlaAsyncSession = Depends(AsyncSessionDependency())
            ):
                pass
        """
        try:
            return request.scope[f"{_ASYNC_REQUEST_SESSION_KEY}_{self.key}"]
        except KeyError:  # pragma: no cover
            raise Exception(
                f"No async session with key {self.key} found in request, "
                "please ensure you've setup fastapi_sqla."
            )


QueryCountDependency = Callable[..., Awaitable[int]]
PaginateSignature = Callable[[Select, Optional[bool]], Awaitable[Page]]
DefaultDependency = Callable[[SqlaAsyncSession, int, int], PaginateSignature]
WithQueryCountDependency = Callable[
    [SqlaAsyncSession, int, int, int], PaginateSignature
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
    page_number = offset / limit + 1
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    data = iter(
        cast(Iterator, result.unique().scalars() if scalars else result.mappings())
    )
    return Page(
        data=data,
        meta={
            "offset": offset,
            "total_items": total_items,
            "total_pages": total_pages,
            "page_number": page_number,
        },
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
    ) -> PaginateSignature:
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
    ):
        async def paginate(query: Select, scalars=True) -> Page:
            return await paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    if query_count:
        return with_query_count_dependency
    else:
        return default_dependency


AsyncPaginate = Annotated[PaginateDependency, Depends(AsyncPagination())]
AsyncSession = Annotated[SqlaAsyncSession, Depends(AsyncSessionDependency())]
