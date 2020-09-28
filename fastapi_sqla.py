import os

import structlog
from fastapi import FastAPI
from sqlalchemy import engine_from_config
from sqlalchemy.orm.session import sessionmaker

__all__ = ["setup"]

logger = structlog.get_logger(__name__)

_Session = sessionmaker()


def setup(app: FastAPI):
    app.add_event_handler("startup", startup)


def startup():
    engine = engine_from_config(os.environ, prefix="sqlalchemy_")
    _Session.configure(bind=engine)
    logger.info("startup", engine=engine)
