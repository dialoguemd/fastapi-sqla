try:
    import boto3

    boto3_installed = True
except ImportError as err:
    boto3_installed = False
    boto3_installed_err = str(err)

from sqlalchemy import event
from sqlalchemy.engine import Engine


def setup():
    assert boto3_installed, boto3_installed_err
    event.listen(Engine, "do_connect", _set_connection_token)


def tear_down():
    event.remove(Engine, "do_connect", _set_connection_token)


def _set_connection_token(dialect, conn_record, cargs, cparams):
    session = boto3.Session()
    client = session.client("rds")
    token = client.generate_db_auth_token(
        DBHostname=cparams["host"],
        Port=cparams.get("port", 5432),
        DBUsername=cparams["user"],
    )
    cparams["password"] = token
