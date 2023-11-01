import asyncio
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Union

import structlog
from fastapi import Request
from fastapi.concurrency import contextmanager_in_threadpool
from fastapi.responses import PlainTextResponse
from sqlalchemy import engine_from_config, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm.session import Session as SqlaSession
from sqlalchemy.orm.session import sessionmaker

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support
from fastapi_sqla.models import Base

logger = structlog.get_logger(__name__)

_SESSION_KEY = "fastapi_sqla_session"

_Session = sessionmaker()


def new_engine(*, envvar_prefix: Union[str, None] = None) -> Engine:
    envvar_prefix = envvar_prefix if envvar_prefix else "sqlalchemy_"
    lowercase_environ = {
        k.lower(): v for k, v in os.environ.items() if k.lower() != "sqlalchemy_warn_20"
    }
    return engine_from_config(lowercase_environ, prefix=envvar_prefix)


def startup():
    engine = new_engine()
    aws_rds_iam_support.setup(engine.engine)
    aws_aurora_support.setup(engine.engine)

    # Fail early:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 'OK'"))
    except Exception:
        logger.critical(
            "Fail querying db: is sqlalchemy_url envvar correctly configured?"
        )
        raise

    Base.prepare(engine)
    _Session.configure(bind=engine)
    logger.info("startup", engine=engine)


class Session(SqlaSession):
    def __new__(cls, request: Request):
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
def open_session() -> Generator[SqlaSession, None, None]:
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
