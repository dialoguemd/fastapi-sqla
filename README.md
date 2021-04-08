# fastapi-sqla

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-brightgreen.svg)](https://conventionalcommits.org)
[![CircleCI](https://circleci.com/gh/dialoguemd/fastapi-sqla.svg?style=svg&circle-token=998482f269270ee521aa54f2accbee2e22943743)](https://circleci.com/gh/dialoguemd/fastapi-sqla)
[![codecov](https://codecov.io/gh/dialoguemd/fastapi-sqla/branch/master/graph/badge.svg?token=BQHLryClIn)](https://codecov.io/gh/dialoguemd/fastapi-sqla)

A highly opinionated [SQLAlchemy] extension for [FastAPI]:

* Setup using environment variables to connect on DB;
* `fastapi_sqla.Base` a declarative base class to reflect DB tables at startup;
* `fastapi_sqla.with_session` a dependency to get an sqla session;
* Automated commit/rollback of sqla session at the end of request before returning
  response;
* Pagination utilities;
* Pytest fixtures to easy writing test;

## Configuration

### Environment variables:

The keys of interest in `os.environ` are prefixed with `sqlalchemy_`.
Each matching key (after the prefix is stripped) is treated as though it were the
corresponding keyword argument to [`sqlalchemy.create_engine`]
call.

The only required key is `sqlalchemy_url`, which provides the database URL.

### Setup the app:

```python
import fastapi_sqla
from fastapi import FastAPI

app = FastAPI()
fastapi_sqla.setup(app)
```

## SQLAlchemy

### Adding a new entity class:

```python
from fastapi_sqla import Base


class Entity(Base):
    __tablename__ = "table-name-in-db"
```

### Getting an sqla session

#### Using dependency injection

Use [FastAPI dependency injection] to get a session as a parameter of a path operation
function.
SQLAlchemy session is committed before response is returned or rollbacked if any
exception occurred:

```python
from fastapi import APIRouter, Depends
from fastapi_sqla import Session

router = APIRouter()


@router.get("/example")
def example(session: Session = Depends()):
    return session.execute("SELECT now()").scalar()
```

#### Using a context manager

When needing a session outside of a path operation, like when using
[FastAPI background tasks], use `fastapi_sqla.open_session` context manager.
SQLAlchemy session is committed when exiting context or rollbacked if any exception
occurred:

```python
from fastapi import APIRouter, BackgroundTasks
from fastapi_sqla import open_session

router = APIRouter()


@router.get("/example")
def example(bg: BackgroundTasks):
    bg.add_task(run_bg)


def run_bg():
    with open_session() as session:
        session.execute("SELECT now()").scalar()
```

### Pagination

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


@router.get("/users", response_model=Page[UserModel])
def all_users(paginate: Paginate = Depends()):
    query = select(User)
    return paginate(query)
```

By default:

* It returns pages of 10 items, up to 100 items;
* Total number of items in the collection is queried using [`Query.count`]

#### Customize pagination

You can customize:
- Minimum and maximum number of items per pages;
- How the total number of items in the collection is queried;

To customize pagination, create a dependency using `fastapi_sqla.Pagination`

```python
from fastapi import APIRouter, Depends
from fastapi_sqla import Base, Page, Pagination, Session
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.sql import Select

router = APIRouter()


class User(Base):
    __tablename__ = "user"


class UserModel(BaseModel):
    id: int
    name: str


def query_count(session: Session, query: Select) -> int:
    return session.execute(select(func.count()).select_from(User)).scalar()


Paginate = Pagination(
    min_page_size=5,
    max_page_size=500,
    query_count=query_count,
)


@router.get("/users", response_model=Page[UserModel])
def all_users(paginate: Paginate = Depends()):
    query = select(User)
    return paginate(query)
```

## Pytest fixtures

This library provides a set of utility fixtures, through its PyTest plugin, which is
automatically installed with the library.

By default, no records are actually written to the database when running tests.
There currently is no way to change this behaviour.

### `sqla_modules`

You must define this fixture, in order for the plugin to reflect table metadata in your
SQLAlchemy entities. It should just import all of the application's modules which contain
SQLAlchemy models.

Example:

```python
# tests/conftest.py
from pytest import fixture


@fixture
def sqla_modules():
    from er import sqla  # noqa
```

### `db_url`

The DB url to use.

When `CI` key is set in environment variables, it defaults to using `postgres` as the
host name:

```
postgresql://postgres@posgres/postgres
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


### `session`

Sqla session to create db fixture:
* All changes done at test setup or during the test are rollbacked at test tear down;
* No record will actually be written in the database;
* Changes in one session need to be committed to be available from other sessions;

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
```

### `db_migration`

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

### `alembic_ini_path`

It returns the path of  `alembic.ini` configuration file. By default, it returns
`./alembic.ini`.


[`sqlalchemy.create_engine`]: https://docs.sqlalchemy.org/en/13/core/engines.html?highlight=create_engine#sqlalchemy.create_engine
[`Query.count`]: https://docs.sqlalchemy.org/en/13/orm/query.html#sqlalchemy.orm.query.Query.count
[pytest options]: https://docs.pytest.org/en/stable/reference.html#confval-usefixtures
[FastAPI]: https://fastapi.tiangolo.com/
[FastAPI dependency injection]: https://fastapi.tiangolo.com/tutorial/dependencies/
[FastAPI background tasks]: https://fastapi.tiangolo.com/tutorial/background-tasks/
[SQLAlchemy]: http://sqlalchemy.org/
