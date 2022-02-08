import os

import boto3


def get_authentication_token(host, port, user):
    session = boto3.Session()
    client = session.client("rds")
    token = client.generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=user
    )
    return token


def set_connection_token(dialect, conn_rec, cargs, cparams):
    if os.environ.get("aws_rds_iam_enabled"):
        cparams["password"] = get_authentication_token(host=cparams["host"], port=5432, user=cparams["user"])
