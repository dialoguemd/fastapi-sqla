import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import structlog
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession as SqlaAsyncSession
from sqlalchemy.orm.session import sessionmaker

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support
from fastapi_sqla.models import Base
from fastapi_sqla.sqla import new_engine

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
    aws_aurora_support.setup(engine.sync_engine)

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
        await connection.run_sync(lambda conn: Base.prepare(conn.engine))

    _AsyncSession.configure(bind=engine, expire_on_commit=False)
    logger.info("startup", async_engine=engine)


class AsyncSession(SqlaAsyncSession):
    def __new__(cls, request: Request):
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
async def open_session() -> AsyncGenerator[SqlaAsyncSession, None]:
    """Context manager to open an async session and properly close it when exiting.

    If no exception is raised before exiting context, session is committed when exiting
    context. If an exception is raised, session is rollbacked.
    """
    session = cast(SqlaAsyncSession, _AsyncSession())
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
