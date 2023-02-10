import httpx
from asgi_lifespan import LifespanManager
from pydantic import BaseModel
from pytest import fixture
from sqlalchemy import text


@fixture(scope="module", autouse=True)
def setup_tear_down(engine):
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS test_integration_user (
                       id serial primary key,
                       first_name varchar,
                       last_name varchar
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO test_integration_user
                    (first_name, last_name)
                    VALUES
                    ('Mulatu', 'Astatke'),
                    ('Jimmy', 'Hughes'),
                    ('Gill', 'Scott-Heron')
                    """
                )
            )
    yield
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("DROP TABLE test_integration_user"))


@fixture
def sqla():
    from fastapi_sqla import Base

    class SQLA:
        class User(Base):
            __tablename__ = "test_integration_user"

    return SQLA


@fixture
def model():
    class Model:
        class UserIn(BaseModel):
            first_name: str
            last_name: str

        class User(UserIn):
            id: int

            class Config:
                orm_mode = True

    return Model


@fixture
async def client(app):
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://example.local"
        ) as client:
            yield client
