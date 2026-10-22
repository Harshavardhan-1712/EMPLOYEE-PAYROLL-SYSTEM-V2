from __future__ import annotations

import re
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel

T = TypeVar("T")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(v: str) -> str:
    v = v.strip()
    if _CTRL.search(v):
        raise ValueError("contains control characters")
    return v


CleanStr = Annotated[str, AfterValidator(_clean)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
