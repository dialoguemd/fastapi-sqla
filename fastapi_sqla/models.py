from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from pydantic import __version__ as pydantic_version

major, _, _ = [int(v) for v in pydantic_version.split(".")]
is_pydantic2 = major == 2
if is_pydantic2:
    GenericModel = BaseModel
else:
    from pydantic.generics import GenericModel  # type:ignore

T = TypeVar("T")


class Item(GenericModel, Generic[T]):
    """Item container."""

    data: T


class Collection(GenericModel, Generic[T]):
    """Collection container."""

    data: list[T]


class Meta(BaseModel):
    """Meta information on current page and collection"""

    offset: int = Field(..., description="Current page offset")
    total_items: int = Field(..., description="Total number of items in the collection")
    total_pages: int = Field(..., description="Total number of pages in the collection")
    page_number: int = Field(..., description="Current page number. Starts at 1.")


class Page(Collection[T], Generic[T]):
    """A page of the collection with info on current page and total items in meta."""

    meta: Meta
