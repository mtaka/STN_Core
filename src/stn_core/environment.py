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
    symbols: dict[str, Value] = field(default_factory=dict)

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

    # -- Symbols (@# / !#()) --------------------------------------------

    def set_symbol(self, name: str, value: Value) -> None:
        self.symbols[name] = value

    def get_symbol(self, name: str) -> Value:
        return self.symbols.get(name, Empty)

    # -- Backward compat aliases ----------------------------------------

    @property
    def publics(self) -> dict[str, Value]:
        return self.symbols

    def set_public(self, name: str, value: Value) -> None:
        self.set_symbol(name, value)

    def get_public(self, name: str) -> Value:
        return self.get_symbol(name)
