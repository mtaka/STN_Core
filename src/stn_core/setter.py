"""Setter resolution for STN Core."""

from __future__ import annotations

from stn.nodes import Node

from .values import Value, VEntity, _Empty, Empty
from .reader import parse_chunk_tokens, atom_to_value


def apply_setter(value: Value, field_name: str, args_node: Node) -> Value:
    """Apply a single setter ``!name(args)`` to *value*.

    Sets ``value.props[field_name]`` from the first unnamed arg in *args_node*.
    Returns the mutated entity (setter chains return the object itself).
    """
    if isinstance(value, _Empty):
        return Empty
    if not isinstance(value, VEntity):
        return value

    entries = parse_chunk_tokens(args_node.items)
    if not entries:
        return value

    entry = entries[0]
    if isinstance(entry.value, str):
        value.props[field_name] = atom_to_value(entry.value)
    return value


def apply_batch_setter(value: Value, args_node: Node) -> Value:
    """Apply a batch setter ``!+(args)`` to *value*.

    Processes all ``key=val`` pairs in *args_node* and sets them in
    ``value.props``.
    """
    if isinstance(value, _Empty):
        return Empty
    if not isinstance(value, VEntity):
        return value

    entries = parse_chunk_tokens(args_node.items)
    for entry in entries:
        if entry.key is not None and isinstance(entry.value, str):
            value.props[entry.key] = atom_to_value(entry.value)
    return value
