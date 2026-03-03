"""SObject — intermediate representation from the Reader layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class SObject:
    """S-object: intermediate representation that can act as dict or list."""

    entries: list["SEntry"]

    def get(self, key: "str | int") -> "object":
        """Access by name or 1-origin index. Returns Empty for missing keys."""
        from .values import Empty

        if isinstance(key, int):
            if key < 1:
                return Empty
            idx = key - 1
            if idx < len(self.entries):
                return self.entries[idx].value
            return Empty

        for entry in self.entries:
            if entry.key == key:
                return entry.value
        return Empty


@dataclass
class SEntry:
    key: str | None  # None = unnamed (array-like element)
    value: "SValue"


SValue = Union[str, SObject, "list[SObject]"]
