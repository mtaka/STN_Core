"""Data model for STN Core values, types and entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Union


# ---------------------------------------------------------------------------
# Empty — singleton for undefined references
# ---------------------------------------------------------------------------

class _EmptyType:
    """Sentinel returned when a reference cannot be resolved."""

    _instance: _EmptyType | None = None

    def __new__(cls) -> _EmptyType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "Empty"

    def __bool__(self) -> bool:
        return False


Empty = _EmptyType()


# ---------------------------------------------------------------------------
# PrimitiveKind / EnumKind
# ---------------------------------------------------------------------------

class PrimitiveKind(Enum):
    Text = auto()
    Number = auto()
    Date = auto()


@dataclass(slots=True)
class EnumKind:
    choices: list[str]


Kind = PrimitiveKind | EnumKind


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class VText:
    value: str


@dataclass(slots=True)
class VNumber:
    value: float


@dataclass(slots=True)
class VDate:
    value: str  # ISO-8601 string kept as-is


@dataclass(slots=True)
class VEnum:
    value: str
    choices: list[str]


@dataclass(slots=True)
class VList:
    items: list[Value]


@dataclass(slots=True)
class VDict:
    entries: dict[str, Value]


@dataclass(slots=True)
class VRef:
    name: str


@dataclass(slots=True)
class VEntity:
    entity: Entity


Value = Union[VText, VNumber, VDate, VEnum, VList, VDict, VRef, VEntity, _EmptyType]


# ---------------------------------------------------------------------------
# TypeDef
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TypeDef:
    name: str
    params: list[str]
    kinds: list[Kind] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Default all kinds to Text if not specified
        if not self.kinds:
            self.kinds = [PrimitiveKind.Text] * len(self.params)


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Entity:
    type_name: str
    fields: dict[str, Value]
    props: dict[str, Value] = field(default_factory=dict)
