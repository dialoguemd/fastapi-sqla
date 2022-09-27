from fastapi import Depends
from pydantic import BaseModel
from pytest import fixture, mark
from sqlalchemy import func, select


class Note(BaseModel):
    id: int
    content: str

    class Config:
        orm_mode = True


class NoteWithAuthorName(Note):
    author_name: str


@fixture
def app(app, user_cls, note_cls):
    from fastapi_sqla import AsyncPaginate, AsyncPagination, AsyncSession, Page

    @app.get("/v1/notes", response_model=Page[Note])
    async def async_paginated_notes(paginate: AsyncPaginate = Depends()):
        return await paginate(select(note_cls))

    async def count_notes(session: AsyncSession = Depends()):
        result = await session.execute(select(func.count(note_cls.id)))
        return result.scalar()

    CustomAsyncPaginate = AsyncPagination(query_count=count_notes)

    @app.get("/v2/notes", response_model=Page[NoteWithAuthorName])
    async def async_paginated_notes_with_author(
        paginate: CustomAsyncPaginate = Depends(),
    ):
        return await paginate(
            select(
                note_cls.id, note_cls.content, user_cls.name.label("author_name")
            ).join(user_cls),
            scalars=False,
        )

    return app


@mark.sqlalchemy("1.4")
@mark.require_asyncpg
@mark.parametrize(
    "offset, items_number, path",
    [
        [0, 10, "/v1/notes"],
        [10, 10, "/v1/notes"],
        [920, 4, "/v1/notes"],
        [0, 10, "/v2/notes"],
        [10, 10, "/v2/notes"],
        [920, 4, "/v2/notes"],
    ],
)
async def test_async_pagination(client, offset, items_number, path, nb_notes):
    result = await client.get(path, params={"offset": offset})

    assert result.status_code == 200, result.json()
    notes = result.json()["data"]
    assert len(notes) == items_number

    meta = result.json()["meta"]
    assert meta["total_items"] == nb_notes
