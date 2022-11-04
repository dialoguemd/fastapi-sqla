from pytest import mark


def test_import_fastapi_sqla():
    import fastapi_sqla  # noqa


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
def test_import_async_session():
    from fastapi_sqla import AsyncSession  # noqa
