"""Value types for STN Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass
class VText:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass
class VNumber:
    value: float

    def __str__(self) -> str:
        v = self.value
        if v == int(v):
            return str(int(v))
        return str(v)


@dataclass
class VDate:
    value: str  # ISO-8601

    def __str__(self) -> str:
        return self.value


@dataclass
class VBool:
    value: bool

    def __str__(self) -> str:
        return str(self.value).lower()


@dataclass
class VEnum:
    value: str
    choices: list[str]

    def __str__(self) -> str:
        return self.value


@dataclass
class VList:
    items: list["Value"]

    def __str__(self) -> str:
        return "[" + ", ".join(str(v) for v in self.items) + "]"


@dataclass
class VEntity:
    typedef: "TypeDef | None"   # TypeDef from typedef.py (forward ref)
    type_name: str | None
    fields: dict[str, "Value"] = field(default_factory=dict)
    props: dict[str, "Value"] = field(default_factory=dict)
    reserved: dict[str, "Value"] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"VEntity({self.type_name})"


class _Empty:
    """Singleton for undefined references."""

    _instance: "_Empty | None" = None

    def __new__(cls) -> "_Empty":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "Empty"

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return "Empty"


Empty = _Empty()

Value = Union[VText, VNumber, VDate, VBool, VEnum, VList, VEntity, _Empty]
