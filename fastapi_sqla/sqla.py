import asyncio
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.concurrency import contextmanager_in_threadpool
from fastapi.responses import PlainTextResponse
from sqlalchemy import engine_from_config, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import DeferredReflection
from sqlalchemy.orm.session import Session as SqlaSession
from sqlalchemy.orm.session import sessionmaker

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support

try:
    from sqlalchemy.orm import DeclarativeBase
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

    DeclarativeBase = declarative_base()  # type: ignore

try:
    from sqlmodel import Session as SqlaSession  # type: ignore

except ImportError:
    pass


logger = structlog.get_logger(__name__)

_DEFAULT_SESSION_KEY = "default"
_REQUEST_SESSION_KEY = "fastapi_sqla_session"
_session_factories: dict[str, sessionmaker] = {}


class Base(DeclarativeBase, DeferredReflection):
    __abstract__ = True


def new_engine(key: str = _DEFAULT_SESSION_KEY) -> Engine:
    envvar_prefix = "sqlalchemy_"
    if key != _DEFAULT_SESSION_KEY:
        envvar_prefix = f"fastapi_sqla__{key}__{envvar_prefix}"

    lowercase_environ = {k.lower(): v for k, v in os.environ.items()}
    lowercase_environ.pop(f"{envvar_prefix}warn_20", None)
    return engine_from_config(lowercase_environ, prefix=envvar_prefix)


def startup(key: str = _DEFAULT_SESSION_KEY):
    engine = new_engine(key)
    aws_rds_iam_support.setup(engine.engine)
    aws_aurora_support.setup(engine.engine)

    # Fail early
    try:
        with engine.connect() as connection:
            connection.execute(text("select 'OK'"))
    except Exception:
        logger.critical(
            f"Failed querying db for key '{key}': "
            "are the the environment variables correctly configured for this key?"
        )
        raise

    Base.prepare(engine)

    _session_factories[key] = sessionmaker(bind=engine, class_=SqlaSession)

    logger.info("engine startup", engine_key=key, engine=engine)


@contextmanager
def open_session(key: str = _DEFAULT_SESSION_KEY) -> Generator[SqlaSession, None, None]:
    """Context manager that opens a session and properly closes session when exiting.

    If no exception is raised before exiting context, session is committed when exiting
    context. If an exception is raised, session is rollbacked.
    """
    try:
        session: SqlaSession = _session_factories[key]()
    except KeyError as exc:
        raise KeyError(
            f"No session with key '{key}' found, "
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


async def add_session_to_request(
    request: Request, call_next, key: str = _DEFAULT_SESSION_KEY
):
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
        setattr(request.state, f"{_REQUEST_SESSION_KEY}_{key}", session)

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
    def __init__(self, key: str = _DEFAULT_SESSION_KEY) -> None:
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
            return getattr(request.state, f"{_REQUEST_SESSION_KEY}_{self.key}")
        except AttributeError:
            logger.exception(
                f"No session with key '{self.key}' found in request, "
                "please ensure you've setup fastapi_sqla.",
                session_key=self.key,
            )
            raise


default_session_dep = SessionDependency()
Session = Annotated[SqlaSession, Depends(default_session_dep)]
