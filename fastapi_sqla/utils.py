import os

import boto3

ENDPOINT = os.getenv("RDS_ORIGIN", "")
REGION = os.getenv("AWS_DEFAULT_REGION", "")
USERNAME = os.getenv("SQLA_USERNAME", "")
PORT = "5432"

RDS_DB_URL = f"postgresql://{USERNAME}@{ENDPOINT}:{PORT}/{USERNAME}"

def get_db_url():
    if os.getenv("RDS_ENDPOINT"):
        return RDS_DB_URL
    else:
        return os.getenv("sqlalchemy_url")

def get_async_db_url():
    if os.getenv("RDS_ENDPOINT"):
        return RDS_DB_URL
    else:
        return os.getenv("async_sqlalchemy_url", "")


def get_authentication_token():
    session = boto3.Session(region_name=REGION)
    client = session.client("rds")
    token = client.generate_db_auth_token(
        DBHostname=ENDPOINT, Port=PORT, DBUsername=USERNAME, Region=REGION
    )
    return token


def set_connection_token(dialect, conn_rec, cargs, cparams):
    if os.getenv("RDS_ENDPOINT"):
        cparams["password"] = get_authentication_token()
