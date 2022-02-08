import boto3
from pydantic import BaseSettings


def get_authentication_token(host, port, user):
    session = boto3.Session()
    client = session.client("rds")
    token = client.generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return token


def set_connection_token(dialect, conn_rec, cargs, cparams):
    config = Config()

    if config.aws_rds_iam_enabled:
        cparams["password"] = get_authentication_token(
            host=cparams["host"], port=cparams["port"], user=cparams["user"]
        )


class Config(BaseSettings):
    aws_rds_iam_enabled: bool = False

    def __init__(self):
        return super().__init__()
