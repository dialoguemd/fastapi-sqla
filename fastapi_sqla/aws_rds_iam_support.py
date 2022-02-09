try:
    import boto3

    boto3_installed = True
except ImportError as err:
    boto3_installed = False
    boto3_installed_err = str(err)

from pydantic import BaseSettings
from sqlalchemy import event


def setup(engine):
    config = Config()

    if config.aws_rds_iam_enabled:
        assert boto3_installed, boto3_installed_err
        event.listen(engine, "do_connect", set_connection_token)


def get_authentication_token(host, port, user):
    session = boto3.Session()
    client = session.client("rds")
    token = client.generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return token


def set_connection_token(dialect, conn_rec, cargs, cparams):
    cparams["password"] = get_authentication_token(
        host=cparams["host"], port=cparams.get("port", 5432), user=cparams["user"]
    )


class Config(BaseSettings):
    aws_rds_iam_enabled: bool = False

    class Config:
        env_prefix = "fastapi_sqla_"
