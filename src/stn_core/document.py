"""Document — the final output of STN Core evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .environment import Environment
from .values import Value
from .typedef import TypeDef


@dataclass
class Document:
    """Holds the fully evaluated result of an STN source."""

    environment: Environment = field(default_factory=Environment)
    results: list[Value] = field(default_factory=list)

    @property
    def locals_(self) -> dict[str, Value]:
        return self.environment.locals_

    @property
    def publics(self) -> dict[str, Value]:
        return self.environment.publics

    @property
    def typedefs(self) -> dict[str, TypeDef]:
        return self.environment.typedefs
