import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Union

import structlog
from fastapi import Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_engine_from_config,
)
from sqlalchemy.ext.asyncio import AsyncSession as SqlaAsyncSession
from sqlalchemy.orm.session import sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support
from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, Base, get_envvar_prefix

logger = structlog.get_logger(__name__)

_ASYNC_REQUEST_SESSION_KEY = "fastapi_sqla_async_session"
_async_session_factories: dict[str, sessionmaker] = {}


def new_async_engine(
    key: str = _DEFAULT_SESSION_KEY,
) -> Union[AsyncEngine, AsyncConnection]:
    envvar_prefix = get_envvar_prefix(key)
    lowercase_environ = {k.lower(): v for k, v in os.environ.items()}
    lowercase_environ.pop(f"{envvar_prefix}warn_20", None)
    return async_engine_from_config(lowercase_environ, prefix=envvar_prefix)


async def startup(key: str = _DEFAULT_SESSION_KEY):
    engine_or_connection = new_async_engine(key)
    aws_rds_iam_support.setup(engine_or_connection.sync_engine)
    aws_aurora_support.setup(engine_or_connection.sync_engine)

    async_engine = (
        engine_or_connection
        if isinstance(engine_or_connection, AsyncEngine)
        else engine_or_connection.engine
    )

    # Fail early
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("select 'ok'"))
    except Exception:
        logger.critical(
            f"Failed querying db for key '{key}': "
            "are the the environment variables correctly configured for this key?"
        )
        raise

    async with async_engine.connect() as connection:
        await connection.run_sync(lambda conn: Base.prepare(conn.engine))

    # TODO: Use async_sessionmaker once only supporting 2.x+
    _async_session_factories[key] = sessionmaker(
        class_=SqlaAsyncSession, bind=engine_or_connection, expire_on_commit=False
    )  # type: ignore

    logger.info("engine startup", engine_key=key, async_engine=engine_or_connection)


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


class AsyncSessionMiddleware:
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

    def __init__(self, app: ASGIApp, key: str = _DEFAULT_SESSION_KEY) -> None:
        self.app = app
        self.key = key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async with open_session(self.key) as session:
            request = Request(scope=scope, receive=receive, send=send)
            setattr(request.state, f"{_ASYNC_REQUEST_SESSION_KEY}_{self.key}", session)

            async def send_wrapper(message: Message) -> None:
                if message["type"] != "http.response.start":
                    return await send(message)

                response: Response | None = None
                status_code = message["status"]
                is_dirty = bool(session.dirty or session.deleted or session.new)

                # try to commit after response, so that we can return a proper 500
                # and not raise a true internal server error
                if status_code < 400:
                    try:
                        await session.commit()
                    except Exception:
                        logger.exception("commit failed, returning http error")
                        status_code = 500
                        response = PlainTextResponse(
                            content="Internal Server Error", status_code=500
                        )

                if status_code >= 400:
                    # If ever a route handler returns an http exception,
                    # we do not want the current session to commit anything in db.
                    if is_dirty:
                        # optimistically only log if there were uncommitted changes
                        logger.warning(
                            "http error, rolling back possibly uncommitted changes",
                            status_code=status_code,
                        )
                    # since this is no-op if the session is not dirty,
                    # we can always call it
                    await session.rollback()

                if response:
                    return await response(scope, receive, send)

                return await send(message)

            await self.app(scope, receive, send_wrapper)


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
