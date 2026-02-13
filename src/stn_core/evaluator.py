"""Two-pass evaluator: definitions → evaluation.

Usage::

    from stn import parse
    from stn_core import evaluate

    doc = evaluate(parse("@%Rect (x y w h) ; @#R1 %Rect(10 20 100 50)").ast)
"""

from __future__ import annotations

from stn.nodes import Node

from .chunk_utils import atom_to_value, normalize_implicit_dict
from .document import Document
from .environment import Environment
from .model import (
    Empty,
    Entity,
    Value,
    VDict,
    VEntity,
    VList,
    VNumber,
    VRef,
    VText,
    TypeDef,
    _EmptyType,
)
from .units import (
    LeaderType,
    Statement,
    Unit,
    parse_chunks_to_statements,
)


def evaluate(root: Node) -> Document:
    """Evaluate a lexer AST and return a Document."""
    env = Environment()
    stmts = parse_chunks_to_statements(root)

    # Pass 1 — register definitions
    for stmt in stmts:
        if stmt.is_define:
            _register_definition(env, stmt)

    # Pass 2 — evaluate all statements
    results: list[Value] = []
    for stmt in stmts:
        if stmt.is_define:
            _eval_definition(env, stmt, results)
        else:
            val = _eval_statement(env, stmt)
            if val is not None:
                results.append(val)

    return Document(environment=env, results=results)


# -----------------------------------------------------------------------
# Pass 1 helpers
# -----------------------------------------------------------------------

def _register_definition(env: Environment, stmt: Statement) -> None:
    """Register TypeDef / GlobalVarDef / LocalVarDef from a define statement."""
    if not stmt.units:
        return

    first = stmt.units[0]

    if first.leader.kind == LeaderType.TypeCall:
        _register_typedef(env, first)
    # GlobalVarDef and LocalVarDef — actual values assigned in pass 2


def _register_typedef(env: Environment, unit: Unit) -> None:
    """Register a TypeDef from ``@%Name (...params...)``."""
    from .model import EnumKind, Kind

    name = unit.operand
    if name is None:
        return

    child = unit.child
    if child is None or not child.chunks:
        env.register_typedef(TypeDef(name=name, params=[]))
        return

    # Flatten all chunks from the child (handles ':' chunk splitting)
    all_atoms: list[str] = []
    for chunk in child.chunks:
        all_atoms.extend(chunk)

    # Check if it's a key-based definition (has ':' sigils)
    if any(a == ":" for a in all_atoms):
        params, kinds = _parse_keyed_params_with_kinds(all_atoms, child.children)
        env.register_typedef(TypeDef(name=name, params=params, kinds=kinds))
    else:
        # Positional: (x y w h) — all default to Text
        params = list(all_atoms)
        env.register_typedef(TypeDef(name=name, params=params))


def _parse_keyed_params_with_kinds(
    atoms: list[str],
    children: list[Node],
) -> tuple[list[str], list[Kind]]:
    """Extract param names and kinds from keyed typedef.

    Examples::

        (:name :age % :sex %s(F M))
        → params=["name", "age", "sex"],
          kinds=[Text, Number, EnumKind(["F", "M"])]

    Convention:
        - ``%``  after a param → Number
        - ``%s(choices...)`` after a param → Enum
        - no annotation → Text
    """
    from .model import EnumKind, Kind, PrimitiveKind

    params: list[str] = []
    kinds: list[Kind] = []
    child_idx = 0
    i = 0

    while i < len(atoms):
        if atoms[i] == ":" and i + 1 < len(atoms):
            param_name = atoms[i + 1]
            params.append(param_name)
            i += 2

            # Look for kind annotation before next ':' or end
            kind: Kind = PrimitiveKind.Text
            while i < len(atoms) and atoms[i] != ":":
                if atoms[i] == "%":
                    # Check if next is a type tag like 's' (enum)
                    if i + 1 < len(atoms) and atoms[i + 1] not in (":", "%") and atoms[i + 1] != ":":
                        tag = atoms[i + 1]
                        if tag == "s" or tag == "S":
                            # Enum — consume child for choices
                            choices: list[str] = []
                            if child_idx < len(children) and children[child_idx].chunks:
                                choices = list(children[child_idx].chunks[0])
                                child_idx += 1
                            kind = EnumKind(choices=choices)
                        i += 2
                    else:
                        # Bare '%' → Number
                        kind = PrimitiveKind.Number
                        i += 1
                else:
                    i += 1
            kinds.append(kind)
        else:
            i += 1

    return params, kinds


# -----------------------------------------------------------------------
# Pass 2 helpers
# -----------------------------------------------------------------------

def _eval_definition(env: Environment, stmt: Statement, results: list[Value]) -> None:
    """Evaluate a definition statement in pass 2."""
    if not stmt.units:
        return

    first = stmt.units[0]

    if first.leader.kind == LeaderType.TypeCall:
        # TypeDef — already registered in pass 1, nothing more to do
        return

    if first.leader.kind == LeaderType.GlobalRef:
        _eval_global_def(env, stmt)
    elif first.leader.kind == LeaderType.LocalRef:
        _eval_local_def(env, stmt)


def _eval_global_def(env: Environment, stmt: Statement) -> None:
    """Evaluate ``@#Name ...`` — GlobalVarDef."""
    first = stmt.units[0]
    var_name = first.operand
    if var_name is None:
        return

    if len(stmt.units) > 1:
        # Has more units (e.g. @#R1 %Rect(...)!setter(...))
        value = _eval_unit_chain(env, stmt.units, start=1)
    elif first.child is not None:
        # Has a direct child (e.g. @#A (99))
        value = _child_to_value(env, first.child)
    else:
        value = Empty

    env.set_global(var_name, value)


def _eval_local_def(env: Environment, stmt: Statement) -> None:
    """Evaluate ``@name (...)`` — LocalVarDef."""
    first = stmt.units[0]
    var_name = first.operand
    if var_name is None:
        return

    # If has a child node, extract value from it
    if first.child is not None:
        value = _child_to_value(env, first.child)
    elif len(stmt.units) > 1:
        # Value comes from remaining units (e.g. @name %Type(...))
        value = _eval_unit_chain(env, stmt.units, start=1)
    else:
        value = Empty

    env.set_local(var_name, value)


def _eval_statement(env: Environment, stmt: Statement) -> Value | None:
    """Evaluate a non-definition statement."""
    if not stmt.units:
        return None
    return _eval_unit_chain(env, stmt.units, start=0)


def _eval_unit_chain(env: Environment, units: list[Unit], start: int) -> Value:
    """Walk a chain of units and produce a Value.

    The first unit establishes a base value, subsequent units apply
    getter / setter / type-call operations.
    """
    if start >= len(units):
        return Empty

    first = units[start]
    base = _eval_single_unit(env, first)

    for unit in units[start + 1:]:
        base = _apply_unit(env, base, unit)

    return base


def _eval_single_unit(env: Environment, unit: Unit) -> Value:
    """Evaluate a single unit to produce a base value."""
    kind = unit.leader.kind

    if kind == LeaderType.GlobalRef:
        name = unit.operand
        if name is None:
            return Empty
        return env.get_global(name)

    if kind == LeaderType.LocalRef:
        name = unit.operand
        if name is None:
            return Empty
        return env.get_local(name)

    if kind == LeaderType.TypeCall:
        return _eval_type_call(env, unit)

    if kind == LeaderType.Key:
        return VText(unit.operand or "")

    return Empty


def _eval_type_call(env: Environment, unit: Unit) -> Value:
    """Evaluate ``%Type(args...)`` to produce a VEntity."""
    type_name = unit.operand
    if type_name is None:
        return Empty

    if unit.child is None or not unit.child.chunks:
        entity = env.create_entity(type_name, [])
        return VEntity(entity)

    # Flatten all chunks
    all_atoms: list[str] = []
    for chunk in unit.child.chunks:
        all_atoms.extend(chunk)

    # Check if keyed arguments (:name val :age val ...)
    if any(a == ":" for a in all_atoms):
        kwargs = _extract_keyed_args(all_atoms)
        entity = env.create_entity_keyed(type_name, kwargs)
    else:
        # Positional arguments
        entity = env.create_entity(type_name, all_atoms)

    return VEntity(entity)


def _extract_keyed_args(atoms: list[str]) -> dict[str, str]:
    """Extract key-value pairs from ``:key val`` atom list."""
    result: dict[str, str] = {}
    i = 0
    while i < len(atoms):
        if atoms[i] == ":" and i + 1 < len(atoms):
            key = atoms[i + 1]
            i += 2
            # Collect value atoms until next ':' or end
            values: list[str] = []
            while i < len(atoms) and atoms[i] != ":":
                values.append(atoms[i])
                i += 1
            if values:
                result[key] = values[0] if len(values) == 1 else " ".join(values)
            else:
                result[key] = ""
        else:
            i += 1
    return result


def _apply_unit(env: Environment, base: Value, unit: Unit) -> Value:
    """Apply a unit (getter/setter/etc.) to a base value."""
    kind = unit.leader.kind

    if kind == LeaderType.Getter:
        return _apply_getter(base, unit.operand)

    if kind == LeaderType.Setter:
        return _apply_setter(env, base, unit)

    if kind == LeaderType.TypeCall:
        return _eval_type_call(env, unit)

    return base


# -----------------------------------------------------------------------
# getter
# -----------------------------------------------------------------------

def _apply_getter(base: Value, field_name: str | None) -> Value:
    """Look up a field on an entity: fields → props → Empty."""
    if field_name is None:
        return Empty

    if isinstance(base, VEntity):
        entity = base.entity
        if field_name in entity.fields:
            return entity.fields[field_name]
        if field_name in entity.props:
            return entity.props[field_name]
        return Empty

    if isinstance(base, VDict):
        return base.entries.get(field_name, Empty)

    return Empty


# -----------------------------------------------------------------------
# setter
# -----------------------------------------------------------------------

def _apply_setter(env: Environment, base: Value, unit: Unit) -> Value:
    """Apply a setter to a base value.

    - ``!field(value)`` — set single field/prop
    - ``!+(...)`` — batch set from implicit dict
    """
    if not isinstance(base, VEntity):
        return base

    entity = base.entity

    if unit.operand == "+":
        _apply_batch_setter(env, entity, unit)
        return base

    field_name = unit.operand
    if field_name is None:
        return base

    value = _child_to_value(env, unit.child)
    _set_field_or_prop(entity, field_name, value)
    return base


def _apply_batch_setter(env: Environment, entity: Entity, unit: Unit) -> None:
    """Apply ``!+(...)`` batch property setting.

    Supports both positional ``(key1 val1 key2 val2)`` and
    implicit-dict ``(:key1 val1 :key2 val2)`` formats.
    """
    if unit.child is None or not unit.child.chunks:
        return

    chunks = unit.child.chunks

    # Check if any chunk starts with ':' → implicit dict format
    has_key_sigils = any(
        chunk and chunk[0] == ":" for chunk in chunks
    )

    if has_key_sigils:
        # Flatten all chunks and use normalize_implicit_dict
        all_atoms: list[str] = []
        for chunk in chunks:
            all_atoms.extend(chunk)
        vdict = normalize_implicit_dict(all_atoms)
        for key, value in vdict.entries.items():
            _set_field_or_prop(entity, key, value)
    else:
        # Positional: (key1 val1 key2 val2 ...)
        atoms = chunks[0]
        i = 0
        while i + 1 < len(atoms):
            key = atoms[i]
            value = atom_to_value(atoms[i + 1])
            _set_field_or_prop(entity, key, value)
            i += 2


def _set_field_or_prop(entity: Entity, key: str, value: Value) -> None:
    """Set a value using setter order: fields → props (existing) → props (new)."""
    if key in entity.fields:
        entity.fields[key] = value
    elif key in entity.props:
        entity.props[key] = value
    else:
        entity.props[key] = value


# -----------------------------------------------------------------------
# Child → Value extraction
# -----------------------------------------------------------------------

def _child_to_value(env: Environment, child: Node | None) -> Value:
    """Extract a Value from a child node."""
    if child is None:
        return Empty
    if not child.chunks:
        return Empty

    chunks = child.chunks

    # Multiple chunks with ':' keys → implicit dict
    if len(chunks) > 1 and any(c and c[0] == ":" for c in chunks):
        all_atoms: list[str] = []
        for chunk in chunks:
            all_atoms.extend(chunk)
        return normalize_implicit_dict(all_atoms)

    first_chunk = chunks[0]
    if not first_chunk:
        return Empty

    # Single chunk starting with ':' → implicit dict
    if first_chunk[0] == ":":
        all_atoms = []
        for chunk in chunks:
            all_atoms.extend(chunk)
        return normalize_implicit_dict(all_atoms)

    # Reference: #name or @name
    if len(first_chunk) >= 2 and first_chunk[0] in ("#", "@"):
        sigil = first_chunk[0]
        ref_name = first_chunk[1]
        if sigil == "#":
            val = env.get_global(ref_name)
        else:
            val = env.get_local(ref_name)

        if not isinstance(val, _EmptyType):
            return val
        # Unresolved → VRef
        return VRef(ref_name)

    # Single value
    if len(first_chunk) == 1:
        return atom_to_value(first_chunk[0])

    # Multiple values → VList
    return VList([atom_to_value(a) for a in first_chunk])
