import asyncio
import math
import os
from contextlib import contextmanager
from functools import singledispatch
from typing import Callable, Generic, List, Optional, TypeVar, Union

import structlog
from fastapi import Depends, FastAPI, Query, Request
from fastapi.concurrency import contextmanager_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel
from sqlalchemy import engine_from_config, text
from sqlalchemy.ext.declarative import DeferredReflection
from sqlalchemy.orm import Query as LegacyQuery
from sqlalchemy.orm.session import Session as SqlaSession
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.sql import Select, func, select

from . import aws_rds_iam_support

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

try:
    from . import asyncio_support
    from .asyncio_support import AsyncSession
    from .asyncio_support import open_session as open_async_session
except ImportError as err:
    asyncio_support = False
    asyncio_support_err = str(err)

__all__ = [
    "AsyncSession",
    "Base",
    "Page",
    "Paginate",
    "Session",
    "open_async_session",
    "open_session",
    "setup",
]

logger = structlog.get_logger(__name__)

_SESSION_KEY = "fastapi_sqla_session"

_Session = sessionmaker()


def setup(app: FastAPI):
    app.add_event_handler("startup", startup)
    app.middleware("http")(add_session_to_request)

    async_sqlalchemy_url = os.getenv("async_sqlalchemy_url")
    if async_sqlalchemy_url:
        assert asyncio_support, asyncio_support_err
        app.add_event_handler("startup", asyncio_support.startup)
        app.middleware("http")(asyncio_support.add_session_to_request)


def startup():
    lowercase_environ = {
        k.lower(): v for k, v in os.environ.items() if k.lower() != "sqlalchemy_warn_20"
    }
    engine = engine_from_config(lowercase_environ, prefix="sqlalchemy_")
    aws_rds_iam_support.setup(engine.engine)

    Base.metadata.bind = engine
    Base.prepare(engine)
    _Session.configure(bind=engine)

    # Fail early:
    try:
        with open_session() as session:
            session.execute(text("select 'OK'"))
    except Exception:
        logger.critical(
            "Fail querying db: is sqlalchemy_url envvar correctly configured?"
        )
        raise

    logger.info("startup", engine=engine)


class Base(declarative_base(cls=DeferredReflection)):  # type: ignore
    __abstract__ = True


class Session(SqlaSession):
    def __new__(cls, request: Request) -> SqlaSession:
        """Yield the sqlalchmey session for that request.

        It is meant to be used as a FastAPI dependency::

            from fastapi import APIRouter, Depends
            from fastapi_sqla import Session

            router = APIRouter()

            @router.get("/users")
            def get_users(session: Session = Depends()):
                pass
        """
        try:
            return request.scope[_SESSION_KEY]
        except KeyError:  # pragma: no cover
            raise Exception(
                "No session found in request, please ensure you've setup fastapi_sqla."
            )


@contextmanager
def open_session() -> Session:
    """Context manager that opens a session and properly closes session when exiting.

    If no exception is raised before exiting context, session is committed when exiting
    context. If an exception is raised, session is rollbacked.
    """
    session = _Session()
    logger.bind(db_session=session)

    try:
        yield session

    except Exception:
        logger.warning("context failed, rolling back", exc_info=True)
        session.rollback()
        raise

    else:
        try:
            session.commit()
        except Exception:
            logger.exception("commit failed, rolling back")
            session.rollback()
            raise

    finally:
        session.close()


async def add_session_to_request(request: Request, call_next):
    """Middleware which injects a new sqla session into every request.

    Handles creation of session, as well as commit, rollback, and closing of session.

    Usage::

        import fastapi_sqla
        from fastapi import FastApi

        app = FastApi()

        fastapi_sqla.setup(app)  # includes middleware

        @app.get("/users")
        def get_users(session: fastapi_sqla.Session = Depends()):
            return session.execute(...) # use your session here
    """
    async with contextmanager_in_threadpool(open_session()) as session:
        request.scope[_SESSION_KEY] = session

        response = await call_next(request)

        loop = asyncio.get_running_loop()

        # try to commit after response, so that we can return a proper 500 response
        # and not raise a true internal server error
        if response.status_code < 400:

            try:
                await loop.run_in_executor(None, session.commit)
            except Exception:
                logger.exception("commit failed, returning http error")
                response = PlainTextResponse(
                    content="Internal Server Error", status_code=500
                )

        if response.status_code >= 400:
            # If ever a route handler returns an http exception, we do not want the
            # session opened by current context manager to commit anything in db.
            logger.warning("http error, rolling back", status_code=response.status_code)
            await loop.run_in_executor(None, session.rollback)

    return response


T = TypeVar("T")


class Item(GenericModel, Generic[T]):
    """Item container."""

    data: T


class Collection(GenericModel, Generic[T]):
    """Collection container."""

    data: List[T]


class Meta(BaseModel):
    """Meta information on current page and collection"""

    offset: int = Field(..., description="Current page offset")
    total_items: int = Field(..., description="Total number of items in the collection")
    total_pages: int = Field(..., description="Total number of pages in the collection")
    page_number: int = Field(..., description="Current page number. Starts at 1.")


class Page(Collection, Generic[T]):
    """A page of the collection with info on current page and total items in meta."""

    meta: Meta


DbQuery = Union[LegacyQuery, Select]
QueryCountDependency = Callable[..., int]
PaginateSignature = Callable[[DbQuery, Optional[bool]], Page[T]]


def default_query_count(session: Session, query: DbQuery) -> int:
    """Default function used to count items returned by a query.

    It is slower than a manually written query could be: It runs the query in a subquery,
    and count the number of elements returned.

    See https://gist.github.com/hest/8798884
    """
    if isinstance(query, LegacyQuery):
        result = query.count()

    elif isinstance(query, Select):
        result = session.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar()

    else:  # pragma no cover
        raise NotImplementedError(f"Query type {type(query)!r} is not supported")

    return result


@singledispatch
def paginate_query(
    query: DbQuery,
    session: Session,
    total_items: int,
    offset: int,
    limit: int,
    scalars: bool = True,
) -> Page[T]:  # pragma no cover
    "Dispatch on registered functions based on `query` type"
    raise NotImplementedError(f"no paginate_query registered for type {type(query)!r}")


@paginate_query.register
def _paginate_legacy(
    query: LegacyQuery,
    session: Session,
    total_items: int,
    offset: int,
    limit: int,
    scalars: bool = True,
) -> Page[T]:
    total_pages = math.ceil(total_items / limit)
    page_number = offset / limit + 1
    return Page[T](
        data=query.offset(offset).limit(limit).all(),
        meta={
            "offset": offset,
            "total_items": total_items,
            "total_pages": total_pages,
            "page_number": page_number,
        },
    )


@paginate_query.register
def _paginate(
    query: Select,
    session: Session,
    total_items: int,
    offset: int,
    limit: int,
    *,
    scalars: bool = True,
) -> Page[T]:
    total_pages = math.ceil(total_items / limit)
    page_number = offset / limit + 1
    query = query.offset(offset).limit(limit)
    result = session.execute(query)
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


DefaultDependency = Callable[[Session, int, int], PaginateSignature]
WithQueryCountDependency = Callable[[Session, int, int, int], PaginateSignature]
PaginateDependency = Union[DefaultDependency, WithQueryCountDependency]


def Pagination(
    min_page_size: int = 10,
    max_page_size: int = 100,
    query_count: QueryCountDependency = None,
) -> PaginateDependency:
    def default_dependency(
        session: Session = Depends(),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
    ) -> PaginateSignature:
        def paginate(query: DbQuery, scalars=True) -> Page[T]:
            total_items = default_query_count(session, query)
            return paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    def with_query_count_dependency(
        session: Session = Depends(),
        offset: int = Query(0, ge=0),
        limit: int = Query(min_page_size, ge=1, le=max_page_size),
        total_items: int = Depends(query_count),
    ) -> PaginateSignature:
        def paginate(query: DbQuery, scalars=True) -> Page[T]:
            return paginate_query(
                query, session, total_items, offset, limit, scalars=scalars
            )

        return paginate

    if query_count:
        return with_query_count_dependency
    else:
        return default_dependency


Paginate: PaginateDependency = Pagination()
