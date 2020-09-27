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
    engine = engine_from_config(os.environ, prefix="sqlalchemy_")
    _Session.configure(bind=engine)
    logger.info("startup", engine=engine)
