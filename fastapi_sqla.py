import asyncio
import os
from contextlib import contextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.concurrency import contextmanager_in_threadpool
from sqlalchemy import engine_from_config
from sqlalchemy.ext.declarative import DeferredReflection, declarative_base
from sqlalchemy.orm.session import Session, sessionmaker

__all__ = ["Base", "setup", "with_session"]

logger = structlog.get_logger(__name__)

_SESSION_KEY = "fastapi_sqla_session"

_Session = sessionmaker()


def setup(app: FastAPI):
    app.add_event_handler("startup", startup)
    app.middleware("http")(add_session_to_request)


def startup():
    engine = engine_from_config(os.environ, prefix="sqlalchemy_")
    Base.metadata.bind = engine
    Base.prepare(engine)
    _Session.configure(bind=engine)
    logger.info("startup", engine=engine)


class Base(declarative_base(cls=DeferredReflection)):  # type: ignore
    __abstract__ = True


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
        session.commit()

    except Exception:
        logger.exception("commit failed. Rolling back")
        session.rollback()
        raise

    finally:
        session.close()


def with_session(request: Request) -> Session:
    """Yield the sqlalchmey session for that request.

    It is meant to be used as a FastAPI® dependency::

        from er import sqla
        from fastapi import APIRouter, Depends

        router = APIRouter()

        @router.get("/users")
        def get_users(db: sqla.Session = Depends(sqla.with_session)):
            pass
    """
    try:
        yield request.scope[_SESSION_KEY]
    except KeyError:  # pragma: no cover
        raise Exception(
            "No session found in request, please ensure you've setup fastapi_sqla."
        )


async def add_session_to_request(request: Request, call_next):
    """Middleware which injects a new sqla session into every request.

    Handles creation of session, as well as commit, rollback, and closing of session.

    Usage::

        import fastapi_sqla
        from fastapi import FastApi

        app = FastApi()

        fastapi_sqla.setup(app)  # includes middleware

        @app.get("/users")
        def get_users(session: sqla.Session = Depends(sqla.new_session)):
            return session.query(...) # use your session here
    """
    async with contextmanager_in_threadpool(open_session()) as session:
        request.scope[_SESSION_KEY] = session
        response = await call_next(request)
        if response.status_code >= 400:
            # If ever a route handler returns an http exception, we do not want the
            # session opened by current context manager to commit anything in db.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, session.rollback)

    return response
