# fastapi-sqla

SqlAlchemy integration for FastAPI®


## Configuration

* Configure environ variables:
  The keys of interest in `os.environ` are prefixed with `sqlalchemy_`.
  Each matching key (after the prefix is stripped) is treated as though it were the
  corresponding keyword argument to [`sqlalchemy.create_engine`]
  (https://docs.sqlalchemy.org/en/13/core/engines.html?highlight=create_engine#sqlalchemy.create_engine)  # noqa
  call.

  The only required key is `sqlalchemy_url`, which provides the database URL.

* Setup the app:
  ```python
  import fastapi_sqla
  from fastapi import FastAPI

  app = FastAPI()
  fastapi_sqla.setup(app)
  ```
* Adding a new entity class:
  ```python
  from fastapi_sqla import Base

  class Entity(Base):
      __tablename__ = "table-name-in-db"
  ```
