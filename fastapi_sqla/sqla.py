import asyncio
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated, Union

import structlog
from fastapi import Depends, Request, Response
from fastapi.concurrency import contextmanager_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pydantic import __version__ as pydantic_version
from sqlalchemy import engine_from_config, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.declarative import DeferredReflection
from sqlalchemy.orm.session import Session as SqlaSession
from sqlalchemy.orm.session import sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastapi_sqla import aws_aurora_support, aws_rds_iam_support

_pydantic_major = int(pydantic_version.split(".")[0])

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


def _coerce_bool_strings(data: dict) -> dict:
    """Coerce 'true'/'false' strings to bool in a dict."""
    coerced = {}
    for k, v in data.items():
        if isinstance(v, str) and v.lower() in ("true", "false"):
            coerced[k] = v.lower() == "true"
        else:
            coerced[k] = v
    return coerced


if _pydantic_major == 2:
    from pydantic import model_validator

    class _EngineConfig(BaseModel):
        """Engine configuration with typed defaults and bool coercion."""

        model_config = {"extra": "allow"}
        hide_parameters: bool = True

        @model_validator(mode="before")
        @classmethod
        def coerce_booleans(cls, data):
            return _coerce_bool_strings(data)

else:
    from pydantic import root_validator

    class _EngineConfig(BaseModel):  # type: ignore[no-redef]
        """Engine configuration with typed defaults and bool coercion."""

        hide_parameters: bool = True

        class Config:
            extra = "allow"

        @root_validator(pre=True, allow_reuse=True)
        def coerce_booleans(cls, values):  # noqa: N805
            return _coerce_bool_strings(values)


class Base(DeclarativeBase, DeferredReflection):
    __abstract__ = True


def get_envvar_prefix(key: str) -> str:
    envvar_prefix = "sqlalchemy_"
    if key != _DEFAULT_SESSION_KEY:
        envvar_prefix = f"fastapi_sqla__{key}__{envvar_prefix}"

    return envvar_prefix


def _get_engine_config(
    envvar_prefix: str,
) -> dict[str, Union[str, bool]]:
    """Build engine config dict with opinionated defaults and type coercion."""
    lowercase_env: dict[str, Union[str, bool]] = {
        k.lower(): v for k, v in os.environ.items()
    }
    lowercase_env.pop(f"{envvar_prefix}warn_20", None)

    overrides = {
        k[len(envvar_prefix) :]: v
        for k, v in lowercase_env.items()
        if k.startswith(envvar_prefix)
    }
    config = _EngineConfig(**overrides)  # type: ignore[arg-type]
    coerced = config.model_dump() if _pydantic_major == 2 else config.dict()
    for param, value in coerced.items():
        lowercase_env[f"{envvar_prefix}{param}"] = value

    return lowercase_env


def new_engine(key: str = _DEFAULT_SESSION_KEY) -> Union[Engine, Connection]:
    envvar_prefix = get_envvar_prefix(key)
    config = _get_engine_config(envvar_prefix)
    return engine_from_config(config, prefix=envvar_prefix)


def startup(key: str = _DEFAULT_SESSION_KEY):
    engine_or_connection = new_engine(key)
    aws_rds_iam_support.setup(engine_or_connection.engine)
    aws_aurora_support.setup(engine_or_connection.engine)

    # Fail early
    try:
        with engine_or_connection.engine.connect() as connection:
            connection.execute(text("select 'OK'"))
    except Exception:
        logger.critical(
            f"Failed querying db for key '{key}': "
            "are the the environment variables correctly configured for this key?"
        )
        raise

    Base.prepare(engine_or_connection.engine)

    _session_factories[key] = sessionmaker(
        bind=engine_or_connection, class_=SqlaSession
    )

    logger.info("engine startup", engine_key=key, engine=engine_or_connection)


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


class SessionMiddleware:
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

    def __init__(self, app: ASGIApp, key: str = _DEFAULT_SESSION_KEY) -> None:
        self.app = app
        self.key = key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async with contextmanager_in_threadpool(open_session(self.key)) as session:
            request = Request(scope=scope, receive=receive, send=send)
            setattr(request.state, f"{_REQUEST_SESSION_KEY}_{self.key}", session)

            async def send_wrapper(message: Message) -> None:
                if message["type"] != "http.response.start":
                    return await send(message)

                response: Response | None = None
                status_code = message["status"]
                is_dirty = bool(session.dirty or session.deleted or session.new)

                loop = asyncio.get_running_loop()

                # try to commit after response, so that we can return a proper 500
                # and not raise a true internal server error
                if status_code < 400:
                    try:
                        await loop.run_in_executor(None, session.commit)
                    except Exception:
                        logger.exception("commit failed, returning http error")
                        status_code = 500
                        response = PlainTextResponse(
                            content="Internal Server Error", status_code=status_code
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
                    await loop.run_in_executor(None, session.rollback)

                if response:
                    return await response(scope, receive, send)

                return await send(message)

            await self.app(scope, receive, send_wrapper)


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
