import os

import structlog
from fastapi import APIRouter
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import sessionmaker

__all__ = ["router"]

router = APIRouter()
logger = structlog.get_logger(__name__)

_Session = sessionmaker()


@router.on_event("startup")
def startup():
    """Setup sqlalchemy.

    Create the sqla engine instance using environment variables.
    The keys of interest in `os.environ` are prefixed with `sqlalchemy_`.
    Each matching key (after the prefix is stripped) is treated as though it were the
    corresponding keyword argument to [`sqlalchemy.create_engine`]
    (https://docs.sqlalchemy.org/en/13/core/engines.html?highlight=create_engine#sqlalchemy.create_engine)  # noqa
    call.

    The only required key is `sqlalchemy_url`, which provides the database URL.
    """
    engine = engine_from_config(os.environ, prefix="sqlalchemy_")
    _Session.configure(bind=engine)
    logger.info("startup", engine=engine)
