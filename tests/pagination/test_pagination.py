from pytest import mark, param
from sqlalchemy.orm import joinedload


@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_pagination(
    session, user_cls, offset, limit, total_pages, page_number, nb_users
):
    from fastapi_sqla import Paginate

    query = session.query(user_cls).options(joinedload(user_cls.notes))
    result = Paginate(session, offset, limit)(query)

    assert result.meta.total_items == nb_users
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@mark.sqlalchemy("1.3")
@mark.parametrize(
    "offset,limit,total_pages,page_number",
    [(0, 5, 9, 1), (10, 10, 5, 2), (40, 10, 5, 5)],
)
def test_pagination_with_legacy_query_count(
    session, user_cls, offset, limit, total_pages, page_number, nb_users
):
    from fastapi_sqla import Paginate

    query = session.query(user_cls).options(joinedload(user_cls.notes))
    result = Paginate(session, offset, limit)(query)

    assert result.meta.total_items == nb_users
    assert result.meta.offset == offset
    assert result.meta.total_pages == total_pages
    assert result.meta.page_number == page_number


@mark.parametrize(
    "offset,items_number,path",
    [
        param(0, 10, "/v1/users"),
        param(10, 10, "/v1/users"),
        param(40, 2, "/v1/users"),
        param(0, 10, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(40, 2, "/v2/users", marks=mark.sqlalchemy("1.4")),
        param(0, 10, "/v2/users-with-notes-count", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/users-with-notes-count", marks=mark.sqlalchemy("1.4")),
        param(40, 2, "/v2/users-with-notes-count", marks=mark.sqlalchemy("1.4")),
    ],
)
async def test_functional(client, offset, items_number, path, nb_users):
    result = await client.get(path, params={"offset": offset})

    assert result.status_code == 200, result.json()
    users = result.json()["data"]
    assert len(users) == items_number
    user_ids = [u["id"] for u in users]
    assert user_ids == list(range(offset + 1, offset + 1 + items_number))

    meta = result.json()["meta"]
    assert meta["total_items"] == nb_users


@mark.parametrize(
    "offset,items_number,path",
    [
        param(0, 10, "/v2/users/1/notes", marks=mark.sqlalchemy("1.4")),
        param(10, 10, "/v2/users/1/notes", marks=mark.sqlalchemy("1.4")),
        param(20, 2, "/v2/users/1/notes", marks=mark.sqlalchemy("1.4")),
    ],
)
async def test_custom_pagination(client, offset, items_number, path):
    result = await client.get(path, params={"offset": offset})

    assert result.status_code == 200, result.json()
    notes = result.json()["data"]
    assert len(notes) == items_number

    meta = result.json()["meta"]
    assert meta["total_items"] == 22


@mark.sqlalchemy("1.4")
async def test_json_result(client):
    result = await client.get("/v2/query-with-json-result")

    assert result.status_code == 200, result.json()
