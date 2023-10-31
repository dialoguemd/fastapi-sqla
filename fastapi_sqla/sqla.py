import asyncio
import math
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import singledispatch
from typing import Annotated, Iterator, Optional, Union, cast

import structlog
from fastapi import Depends, Query, Request
from fastapi.concurrency import contextmanager_in_threadpool
from fastapi.responses import PlainTextResponse
from sqlalchemy import engine_from_config, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import DeferredReflection
from sqlalchemy.orm import Query as LegacyQuery
from sqlalchemy.orm.session import Session as SqlaSession
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.sql import Select, func, select

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support
from fastapi_sqla.models import Page

try:
    from sqlalchemy.orm import DeclarativeBase
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

    DeclarativeBase = declarative_base()  # type: ignore


logger = structlog.get_logger(__name__)

_SESSION_KEY = "fastapi_sqla_session"

_Session: dict[str, sessionmaker] = {}


class Base(DeclarativeBase, DeferredReflection):
    __abstract__ = True


def new_engine(key: str = "default") -> Engine:
    envvar_prefix = "sqlalchemy_"
    if key != "default":
        envvar_prefix = f"fastapi_sqla__{key}__sqlalchemy_{envvar_prefix}"

    lowercase_environ = {k.lower(): v for k, v in os.environ.items()}
    lowercase_environ.pop(f"{envvar_prefix}warn_20", None)
    return engine_from_config(lowercase_environ, prefix=envvar_prefix)


def is_async_dialect(engine: Engine):
    return engine.dialect.is_async if hasattr(engine.dialect, "is_async") else False


def startup(key: str = "default"):
    engine = new_engine(key)
    aws_rds_iam_support.setup(engine.engine)
    aws_aurora_support.setup(engine.engine)

    # Fail early
    try:
        with engine.connect() as connection:
            connection.execute(text("select 'OK'"))
    except Exception:
        logger.critical(
            "Fail querying db: is sqlalchemy_url envvar correctly configured?"
        )
        raise

    Base.prepare(engine)
    _Session[key] = sessionmaker(bind=engine)

    logger.info("engine startup", engine_key=key, engine=engine)


@contextmanager
def open_session(key: str = "default") -> Generator[SqlaSession, None, None]:
    """Context manager that opens a session and properly closes session when exiting.

    If no exception is raised before exiting context, session is committed when exiting
    context. If an exception is raised, session is rollbacked.
    """
    try:
        session: SqlaSession = _Session[key]()
    except KeyError as exc:
        raise Exception(
            f"No session with key {key} found, "
            "please ensure you've configured the environment variables for this key."
        ) from exc

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


async def add_session_to_request(request: Request, call_next, key: str = "default"):
    """Middleware which injects a new sqla session into every request.

    Handles creation of session, as well as commit, rollback, and closing of session.

    Usage::

        import fastapi_sqla
        from fastapi import FastApi

        app = FastApi()

        fastapi_sqla.setup(app)  # includes middleware

        @app.get("/users")
        def get_users(session: fastapi_sqla.Session):
            return session.execute(...) # use your session here
    """
    async with contextmanager_in_threadpool(open_session(key)) as session:
        # TODO: This should use request.state
        request.scope[f"{_SESSION_KEY}_{key}"] = session

        response = await call_next(request)

        is_dirty = bool(session.dirty or session.deleted or session.new)

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
            if is_dirty:
                # optimistically only log if there were uncommitted changes
                logger.warning(
                    "http error, rolling back possibly uncommitted changes",
                    status_code=response.status_code,
                )
            # since this is no-op if session is not dirty, we can always call it
            await loop.run_in_executor(None, session.rollback)

    return response


class SessionDependency:
    def __init__(self, key: str = "default") -> None:
        self.key = key

    def __call__(self, request: Request) -> SqlaSession:
        """Yield the sqlalchemy session for that request.

        It is meant to be used as a FastAPI dependency::

            from fastapi import APIRouter, Depends
            from fastapi_sqla import SqlaSession, SessionDependency

            router = APIRouter()

            @router.get("/users")
            def get_users(session: SqlaSession = Depends(SessionDependency())):
                pass
        """
        try:
            return request.scope[f"{_SESSION_KEY}_{self.key}"]
        except KeyError:  # pragma: no cover
            raise Exception(
                f"No session with key {self.key} found in request, "
                "please ensure you've setup fastapi_sqla."
            )


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
    "Dispatch on registered functions based on `query` type"
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
    page_number = offset / limit + 1
    return Page(
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
    session: SqlaSession,
    total_items: int,
    offset: int,
    limit: int,
    *,
    scalars: bool = True,
) -> Page:
    total_pages = math.ceil(total_items / limit)
    page_number = offset / limit + 1
    query = query.offset(offset).limit(limit)
    result = session.execute(query)
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


def Pagination(
    session_key: str = "default",
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


Paginate = Annotated[PaginateDependency, Depends(Pagination())]
Session = Annotated[SqlaSession, Depends(SessionDependency())]
