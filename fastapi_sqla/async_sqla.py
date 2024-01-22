from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession as SqlaAsyncSession
from sqlalchemy.orm.session import sessionmaker

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support
from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, Base, new_engine

logger = structlog.get_logger(__name__)

_ASYNC_REQUEST_SESSION_KEY = "fastapi_sqla_async_session"
_async_session_factories: dict[str, sessionmaker] = {}


def new_async_engine(key: str = _DEFAULT_SESSION_KEY):
    engine = new_engine(key)
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

    _async_session_factories[key] = sessionmaker(
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
        session: SqlaAsyncSession = _async_session_factories[key]()
    except KeyError as exc:
        raise KeyError(
            f"No async session with key '{key}' found, "
            "please ensure you've configured the environment variables for this key."
        ) from exc

    logger.bind(db_async_session=session)

    try:
        yield session
    except Exception:
        logger.warning("context failed, rolling back", exc_info=True)
        await session.rollback()
        raise

    else:
        try:
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
        setattr(request.state, f"{_ASYNC_REQUEST_SESSION_KEY}_{key}", session)
        response = await call_next(request)

        is_dirty = bool(session.dirty or session.deleted or session.new)

        # try to commit after response, so that we can return a proper 500 response
        # and not raise a true internal server error
        if response.status_code < 400:
            try:
                await session.commit()
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
            return getattr(request.state, f"{_ASYNC_REQUEST_SESSION_KEY}_{self.key}")
        except AttributeError:
            logger.exception(
                f"No async session with key '{self.key}' found in request, "
                "please ensure you've setup fastapi_sqla.",
                session_key=self.key,
            )
            raise


default_async_session_dep = AsyncSessionDependency()
AsyncSession = Annotated[SqlaAsyncSession, Depends(default_async_session_dep)]
