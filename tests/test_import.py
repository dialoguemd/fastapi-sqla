from pytest import mark


def test_import_sync_api():
    from fastapi_sqla import (  # noqa
        Base,
        Collection,
        Item,
        Page,
        Paginate,
        Pagination,
        Session,
        SessionDependency,
        SqlaSession,
        open_session,
        setup,
    )


@mark.require_asyncpg
@mark.sqlalchemy("1.4")
def test_import_async_api():
    from fastapi_sqla import (  # noqa
        AsyncPaginate,
        AsyncPagination,
        AsyncSession,
        AsyncSessionDependency,
        SqlaAsyncSession,
        open_async_session,
    )
