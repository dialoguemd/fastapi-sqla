# Fastapi-SQLA

[![codecov](https://codecov.io/gh/dialoguemd/fastapi-sqla/branch/master/graph/badge.svg?token=BQHLryClIn)](https://codecov.io/gh/dialoguemd/fastapi-sqla)
[![CircleCI](https://dl.circleci.com/status-badge/img/gh/dialoguemd/fastapi-sqla/tree/master.svg?style=svg)](https://dl.circleci.com/status-badge/redirect/gh/dialoguemd/fastapi-sqla/tree/master)
![PyPI](https://img.shields.io/pypi/v/fastapi-sqla)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-brightgreen.svg)](https://conventionalcommits.org)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)


Fastapi-SQLA is an [SQLAlchemy] extension for [FastAPI] easy to setup with support for
pagination, asyncio, [SQLModel] and [pytest].
It supports SQLAlchemy>=1.3 and is fully compliant with [SQLAlchemy 2.0].
It is developped, maintained and used on production by the team at [@dialoguemd] with
love from Montreal 🇨🇦.

# Installing

Using [pip](https://pip.pypa.io/):
```
pip install fastapi-sqla
```

# Quick Example

Assuming it runs against a DB with a table `user` with 3 columns, `id`, `name` and
unique `email`:

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi_sqla import Base, Item, Page, Paginate, Session, setup_middlewares, startup
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup()
    yield


app = FastAPI(lifespan=lifespan)
setup_middlewares(app)


class User(Base):
    __tablename__ = "user"


class UserIn(BaseModel):
    name: str
    email: EmailStr


class UserModel(UserIn):
    id: int

    class Config:
        orm_mode = True


@app.get("/users", response_model=Page[UserModel])
def list_users(paginate: Paginate):
    return paginate(select(User))


@app.get("/users/{user_id}", response_model=Item[UserModel])
def get_user(user_id: int, session: Session):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404)
    return {"data": user}


@app.post("/users", response_model=Item[UserModel])
def create_user(new_user: UserIn, session: Session):
    user = User(**new_user.model_dump())
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(409, "Email is already taken.")
    return {"data": user}
```

Creating a db using `sqlite3`:
```bash
sqlite3 db.sqlite <<EOF
CREATE TABLE user (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    name  TEXT NOT NULL
);
CREATE UNIQUE INDEX user_email_idx ON user (email);
EOF
```

Running the app:
```bash
sqlalchemy_url=sqlite:///db.sqlite?check_same_thread=false uvicorn main:app
```

# Configuration

## Environment variables:

The keys of interest in `os.environ` are prefixed with `sqlalchemy_`.
Each matching key (after the prefix is stripped) is treated as though it were the
corresponding keyword argument to [`sqlalchemy.create_engine`]
call.

The only required key is `sqlalchemy_url`, which provides the database URL, example:

```bash
export sqlalchemy_url=postgresql://postgres@localhost
```

### Multi-session support

In order to configure multiple sessions for the application, 
set the environment variables with this prefix format: `fastapi_sqla__MY_KEY__`.

As with the default session, each matching key (after the prefix is stripped) 
is treated as though it were the corresponding keyword argument to [`sqlalchemy.create_engine`]
call.

For example, to configure a session with the `read_only` key:

```bash
export fastapi_sqla__read_only__sqlalchemy_url=postgresql://postgres@localhost
```

### `asyncio` support using [`asyncpg`]

SQLAlchemy `>= 1.4` supports `asyncio`.
To enable `asyncio` support against a Postgres DB, install `asyncpg`:

```bash
pip install asyncpg
```

And define the environment variable `sqlalchemy_url` with `postgres+asyncpg` scheme:

```bash
export sqlalchemy_url=postgresql+asyncpg://postgres@localhost
```

## Setup the app AsyncContextManager (recommended):

```python
import fastapi_sqla
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    await fastapi_sqla.startup()
    yield


app = FastAPI(lifespan=lifespan)
fastapi_sqla.setup_middlewares(app)
```

## Setup the app using startup/shutdown events (deprecated):

```python
import fastapi_sqla
from fastapi import FastAPI

app = FastAPI()
fastapi_sqla.setup(app)
```

# SQLAlchemy

## Adding a new entity class:

```python
from fastapi_sqla import Base


class Entity(Base):
    __tablename__ = "table-name-in-db"
```

## Getting an sqla session

### Using dependency injection

Use [FastAPI dependency injection] to get a session as a parameter of a path operation
function.

The SQLAlchemy session is committed before the response is returned or rollbacked if any
exception occurred:

```python
from fastapi import APIRouter
from fastapi_sqla import AsyncSession, Session

router = APIRouter()


@router.get("/example")
def example(session: Session):
    return session.execute("SELECT now()").scalar()


@router.get("/async_example")
async def async_example(session: AsyncSession):
    return await session.scalar("SELECT now()")
```

In order to get a session configured with a custom key:

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_sqla import (
    AsyncSessionDependency,
    SessionDependency,
    SqlaAsyncSession,
    SqlaSession,
)

router = APIRouter()


# Preferred

ReadOnlySession = Annotated[SqlaSession, Depends(SessionDependency(key="read_only"))]
AsyncReadOnlySession = Annotated[
    SqlaAsyncSession, Depends(AsyncSessionDependency(key="read_only"))
]

@router.get("/example")
def example(session: ReadOnlySession):
    return session.execute("SELECT now()").scalar()


@router.get("/async_example")
async def async_example(session: AsyncReadOnlySession):
    return await session.scalar("SELECT now()")


# Alternative

@router.get("/example/alt")
def example_alt(session: SqlaSession = Depends(SessionDependency(key="read_only"))):
    return session.execute("SELECT now()").scalar()


@router.get("/async_example/alt")
async def async_example_alt(
    session: SqlaAsyncSession = Depends(AsyncSessionDependency(key="read_only")),
):
    return await session.scalar("SELECT now()")
```

### Using a context manager

When needing a session outside of a path operation, like when using
[FastAPI background tasks], use `fastapi_sqla.open_session` context manager.
The SQLAlchemy session is committed when exiting context or rollbacked if any exception
occurred:

```python
from fastapi import APIRouter, BackgroundTasks
from fastapi_sqla import open_async_session, open_session

router = APIRouter()


@router.get("/example")
def example(bg: BackgroundTasks):
    bg.add_task(run_bg)
    bg.add_task(run_async_bg)


def run_bg():
    with open_session() as session:
        session.execute("SELECT now()").scalar()

def run_bg_with_key():
    with open_session(key="read_only") as session:
        session.execute("SELECT now()").scalar()

async def run_async_bg():
    async with open_async_session() as session:
        await session.scalar("SELECT now()")

async def run_async_bg_with_key():
    async with open_async_session(key="read_only") as session:
        await session.scalar("SELECT now()")
```

## Pagination

```python
from fastapi import APIRouter
from fastapi_sqla import Base, Page, Paginate
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter()


class User(Base):
    __tablename__ = "user"


class UserModel(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


@router.get("/users", response_model=Page[UserModel])
def all_users(paginate: Paginate):
    return paginate(select(User))
```

By default:

* It returns pages of 10 items, up to 100 items;
* Total number of items in the collection is queried using [`Query.count`].
* Response example for `/users?offset=40&limit=10`:

    ```json
    {
        "data": [
            {
                "id": 41,
                "name": "Pat Thomas"
            },
            {
                "id": 42,
                "name": "Mulatu Astatke"
            }
        ],
        "meta": {
            "offset": 40,
            "total_items": 42,
            "total_pages": 5,
            "page_number": 5
        }
    }
    ```

### Paginating non-scalar results

To paginate a query which doesn't return [scalars], specify `scalars=False` when invoking
`paginate`:

```python
from fastapi import APIRouter
from fastapi_sqla import Base, Page, Paginate
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import relationship

router = APIRouter()


class User(Base):
    __tablename__ = "user"
    notes = relationship("Note")


class Note(Base):
    __tablename__ = "note"


class UserModel(BaseModel):
    id: int
    name: str
    notes_count: int


@router.get("/users", response_model=Page[UserModel])
def all_users(paginate: Paginate):
    query = (
        select(User.id, User.name, func.count(Note.id).label("notes_count"))
        .join(Note)
        .group_by(User)
    )
    return paginate(query, scalars=False)
```


### Customize pagination

You can customize:
- Minimum and maximum number of items per pages;
- How the total number of items in the collection is queried;

To customize pagination, create a dependency using `fastapi_sqla.Pagination`:

```python
from fastapi import APIRouter, Depends
from fastapi_sqla import Base, Page, Pagination, Session
from pydantic import BaseModel
from sqlalchemy import func, select

router = APIRouter()


class User(Base):
    __tablename__ = "user"


class UserModel(BaseModel):
    id: int
    name: str


def query_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(User)).scalar()


CustomPaginate = Pagination(min_page_size=5, max_page_size=500, query_count=query_count)


@router.get("/users", response_model=Page[UserModel])
def all_users(paginate: CustomPaginate = Depends()):
    return paginate(select(User))
```

### Async pagination

When using the asyncio support, use the `AsyncPaginate` dependency:

```python
from fastapi import APIRouter
from fastapi_sqla import Base, Page, AsyncPaginate
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter()


class User(Base):
    __tablename__ = "user"


class UserModel(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


@router.get("/users", response_model=Page[UserModel])
async def all_users(paginate: AsyncPaginate):
    return await paginate(select(User))
```

Customize pagination by creating a dependency using `fastapi_sqla.AsyncPagination`:

```python
from fastapi import APIRouter, Depends
from fastapi_sqla import Base, Page, AsyncPagination, AsyncSession
from pydantic import BaseModel
from sqlalchemy import func, select

router = APIRouter()


class User(Base):
    __tablename__ = "user"


class UserModel(BaseModel):
    id: int
    name: str


async def query_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar()


CustomPaginate = AsyncPagination(min_page_size=5, max_page_size=500, query_count=query_count)


@router.get("/users", response_model=Page[UserModel])
async def all_users(paginate: CustomPaginate = Depends()):
    return await paginate(select(User))
```

### Multi-session support

Pagination supports multiple sessions as well. To paginate using a session 
configured with a custom key:

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_sqla import (
    AsyncPaginateSignature,
    AsyncPagination,
    Base,
    Page,
    PaginateSignature,
    Pagination,
)
from pydantic import BaseModel
from sqlalchemy import func, select

router = APIRouter()


class User(Base):
    __tablename__ = "user"


class UserModel(BaseModel):
    id: int
    name: str


# Preferred

ReadOnlyPaginate = Annotated[
    PaginateSignature, Depends(Pagination(session_key="read_only"))
]
AsyncReadOnlyPaginate = Annotated[
    AsyncPaginateSignature, Depends(AsyncPagination(session_key="read_only"))
]

@router.get("/users", response_model=Page[UserModel])
def all_users(paginate: ReadOnlyPaginate):
    return paginate(select(User))

@router.get("/async_users", response_model=Page[UserModel])
async def async_all_users(paginate: AsyncReadOnlyPaginate):
    return await paginate(select(User))


# Alternative

@router.get("/users/alt", response_model=Page[UserModel])
def all_users_alt(
    paginate: PaginateSignature = Depends(
        Pagination(session_key="read_only")
    ),
):
    return paginate(select(User))

@router.get("/async_users/alt", response_model=Page[UserModel])
async def async_all_users_alt(
    paginate: AsyncPaginateSignature = Depends(
        AsyncPagination(session_key="read_only")
    ),
):
    return await paginate(select(User))
```

# SQLModel support 🎉

If your project uses [SQLModel], then `Session` dependency is an SQLModel session::

```python
    from http import HTTPStatus

    from fastapi import FastAPI, HTTPException
    from fastapi_sqla import Item, Page, Paginate, Session, setup
    from sqlmodel import Field, SQLModel, select

    class Hero(SQLModel, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str
        secret_name: str
        age: int | None = None


    app = FastAPI()
    setup(app)

    @app.get("/heros", response_model=Page[Hero])
    def list_hero(paginate: Paginate) -> Page[Hero]:
        return paginate(select(Hero))


    @app.get("/heros/{hero_id}", response_model=Item[Hero])
    def get_hero(hero_id: int, session: Session) -> Item[Hero]:
        hero = session.get(Hero, hero_id)
        if hero is None:
            raise HTTPException(HTTPStatus.NOT_FOUND)
        return {"data": hero}

```

# Pytest fixtures

This library provides a set of utility fixtures, through its PyTest plugin, which is
automatically installed with the library.

By default, no records are actually written to the database when running tests.
There currently is no way to change this behaviour.

## `sqla_modules`

You must define this fixture, in order for the plugin to reflect table metadata in your
SQLAlchemy entities. It should just import all of the application's modules which contain
SQLAlchemy models.

Example:

```python
# tests/conftest.py
from pytest import fixture


@fixture
def sqla_modules():
    from app import sqla  # noqa
```

## `db_url`

The DB url to use.

When `CI` key is set in environment variables, it defaults to using `postgres` as the
host name:

```
postgresql://postgres@postgres/postgres
```

In other cases, the host is set to `localhost`:

```
postgresql://postgres@localhost/postgres
```

Of course, you can override it by overloading the fixture:

```python
from pytest import fixture


@fixture(scope="session")
def db_url():
    return "postgresql://postgres@localhost/test_database"
```

## `async_sqlalchemy_url`

DB url to use when using `asyncio` support. Defaults to `db_url` fixture with
`postgresql+asyncpg://` scheme.


## `session` & `async_session`

Sqla sessions to create db fixture:
* All changes done at test setup or during the test are rollbacked at test tear down;
* No record will actually be written in the database;
* Changes in one regular session need to be committed to be available from other regular
  sessions;
* Changes in one async session need to be committed to be available from other async
  sessions;
* Changes from regular sessions are not available from `async` session and vice-versa
  even when committed;

Example:
```python
from pytest import fixture


@fixture
def patient(session):
    from er.sqla import Patient
    patient = Patient(first_name="Bob", last_name="David")
    session.add(patient)
    session.commit()
    return patient


@fixture
async def doctor(async_session):
    from er.sqla import Doctor
    doctor = Doctor(name="who")
    async_session.add(doctor)
    await async_session.commit()
    return doctor
```

## `db_migration`

A session scope fixture that runs `alembic upgrade` at test session setup and
`alembic downgrade` at tear down.

It depends on `alembic_ini_path` fixture to get the path of `alembic.ini` file.

To use in a test or test module:

```python
from pytest import mark

pytestmark = mark.usefixtures("db_migration")
```

To use globally, add to [pytest options]:

 ```ini
 [pytest]
 usefixtures =
     db_migration
 ```

Or depends on it in top-level `conftest.py` and mark it as _auto-used_:

```python
from pytest import fixture


@fixture(scope="session", autouse=True)
def db_migration(db_migration):
    pass
```

## `alembic_ini_path`

It returns the path of  `alembic.ini` configuration file. By default, it returns
`./alembic.ini`.


# Development

## Prerequisites

- **Python >=3.9**
- [**Poetry**](https://poetry.eustace.io/) to install package dependencies.
- A postgres DB reachable at `postgresql://postgres@localhost/postgres`


## Setup

```bash
$ poetry install --extras tests --extras asyncpg --extras aws_rds_iam
```

## Running tests

```bash
$ poetry run pytest
```

#### Runing tests on multiple environments

```bash
$ poetry run tox
```

[`sqlalchemy.create_engine`]: https://docs.sqlalchemy.org/en/20/core/engines.html#sqlalchemy.create_engine
[`Query.count`]: https://docs.sqlalchemy.org/en/20/orm/queryguide/query.html#sqlalchemy.orm.Query.count
[pytest options]: https://docs.pytest.org/en/stable/reference.html#confval-usefixtures
[FastAPI]: https://fastapi.tiangolo.com/
[FastAPI dependency injection]: https://fastapi.tiangolo.com/tutorial/dependencies/
[FastAPI background tasks]: https://fastapi.tiangolo.com/tutorial/background-tasks/
[SQLAlchemy]: http://sqlalchemy.org/
[SQLAlchemy 2.0]: https://docs.sqlalchemy.org/en/20/changelog/migration_20.html
[SQLModel]: https://sqlmodel.tiangolo.com
[`asyncpg`]: https://magicstack.github.io/asyncpg/current/
[scalars]: https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Result.scalars
[alembic]: https://alembic.sqlalchemy.org/
[pytest]: https://docs.pytest.org/
[@dialoguemd]: https://github.com/dialoguemd
