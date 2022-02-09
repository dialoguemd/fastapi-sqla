# fastapi-sqla

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-brightgreen.svg)](https://conventionalcommits.org)
[![CircleCI](https://circleci.com/gh/dialoguemd/fastapi-sqla.svg?style=svg&circle-token=998482f269270ee521aa54f2accbee2e22943743)](https://circleci.com/gh/dialoguemd/fastapi-sqla)
[![codecov](https://codecov.io/gh/dialoguemd/fastapi-sqla/branch/master/graph/badge.svg?token=BQHLryClIn)](https://codecov.io/gh/dialoguemd/fastapi-sqla)

A highly opinionated [SQLAlchemy] extension for [FastAPI]:

* Setup using environment variables to connect on DB;
* `fastapi_sqla.Base` a declarative base class to reflect DB tables at startup;
* `fastapi_sqla.Session` a dependency to get an sqla session;
* `fastapi_sqla.open_session` a context manager to get an sqla session;
* `fastapi_sqla.asyncio_support.AsyncSession` a dependency to get an async sqla session ;
* `fastapi_sqla.asyncio_support.open_session` a context manager to get an async sqla
  session;
* Automated commit/rollback of sqla session at the end of request before returning
  response;
* Pagination utilities;
* Pytest fixtures;

# Configuration

## Environment variables:

The keys of interest in `os.environ` are prefixed with `sqlalchemy_`.
Each matching key (after the prefix is stripped) is treated as though it were the
corresponding keyword argument to [`sqlalchemy.create_engine`]
call.

The only required key is `sqlalchemy_url`, which provides the database URL.

### `asyncio` support using [`asyncpg`]

SQLAlchemy `>= 1.4` supports `asyncio`.
To enable `asyncio` support against a Postgres DB, install `asyncpg`:

```bash
pip install asyncpg
```

And define environment variable `async_sqlalchemy_url` with `postgres+asyncpg` scheme:

```bash
export async_sqlalchemy_url=postgresql+asyncpg://postgres@localhost
```

## Setup the app:

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
SQLAlchemy session is committed before response is returned or rollbacked if any
exception occurred:

```python
from fastapi import APIRouter, Depends
from fastapi_sqla import Session
from fastapi_sqla.asyncio_support import AsyncSession

router = APIRouter()


@router.get("/example")
def example(session: Session = Depends()):
    return session.execute("SELECT now()").scalar()


@router.get("/async_example")
async def async_example(session: AsyncSession = Depends()):
    return await session.scalar("SELECT now()")
```

### Using a context manager

When needing a session outside of a path operation, like when using
[FastAPI background tasks], use `fastapi_sqla.open_session` context manager.
SQLAlchemy session is committed when exiting context or rollbacked if any exception
occurred:

```python
from fastapi import APIRouter, BackgroundTasks
from fastapi_sqla import open_session
from fastapi_sqla import asyncio_support

router = APIRouter()


@router.get("/example")
def example(bg: BackgroundTasks):
    bg.add_task(run_bg)
    bg.add_task(run_async_bg)


def run_bg():
    with open_session() as session:
        session.execute("SELECT now()").scalar()


async def run_async_bg():
    async with asyncio_support.open_session() as session:
        await session.scalar("SELECT now()")
```

## Pagination

```python
from fastapi import APIRouter, Depends
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
def all_users(paginate: Paginate = Depends()):
    return paginate(select(User))
```

By default:

* It returns pages of 10 items, up to 100 items;
* Total number of items in the collection is queried using [`Query.count`] for legacy
  orm queries and the equivalent for 2.0 style queries.
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
from fastapi import APIRouter, Depends
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
def all_users(paginate: Paginate = Depends()):
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


def query_count(session: Session = Depends()) -> int:
    return session.execute(select(func.count()).select_from(User)).scalar()


Paginate = Pagination(min_page_size=5, max_page_size=500, query_count=query_count)


@router.get("/users", response_model=Page[UserModel])
def all_users(paginate: Paginate = Depends()):
    return paginate(select(User))
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

[`sqlalchemy.create_engine`]: https://docs.sqlalchemy.org/en/13/core/engines.html?highlight=create_engine#sqlalchemy.create_engine
[`Query.count`]: https://docs.sqlalchemy.org/en/13/orm/query.html#sqlalchemy.orm.query.Query.count
[pytest options]: https://docs.pytest.org/en/stable/reference.html#confval-usefixtures
[FastAPI]: https://fastapi.tiangolo.com/
[FastAPI dependency injection]: https://fastapi.tiangolo.com/tutorial/dependencies/
[FastAPI background tasks]: https://fastapi.tiangolo.com/tutorial/background-tasks/
[SQLAlchemy]: http://sqlalchemy.org/
[`asyncpg`]: https://magicstack.github.io/asyncpg/current/
[scalars]: (https://docs.sqlalchemy.org/en/14/core/connections.html?highlight=scalars#sqlalchemy.engine.Result.scalars),
