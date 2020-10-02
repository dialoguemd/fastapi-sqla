import asyncio
import os
from contextlib import contextmanager

import structlog
from fastapi import FastAPI, Request
from sqlalchemy import engine_from_config
from sqlalchemy.ext.declarative import DeferredReflection, declarative_base
from sqlalchemy.orm.session import Session, sessionmaker

__all__ = ["Base", "setup", "with_session"]

logger = structlog.get_logger(__name__)

_Session = sessionmaker()


def setup(app: FastAPI):
    app.add_event_handler("startup", startup)
    app.middleware("http")(handle_session_completion)


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
        logger.debug("committing")
        session.commit()
    except Exception:
        logger.exception("rolling back")
        session.rollback()
        raise
    finally:
        session.close()


def with_session(request: Request) -> Session:
    """Open and yield an sqlalchmey session for that request.

    It is meant to be used as a FastAPI® dependency::

        from er import sqla
        from fastapi import APIRouter, Depends

        router = APIRouter()

        @router.get("/users")
        def get_users(db: sqla.Session = Depends(sqla.with_session)):
            pass
    """
    if "fastapi_sqla_middleware" not in request.scope:
        msg = (
            "fastapi_sqla middleware not configured using fastapi_sqla.setup. "
            "Please consult fastapi_sqle README"
        )
        logger.critical(msg)
        raise Exception(msg)

    session = _Session()
    logger.bind(db_session=session)
    request.scope["sqla_session"] = session
    return session


async def handle_session_completion(request: Request, call_next):
    """Middleware to handle sqla session completion after every request.

    Handles session commit, rollback, and closing.

    Usage::

        import fastapi_sqla
        from fastapi import FastApi

        app = FastApi()

        fastapi_sqla.setup(app)  # includes middleware

        @app.get("/users")
        def get_users(session: sqla.Session = Depends(sqla.with_session)):
            return session.query(...) # use your session here
    """
    request.scope["fastapi_sqla_middleware"] = True  # sometimes, boolean works 🐱
    response = await call_next(request)

    if "sqla_session" in request.scope:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            None, complete_session, request["sqla_session"], response.status_code,
        )

    return response


def complete_session(session: Session, status_code: int):
    """Closing session after commiting or rollbacking."""
    func = session.rollback if status_code >= 400 else session.commit

    try:
        func()

    except Exception:
        logger.exception(f"{func} failed")
        raise

    finally:
        session.close()
