import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, Request
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


AsyncSession = Annotated[SqlaAsyncSession, Depends(AsyncSessionDependency())]
