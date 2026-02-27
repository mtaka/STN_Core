"""Environment: definition tables and scope management."""

from __future__ import annotations

from dataclasses import dataclass, field

from .values import Value, Empty
from .typedef import TypeDef


@dataclass
class Environment:
    """Holds all definitions produced during evaluation."""

    typedefs: dict[str, TypeDef] = field(default_factory=dict)
    locals_: dict[str, Value] = field(default_factory=dict)
    publics: dict[str, Value] = field(default_factory=dict)

    # -- TypeDef --------------------------------------------------------

    def register_typedef(self, td: TypeDef) -> None:
        self.typedefs[td.name] = td

    def resolve_typedef(self, name: str) -> TypeDef | None:
        return self.typedefs.get(name)

    # -- Locals (@@) ----------------------------------------------------

    def set_local(self, name: str, value: Value) -> None:
        self.locals_[name] = value

    def get_local(self, name: str) -> Value:
        return self.locals_.get(name, Empty)

    # -- Publics (@#) ---------------------------------------------------

    def set_public(self, name: str, value: Value) -> None:
        self.publics[name] = value

    def get_public(self, name: str) -> Value:
        return self.publics.get(name, Empty)
