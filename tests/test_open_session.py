from unittest.mock import patch
from pytest import fixture, raises


@fixture
def _Session():
    with patch("fastapi_sqla._Session") as _Session:
        yield _Session


def test_open_session(_Session):
    from fastapi_sqla import open_session

    with open_session() as session:
        pass

    session.commit.assert_called_once_with()
    session.close.assert_called_once_with()


def test_open_session_rollback_on_exception(_Session):
    from fastapi_sqla import open_session

    with raises(Exception), open_session() as session:
        raise Exception()

    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()
