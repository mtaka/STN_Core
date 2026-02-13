"""Document — the final output of STN Core evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .environment import Environment
from .model import TypeDef, Value


@dataclass
class Document:
    """Holds the fully evaluated result of an STN source."""

    environment: Environment = field(default_factory=Environment)
    results: list[Value] = field(default_factory=list)

    # -- Convenience accessors ------------------------------------------

    @property
    def globals_(self) -> dict[str, Value]:
        return self.environment.globals_

    @property
    def locals_(self) -> dict[str, Value]:
        return self.environment.locals_

    @property
    def typedefs(self) -> dict[str, TypeDef]:
        return self.environment.typedefs
