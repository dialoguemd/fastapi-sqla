from unittest.mock import Mock, patch

from pytest import raises


def test_with_session_raise_exception_if_middleware_not_in_scope():
    from fastapi_sqla import with_session

    request = Mock(scope={})
    with raises(Exception):
        with_session(request)


def test_with_session():
    from fastapi_sqla import with_session

    request = Mock(scope={"fastapi_sqla_middleware": True})

    with patch("fastapi_sqla._Session") as _Session:
        session = with_session(request)

    assert session == _Session.return_value
