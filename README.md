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

## Pytest fixtures
This library provides a set of utility fixtures, through its PyTest plugin, which is automatically installed with the library.

By default, no records are actually written in database when running tests.
There is no way to deactivate that behaviour at the moment.

### `sqla_modules`

This fixture must be defined to load db tables information in sqla entities adequately.
It should just import all modules containing sqla entity classes.

Example:

```python
# tests/conftest.py
from pytest import fixture


@fixture
def sqla_modules():
    from er import sqla  # noqa
```

### `db_url`

Db url used.

When `CIRCLECI` key is set in environment variables, it uses `postgres` as host name:

```
postgresql://postgres@posgres/postgres
```

Else, host used is `localhost`:

```
postgresql://postgres@localhost/postgres
```

Of course, you can override it, example:

```python
from pytest import fixture


@fixture(scope="session")
def db_url():
    return "postgresql://postgres@localhost/test_database"
```


### `session`

Sqla session to create db fixture. No record will actually be written in the database.
Changes in one session need to be committed to be _seen_ from other sessions.

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
