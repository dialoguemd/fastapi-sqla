import math
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Optional, Union

import structlog
from fastapi import Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession as SqlaAsyncSession
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.sql import Select, func, select

from fastapi_sqla.sqla import Base, Page, T, aws_rds_iam_support, new_engine

logger = structlog.get_logger(__name__)
_ASYNC_SESSION_KEY = "fastapi_sqla_async_session"
_AsyncSession = sessionmaker(class_=SqlaAsyncSession)


def new_async_engine():
    envvar_prefix = None
    if "async_sqlalchemy_url" in os.environ:
        envvar_prefix = "async_sqlalchemy_"

    engine = new_engine(envvar_prefix=envvar_prefix)
    return AsyncEngine(engine)


async def startup():
    engine = new_async_engine()
    aws_rds_iam_support.setup(engine.sync_engine)

    # Fail early:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 'ok'"))
    except Exception:
        logger.critical(
            "Failed querying db: is sqlalchemy_url or async_sqlalchemy_url envvar "
            "correctly configured?"
        )
        raise

    async with engine.connect() as connection:
        await connection.run_sync(Base.prepare)

    _AsyncSession.configure(bind=engine, expire_on_commit=False)
    logger.info("startup", async_engine=engine)


class AsyncSession(SqlaAsyncSession):
    def __new__(cls, request: Request) -> SqlaAsyncSession:
        """Yield the sqlalchmey async session for that request.

        It is meant to be used as a FastAPI dependency::

            from fastapi import APIRouter, Depends
            from fastapi_sqla import AsyncSession

            router = APIRouter()

            @router.get("/users")
            async def get_users(session: AsyncSession = Depends()):
                pass
        """
        try:
            return request.scope[_ASYNC_SESSION_KEY]
        except KeyError:  # pragma: no cover
            raise Exception(
                "No async session found in request, please ensure you've setup "
                "fastapi_sqla."
            )


@asynccontextmanager
async def open_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager to open an async session and properly close it when exiting.

    If no exception is raised before exiting context, session is committed when exiting
    context. If an exception is raised, session is rollbacked.
    """
    session = _AsyncSession()
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


async def add_session_to_request(request: Request, call_next):
    """Middleware which injects a new sqla async session into every request.

    Handles creation of session, as well as commit, rollback, and closing of session.

    Usage::

        import fastapi_sqla
        from fastapi import FastApi

        app = FastApi()

        fastapi_sqla.setup(app)  # includes middleware

        @app.get("/users")
        async def get_users(session: fastapi_sqla.AsyncSession = Depends()):
            return await session.execute(...) # use your session here
    """
    async with open_session() as session:
        request.scope[_ASYNC_SESSION_KEY] = session
        response = await call_next(request)
        if response.status_code >= 400:
            # If ever a route handler returns an http exception, we do not want the
            # session opened by current context manager to commit anything in db.
            await session.rollback()

    return response


QueryCountDependency = Callable[..., Awaitable[int]]
PaginateSignature = Callable[[Select, Optional[bool]], Awaitable[Page[T]]]
DefaultDependency = Callable[[AsyncSession, int, int], PaginateSignature]
WithQueryCountDependency = Callable[[AsyncSession, int, int, int], PaginateSignature]
PaginateDependency = Union[DefaultDependency, WithQueryCountDependency]


async def default_query_count(session: AsyncSession, query: Select) -> int:
    result = await session.execute(select(func.count()).select_from(query.subquery()))
    return result.scalar()


async def paginate_query(
    query: Select,
    session: AsyncSession,
    total_items: int,
    offset: int,
    limit: int,
    *,
    scalars: bool = True,
) -> Page[T]:
    total_pages = math.ceil(total_items / limit)
    page_number = offset / limit + 1
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    data = iter(result.unique().scalars() if scalars else result.mappings())
    return Page[T](
        data=data,
        meta={
            "offset": offset,
            "total_items": total_items,
            "total_pages": total_pages,
            "page_number": page_number,
        },
    )


def AsyncPagination(
    min_page_size: int = 10,
    max_page_size: int = 100,
    query_count: Union[QueryCountDependency, None] = None,
) -> PaginateDependency:
    def default_dependency(
        session: AsyncSession = Depends(),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
    ) -> PaginateSignature:
        async def paginate(query: Select, scalars=True) -> Page[T]:
            total_items = await default_query_count(session, query)
            return await paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    def with_query_count_dependency(
        session: AsyncSession = Depends(),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
        total_items: int = Depends(query_count),
    ):
        async def paginate(query: Select, scalars=True) -> Page[T]:
            return await paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    if query_count:
        return with_query_count_dependency
    else:
        return default_dependency


AsyncPaginate: PaginateDependency = AsyncPagination()
