"""Environment: definition tables and scope management."""

from __future__ import annotations

from dataclasses import dataclass, field

from .values import Value, Empty
from .typedef import TypeDef
from .funcdef import FuncDef


@dataclass
class Environment:
    """Holds all definitions produced during evaluation."""

    typedefs: dict[str, TypeDef] = field(default_factory=dict)
    locals_: dict[str, Value] = field(default_factory=dict)
    symbols: dict[str, Value] = field(default_factory=dict)
    functions: dict[str, FuncDef] = field(default_factory=dict)
    _scope_stack: list = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        from .system_funcs import get_system_functions
        for fd in get_system_functions():
            self.functions[fd.name] = fd

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

    # -- Functions (@=) -------------------------------------------------

    def register_function(self, fd: FuncDef) -> None:
        self.functions[fd.name] = fd

    def get_function(self, name: str) -> FuncDef | None:
        return self.functions.get(name)

    # -- Scope stack ($var) ---------------------------------------------

    def push_scope(self, scope: "dict[str, Value]") -> None:
        self._scope_stack.append(dict(scope))

    def pop_scope(self) -> None:
        if self._scope_stack:
            self._scope_stack.pop()

    def get_scope_var(self, name: str) -> Value:
        for scope in reversed(self._scope_stack):
            if name in scope:
                return scope[name]
        return Empty

    def set_scope_var(self, name: str, val: Value) -> None:
        if self._scope_stack:
            self._scope_stack[-1][name] = val

    # -- Backward compat aliases ----------------------------------------

    @property
    def publics(self) -> dict[str, Value]:
        return self.symbols

    def set_public(self, name: str, value: Value) -> None:
        self.set_symbol(name, value)

    def get_public(self, name: str) -> Value:
        return self.get_symbol(name)
