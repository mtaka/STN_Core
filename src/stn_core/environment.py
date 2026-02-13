"""Definition tables and scope management."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import (
    Empty,
    EnumKind,
    Entity,
    Kind,
    PrimitiveKind,
    TypeDef,
    Value,
    VDate,
    VEnum,
    VNumber,
    VText,
    _EmptyType,
)
from .chunk_utils import atom_to_value


@dataclass
class Environment:
    """Holds all definitions produced during evaluation."""

    typedefs: dict[str, TypeDef] = field(default_factory=dict)
    globals_: dict[str, Value] = field(default_factory=dict)
    locals_: dict[str, Value] = field(default_factory=dict)

    # -- TypeDef --------------------------------------------------------

    def register_typedef(self, td: TypeDef) -> None:
        self.typedefs[td.name] = td

    def resolve_typedef(self, name: str) -> TypeDef | None:
        return self.typedefs.get(name)

    # -- Variables ------------------------------------------------------

    def set_global(self, name: str, value: Value) -> None:
        self.globals_[name] = value

    def get_global(self, name: str) -> Value:
        return self.globals_.get(name, Empty)

    def set_local(self, name: str, value: Value) -> None:
        self.locals_[name] = value

    def get_local(self, name: str) -> Value:
        return self.locals_.get(name, Empty)

    # -- Entity creation ------------------------------------------------

    def create_entity(self, type_name: str, args: list[str]) -> Entity:
        """Instantiate an Entity from a TypeDef name and positional args."""
        td = self.resolve_typedef(type_name)
        if td is None:
            fields = {f"_{i}": atom_to_value(a) for i, a in enumerate(args)}
            return Entity(type_name=type_name, fields=fields)

        fields: dict[str, Value] = {}
        for i, param in enumerate(td.params):
            if i < len(args):
                kind = td.kinds[i] if i < len(td.kinds) else PrimitiveKind.Text
                fields[param] = _coerce(args[i], kind)
            else:
                fields[param] = Empty
        return Entity(type_name=type_name, fields=fields)

    def create_entity_keyed(self, type_name: str, kwargs: dict[str, str]) -> Entity:
        """Instantiate an Entity from a TypeDef name and keyword args."""
        td = self.resolve_typedef(type_name)
        if td is None:
            fields = {k: atom_to_value(v) for k, v in kwargs.items()}
            return Entity(type_name=type_name, fields=fields)

        fields: dict[str, Value] = {}
        for i, param in enumerate(td.params):
            if param in kwargs:
                kind = td.kinds[i] if i < len(td.kinds) else PrimitiveKind.Text
                fields[param] = _coerce(kwargs[param], kind)
            else:
                fields[param] = Empty
        return Entity(type_name=type_name, fields=fields)


def _coerce(raw: str, kind: Kind) -> Value:
    """Convert a raw string to a Value according to the expected kind."""
    if kind == PrimitiveKind.Number:
        try:
            return VNumber(float(raw))
        except ValueError:
            return VText(raw)
    if kind == PrimitiveKind.Date:
        # Strip literal brackets if present
        text = raw[1:-1] if raw.startswith("[") and raw.endswith("]") else raw
        return VDate(text)
    if isinstance(kind, EnumKind):
        # Strip literal brackets if present
        text = raw[1:-1] if raw.startswith("[") and raw.endswith("]") else raw
        return VEnum(text, kind.choices)
    # Text / unknown → atom_to_value
    return atom_to_value(raw)
