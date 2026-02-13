"""Chunk-level utilities: atom→Value conversion and implicit-dict normalisation."""

from __future__ import annotations

import re

from .model import Value, VDate, VText, VNumber, VList, VDict

_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def atom_to_value(atom: str) -> Value:
    """Convert a raw atom string to an appropriate Value.

    - Numeric strings → VNumber
    - Bracket-wrapped literals ``[...]`` → VText (brackets stripped)
    - Date-like strings (within literals) → VDate
    - Everything else → VText
    """
    if _NUMBER_RE.match(atom):
        return VNumber(float(atom))
    # Strip literal brackets
    if atom.startswith("[") and atom.endswith("]"):
        inner = atom[1:-1]
        # Check for date pattern inside literal
        if _DATE_RE.match(inner):
            return VDate(inner)
        return VText(inner)
    return VText(atom)


def normalize_implicit_dict(atoms: list[str]) -> VDict:
    """Convert a flat atom list with key markers into a VDict.

    Handles both pre-joined ``[":x", "10"]`` and sigil-separated
    ``[":", "x", "10"]`` formats (the lexer produces the latter).

    Example::

        [":", "x", "10", "20", ":", "y", "30"]
        → VDict({"x": VList([VNumber(10), VNumber(20)]),
                  "y": VNumber(30)})
    """
    entries: dict[str, Value] = {}
    current_key: str | None = None
    current_values: list[Value] = []
    i = 0

    while i < len(atoms):
        atom = atoms[i]
        if atom == ":":
            # Flush previous key
            if current_key is not None:
                entries[current_key] = _collapse(current_values)
                current_values = []
            # Next atom is the key name
            if i + 1 < len(atoms):
                current_key = atoms[i + 1]
                i += 2
            else:
                i += 1
        elif atom.startswith(":") and len(atom) > 1:
            # Pre-joined format (e.g. from test input)
            if current_key is not None:
                entries[current_key] = _collapse(current_values)
                current_values = []
            current_key = atom[1:]
            i += 1
        else:
            current_values.append(atom_to_value(atom))
            i += 1

    # Flush last key
    if current_key is not None:
        entries[current_key] = _collapse(current_values)

    return VDict(entries)


def _collapse(values: list[Value]) -> Value:
    """Return single value or VList."""
    if len(values) == 0:
        return VText("")
    if len(values) == 1:
        return values[0]
    return VList(values)
