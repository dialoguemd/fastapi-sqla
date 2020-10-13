# fastapi-sqla

SqlAlchemy integration for FastAPI®

## Configuration

### Environment variables:
  The keys of interest in `os.environ` are prefixed with `sqlalchemy_`.
  Each matching key (after the prefix is stripped) is treated as though it were the
  corresponding keyword argument to [`sqlalchemy.create_engine`](https://docs.sqlalchemy.org/en/13/core/engines.html?highlight=create_engine#sqlalchemy.create_engine)
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

### Getting an sqla orm session

```python
from fastapi import APIRouter, Depends
from fastapi_sqla import Session, with_session

router = APIRouter()


@router.get("/example")
def example(session: Session = Depends(with_session)):
    return session.execute("SELECT now()").scalar()
```

### Pagination

```python
from typing import Callable

from fastapi import APIRouter, Depends
from fastapi_sqla import Base, Paginated, Session, with_pagination, with_session
from pydantic import BaseModel
from sqlalchemy.orm import Query

router = APIRouter()


class UserEntity(Base):
    __tablename__ = "user"


class User(BaseModel):
    id: int
    name: str


@router.get("/users", response_model=Paginated[User])
def all_users(
    session: Session = Depends(with_session),
    paginated_result: Callable[[Query], Paginated[User]] = Depends(with_pagination),
):
    query = session.query(UserEntity)
    return paginated_result(query)
```

By default:
* It returns pages of 10 items, up to 100 items;
* Total number of items in the collection is queried using
  [`Query.count`](https://docs.sqlalchemy.org/en/13/orm/query.html#sqlalchemy.orm.query.Query.count)

### Custom pagination

You can customize:
- Minimum and maximunm number of items per pages;
- How the total number of items in the collection is queried;

To customize pagination, create a dependency using `fastapi_sqla.new_pagination`

```python
from fastapi import APIRouter, Depends
from fastapi_sqla import Base, Paginated, Session, new_pagination, with_session
from pydantic import BaseModel
from sqlalchemy import func

router = APIRouter()


class UserEntity(Base):
    __tablename__ = "user"


class User(BaseModel):
    id: int
    name: str


def query_count(session, query):
    return query.statement.with_only_columns([func.count()]).scalar()


with_custom_pagination = new_pagination(
    min_page_size=5,
    max_page_size=500,
    query_count=query_count,
)


@router.get("/users", response_model=Paginated[User])
def all_users(
    session: Session = Depends(with_session),
    paginated_result=Depends(with_custom_pagination),
):
    query = session.query(UserEntity)
    return paginated_result(query)
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
* All changes done at test setiup or during the test are rollbacked at test tear down;
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
