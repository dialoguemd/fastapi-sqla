from unittest.mock import call, patch

from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pytest import fixture, mark
from sqlalchemy import event
from sqlalchemy.engine import Engine

pytestmark = [mark.dont_patch_engines, mark.dont_patch_sqla_event, mark.require_boto3]


@fixture
async def app(monkeypatch):
    from fastapi_sqla import setup

    app = FastAPI()

    monkeypatch.setenv("fastapi_sqla_aws_rds_iam_enabled", True)

    setup(app)

    async with LifespanManager(app):
        yield app


@fixture(autouse=True)
def boto_client_mock():
    with patch("fastapi_sqla.aws_rds_iam_support.boto3.Session") as mock_session:
        yield mock_session.return_value.client.return_value


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
def test_with_async(boto_client_mock, db_host, db_user, app):
    boto_client_mock.generate_db_auth_token.call_count == 2

    call1, call2 = boto_client_mock.generate_db_auth_token.call_args_list

    assert call1 == call2 == call(DBHostname=db_host, Port=5432, DBUsername=db_user)


@mark.sqlalchemy("1.3")
def test_without_async(boto_client_mock, db_host, db_user, app):
    boto_client_mock.generate_db_auth_token.assert_called_once_with(
        DBHostname=db_host, Port=5432, DBUsername=db_user
    )
