from pydantic import __version__ as pydantic_version

major, _, _ = (int(v) for v in pydantic_version.split("."))
is_pydantic2 = major == 2


def test_module_importable():
    import fastapi_sqla.v1  # noqa


def test_classes_importable():
    from fastapi_sqla.v1 import Collection, Item, Meta, Page  # noqa


def test_item_mro_uses_pydantic_v1_generic_model():
    from fastapi_sqla.v1 import Item

    if is_pydantic2:
        from pydantic.v1.generics import GenericModel

        assert issubclass(Item, GenericModel)
    else:
        from pydantic.generics import GenericModel

        assert issubclass(Item, GenericModel)


def test_collection_mro_uses_pydantic_v1_generic_model():
    from fastapi_sqla.v1 import Collection

    if is_pydantic2:
        from pydantic.v1.generics import GenericModel

        assert issubclass(Collection, GenericModel)
    else:
        from pydantic.generics import GenericModel

        assert issubclass(Collection, GenericModel)


def test_meta_is_subclass_of_pydantic_v1_base_model():
    from fastapi_sqla.v1 import Meta

    if is_pydantic2:
        from pydantic.v1 import BaseModel

        assert issubclass(Meta, BaseModel)
    else:
        from pydantic import BaseModel

        assert issubclass(Meta, BaseModel)


def test_page_mro_uses_pydantic_v1_generic_model():
    from fastapi_sqla.v1 import Page

    if is_pydantic2:
        from pydantic.v1.generics import GenericModel

        assert issubclass(Page, GenericModel)
    else:
        from pydantic.generics import GenericModel

        assert issubclass(Page, GenericModel)


def test_item_instantiation():
    from fastapi_sqla.v1 import Item

    item = Item[str](data="hello")
    assert item.data == "hello"


def test_collection_instantiation():
    from fastapi_sqla.v1 import Collection

    collection = Collection[int](data=[1, 2, 3])
    assert collection.data == [1, 2, 3]


def test_meta_instantiation():
    from fastapi_sqla.v1 import Meta

    meta = Meta(offset=0, total_items=10, total_pages=2, page_number=1)
    assert meta.offset == 0
    assert meta.total_items == 10
    assert meta.total_pages == 2
    assert meta.page_number == 1


def test_page_instantiation():
    from fastapi_sqla.v1 import Meta, Page

    meta = Meta(offset=0, total_items=1, total_pages=1, page_number=1)
    page = Page[str](data=["a"], meta=meta)
    assert page.data == ["a"]
    assert page.meta == meta
    assert page.meta.total_items == 1
