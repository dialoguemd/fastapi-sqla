from os import environ

try:
    import boto3

    boto3_installed = True
except ImportError as err:
    boto3_installed = False
    boto3_installed_err = str(err)

from functools import lru_cache

from sqlalchemy import event


def setup(engine):
    lc_environ = {k.lower(): v for k, v in environ.items()}
    aws_rds_iam_enabled = lc_environ.get("fastapi_sqla_aws_rds_iam_enabled") == "true"

    if aws_rds_iam_enabled:
        assert boto3_installed, boto3_installed_err
        # Cache the client at startup
        get_rds_client()
        event.listen(engine, "do_connect", set_connection_token)


@lru_cache
def get_rds_client():
    session = boto3.Session()
    return session.client("rds")


def get_authentication_token(host, port, user):
    client = get_rds_client()
    token = client.generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return token


def set_connection_token(dialect, conn_rec, cargs, cparams):
    cparams["password"] = get_authentication_token(
        host=cparams["host"], port=cparams.get("port", 5432), user=cparams["user"]
    )
