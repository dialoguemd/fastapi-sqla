from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from pydantic import __version__ as pydantic_version
from sqlalchemy.ext.declarative import DeferredReflection

try:
    from sqlalchemy.orm import DeclarativeBase
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

    DeclarativeBase = declarative_base()  # type: ignore

major, _, _ = [int(v) for v in pydantic_version.split(".")]
is_pydantic2 = major == 2
if is_pydantic2:
    GenericModel = BaseModel
else:
    from pydantic.generics import GenericModel  # type:ignore


class Base(DeclarativeBase, DeferredReflection):
    __abstract__ = True


ItemT = TypeVar("ItemT")


class Item(GenericModel, Generic[ItemT]):
    """Item container."""

    data: ItemT


class Collection(GenericModel, Generic[ItemT]):
    """Collection container."""

    data: list[ItemT]


class Meta(BaseModel):
    """Meta information on current page and collection"""

    offset: int = Field(..., description="Current page offset")
    total_items: int = Field(..., description="Total number of items in the collection")
    total_pages: int = Field(..., description="Total number of pages in the collection")
    page_number: int = Field(..., description="Current page number. Starts at 1.")


class Page(Collection[ItemT], Generic[ItemT]):
    """A page of the collection with info on current page and total items in meta."""

    meta: Meta
