from pydantic import BaseSettings
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import ExceptionContext

# Taken from
# https://www.postgresql.org/docs/current/errcodes-appendix.html#ERRCODES-TABLE
READONLY_ERROR_CODE = "25006"


def setup(engine: Engine):
    config = Config()

    if not config.aws_aurora_enabled:
        return

    event.listen(engine, "handle_error", disconnect_on_readonly_error)


def disconnect_on_readonly_error(context: ExceptionContext):
    if context.is_disconnect:
        return

    error_code = getattr(context.original_exception, "pgcode", None)
    if error_code == READONLY_ERROR_CODE:
        context.is_disconnect = True  # type: ignore


class Config(BaseSettings):
    aws_aurora_enabled: bool = False

    class Config:
        env_prefix = "fastapi_sqla_"
