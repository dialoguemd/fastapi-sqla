from unittest.mock import Mock

from pytest import fixture, mark, raises
from structlog.testing import capture_logs


@fixture
def session():
    return Mock()


@mark.parametrize("status_code", [200, 201, 202, 300, 301, 302])
def test_complete_session_does_a_commit(status_code, session):
    from fastapi_sqla import complete_session

    complete_session(session, status_code)

    assert session.rollback.called is False
    session.commit.assert_called_with()
    session.close.assert_called_with()


@mark.parametrize("status_code", [400, 401, 403, 404, 500])
def test_complete_session_does_a_crollback(status_code, session):
    from fastapi_sqla import complete_session

    complete_session(session, status_code)

    assert session.commit.called is False
    session.rollback.assert_called_with()
    session.close.assert_called_with()


@mark.parametrize(
    "func_name, status_code",
    [
        ("commit", 200),
        ("commit", 201),
        ("commit", 202),
        ("commit", 300),
        ("commit", 301),
        ("commit", 302),
        ("rollback", 400),
        ("rollback", 401),
        ("rollback", 403),
        ("rollback", 404),
        ("rollback", 500),
    ],
)
def test_complete_session_raises_on_commit_and_rollback_exception(
    func_name, status_code, session
):
    from fastapi_sqla import complete_session

    session.commit.side_effect = session.rollback.side_effect = Exception()
    with raises(Exception), capture_logs() as caplog:
        complete_session(session, status_code)

    assert {"event": f"{func_name} failed", "log_level": "exception"} in caplog
