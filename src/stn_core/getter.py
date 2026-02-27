"""Getter resolution for STN Core."""

from __future__ import annotations

from .values import Value, VEntity, VList, _Empty, Empty


def apply_getter(value: Value, accessor: str) -> Value:
    """Resolve a single getter accessor on a value.

    - VEntity: fields first, then props, then 1-based index into fields
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
