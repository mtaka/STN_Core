"""Getter resolution for STN Core."""

from __future__ import annotations

from .values import Value, VText, VEntity, VList, _Empty, Empty


def apply_getter(value: Value, accessor: str) -> Value:
    """Resolve a single getter accessor on a value.

    - VEntity: fields first, then props, then reserved, then 1-based index
    - VList: 1-based integer index
    - Empty / other: returns Empty
    """
    if isinstance(value, _Empty):
        return Empty

    if isinstance(value, VEntity):
        if accessor in value.fields:
            return value.fields[accessor]
        if accessor in value.props:
            return value.props[accessor]
        if accessor in value.reserved:
            return value.reserved[accessor]
        # Numeric index (1-based)
        try:
            idx = int(accessor) - 1
            field_values = list(value.fields.values())
            if 0 <= idx < len(field_values):
                return field_values[idx]
        except ValueError:
            pass
        return Empty

    if isinstance(value, VList):
        try:
            idx = int(accessor) - 1
            if 0 <= idx < len(value.items):
                return value.items[idx]
        except ValueError:
            pass
        return Empty

    return Empty


# ---------------------------------------------------------------------------
# Symbol id helpers
# ---------------------------------------------------------------------------

def _entity_has_id(entity: VEntity, sym_name: str) -> bool:
    """Return True if entity has __(:id sym_name) set."""
    reserved_obj = entity.reserved.get("__")
    if not isinstance(reserved_obj, VEntity):
        return False
    id_val = reserved_obj.fields.get("id")
    return isinstance(id_val, VText) and id_val.value == sym_name


def apply_symbol_getter(value: Value, sym_name: str) -> Value:
    """.(#name) — find element in collection by __(:id) == sym_name."""
    if isinstance(value, _Empty):
        return Empty

    if isinstance(value, VList):
        for item in value.items:
            if isinstance(item, VEntity) and _entity_has_id(item, sym_name):
                return item
        return Empty

    if isinstance(value, VEntity):
        # Search unnamed sub-entities
        for v in value.fields.values():
            if isinstance(v, VEntity) and _entity_has_id(v, sym_name):
                return v
        return Empty

    return Empty


def apply_node_getter(value: Value, node: object) -> Value:
    """.(expr) getter where expr is not a #symbol.

    Handles .(name) and .(N) — falls back to apply_getter.
    Multi-access .(name age) is not yet implemented (returns Empty).
    """
    from stn.tokenizer import Token, TokenType  # type: ignore
    from stn.nodes import Node  # type: ignore

    if not isinstance(node, Node):
        return Empty

    items = node.items
    if not items:
        return Empty

    # Single token: .(name) or .(N)
    if len(items) == 1 and isinstance(items[0], Token):
        tok = items[0]
        if tok.type in (TokenType.ATOM, TokenType.NUMBER):
            return apply_getter(value, tok.value)

    # Multi-access: not yet implemented
    return Empty


# ---------------------------------------------------------------------------
# Query locator
# ---------------------------------------------------------------------------

def apply_query_locator(value: Value, condition_node: object, env: object) -> Value:
    """?(conditions) — filter a VList/VEntity by field conditions.

    Conditions are parsed as :key value pairs.
    - VList: filter elements; return single match or VList of matches
    - VEntity: filter unnamed sub-entities
    - No match: Empty
    """
    from stn.nodes import Node  # type: ignore
    from .reader import parse_chunk_tokens  # type: ignore

    if not isinstance(condition_node, Node):
        return Empty

    entries = parse_chunk_tokens(condition_node.items)
    # Build condition dict {key: raw_str_value}
    conditions: dict[str, str] = {}
    for entry in entries:
        if entry.key is not None and isinstance(entry.value, str):
            conditions[entry.key] = entry.value

    if not conditions:
        return value

    def _matches(entity: VEntity) -> bool:
        for key, expected in conditions.items():
            actual = entity.fields.get(key) or entity.props.get(key)
            if actual is None:
                return False
            if str(actual) != expected:
                return False
        return True

    if isinstance(value, _Empty):
        return Empty

    if isinstance(value, VList):
        matches = [
            item for item in value.items
            if isinstance(item, VEntity) and _matches(item)
        ]
        if not matches:
            return Empty
        return matches[0] if len(matches) == 1 else VList(items=matches)

    if isinstance(value, VEntity):
        # Query over sub-entities (unnamed fields)
        elements = list(value.fields.values())
        matches = [e for e in elements if isinstance(e, VEntity) and _matches(e)]
        if not matches:
            return Empty
        return matches[0] if len(matches) == 1 else VList(items=matches)

    return Empty
