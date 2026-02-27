"""SObject — intermediate representation from the Reader layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class SObject:
    """S-object: intermediate representation that can act as dict or list."""

    entries: list["SEntry"]


@dataclass
class SEntry:
    key: str | None  # None = unnamed (array-like element)
    value: "SValue"


SValue = Union[str, SObject, "list[SObject]"]
