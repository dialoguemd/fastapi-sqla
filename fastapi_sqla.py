import structlog
from fastapi import APIRouter
from pydantic import BaseSettings, SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm.session import sessionmaker


__all__ = ["router"]

router = APIRouter()
logger = structlog.get_logger(__name__)

_Session = sessionmaker()


class Settings(BaseSettings):
    sqlalchemy_connection_pool_size: int = 15
    sqlalchemy_connection_max_overflow: int = 15
    sqlalchemy_database_uri: SecretStr


@router.on_event("startup")
def startup():
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_database_uri.get_secret_value(),
        pool_size=settings.sqlalchemy_connection_pool_size,
        max_overflow=settings.sqlalchemy_connection_max_overflow,
    )
    _Session.configure(bind=engine)
    logger.info("startup", engine=engine, settings=settings)
