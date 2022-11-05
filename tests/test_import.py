from pytest import mark, raises


def test_import_sync_api():
    from fastapi_sqla import (  # noqa
        Base,
        Collection,
        Item,
        Page,
        Paginate,
        Session,
        open_session,
        setup,
    )


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
def test_import_async_api():
    from fastapi_sqla import (  # noqa
        AsyncSession,
        AsyncPagination,
        AsyncPaginate,
        open_async_session,
    )
