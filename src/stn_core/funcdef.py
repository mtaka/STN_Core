"""FuncDef and ParamDef for STN Core functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class ParamDef:
    name: str                    # variable name without $ prefix
    default: Any = None          # Value or None (= required)


@dataclass
class FuncDef:
    name: str
    params: list[ParamDef] = field(default_factory=list)
    body: Any = None             # Node (user-defined body) or None
    impl: Callable | None = None  # Python callable for system functions
