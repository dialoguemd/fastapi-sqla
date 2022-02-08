import os

import boto3

ENDPOINT = os.getenv("RDS_ENDPOINT", "")
REGION = os.getenv("AWS_REGION", "")
USERNAME = os.getenv("USERNAME", "")


def get_authentication_token():
    session = boto3.Session(region_name=REGION)
    client = session.client("rds")
    token = client.generate_db_auth_token(
        DBHostname=ENDPOINT, Port="5432", DBUsername=USERNAME, Region=REGION
    )
    return token


def set_connection_token(dialect, conn_rec, cargs, cparams):
    if os.getenv("RDS_ENDPOINT"):
        cparams["password"] = get_authentication_token()
