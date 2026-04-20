"""System function implementations for STN Core.

System functions are pre-registered in every Environment.  Their signatures
match the STN spec (sec. 4) and are implemented in Python.
"""

from __future__ import annotations

import uuid as _uuid_mod
from datetime import date, datetime

from .values import Value, VText, VNumber, VDate, VBool, VList, VEntity, _Empty, Empty
from .funcdef import FuncDef, ParamDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bool(v: Value) -> bool:
    if isinstance(v, _Empty):
        return False
    if isinstance(v, VBool):
        return v.value
    if isinstance(v, VNumber):
        return v.value != 0
    if isinstance(v, VText):
        return v.value.lower() not in ("false", "0", "", "empty")
    return True


def _to_float(v: Value) -> float | None:
    try:
        return float(str(v))
    except (ValueError, TypeError):
        return None


def _iter_values(v: Value) -> list[Value]:
    if isinstance(v, VList):
        return v.items
    if isinstance(v, VEntity):
        return list(v.fields.values())
    return []


# ---------------------------------------------------------------------------
# 4-1  Structural operations
# ---------------------------------------------------------------------------

def _sys_sep(st: Value, sep: Value | None = None) -> Value:
    """Split string *st* on *sep* (default: whitespace). Returns VList."""
    text = str(st) if not isinstance(st, _Empty) else ""
    if sep is None or isinstance(sep, _Empty):
        parts = text.split()
    else:
        parts = text.split(str(sep))
    return VList([VText(p) for p in parts if p])


def _sys_cat(s: Value, sep: Value | None = None) -> Value:
    """Join elements of *s* with *sep* (default: empty string). Returns VText."""
    joiner = str(sep) if sep is not None and not isinstance(sep, _Empty) else ""
    parts = [str(v) for v in _iter_values(s)] if not isinstance(s, _Empty) else [str(s)]
    return VText(joiner.join(parts))


def _sys_len(obj: Value) -> Value:
    """Length of a string or collection."""
    if isinstance(obj, VText):
        return VNumber(len(obj.value))
    if isinstance(obj, VList):
        return VNumber(len(obj.items))
    if isinstance(obj, VEntity):
        return VNumber(len(obj.fields))
    return VNumber(0)


def _sys_get(obj: Value, key: Value) -> Value:
    """Field/prop getter: get(obj key) == obj.(key)."""
    from .getter import apply_getter
    return apply_getter(obj, str(key))


# ---------------------------------------------------------------------------
# 4-2  Comparison / logical operations
# ---------------------------------------------------------------------------

def _sys_eq(a: Value, b: Value) -> Value:
    return VBool(str(a) == str(b))


def _sys_gt(a: Value, b: Value) -> Value:
    fa, fb = _to_float(a), _to_float(b)
    if fa is not None and fb is not None:
        return VBool(fa > fb)
    return VBool(str(a) > str(b))


def _sys_lt(a: Value, b: Value) -> Value:
    fa, fb = _to_float(a), _to_float(b)
    if fa is not None and fb is not None:
        return VBool(fa < fb)
    return VBool(str(a) < str(b))


def _sys_and(a: Value, b: Value) -> Value:
    return VBool(_to_bool(a) and _to_bool(b))


def _sys_or(a: Value, b: Value) -> Value:
    return VBool(_to_bool(a) or _to_bool(b))


def _sys_not(obj: Value) -> Value:
    return VBool(not _to_bool(obj))


def _sys_eg(a: Value, b: Value) -> Value:
    """Greater than or equal: not (a < b)."""
    return _sys_not(_sys_lt(a, b))


def _sys_el(a: Value, b: Value) -> Value:
    """Less than or equal: not (a > b)."""
    return _sys_not(_sys_gt(a, b))


def _sys_contains(a: Value, e: Value) -> Value:
    """True if collection *a* contains element *e*, or string *a* contains substring *e*."""
    if isinstance(a, VList):
        target = str(e)
        return VBool(any(str(item) == target for item in a.items))
    if isinstance(a, VText):
        return VBool(str(e) in a.value)
    return VBool(False)


# ---------------------------------------------------------------------------
# 4-3  Aggregation
# ---------------------------------------------------------------------------

def _sys_size(s: Value) -> Value:
    """Size of a collection (alias of len)."""
    return _sys_len(s)


def _sys_sum(s: Value) -> Value:
    """Sum of numeric elements in a collection."""
    total = 0.0
    for v in _iter_values(s):
        f = _to_float(v)
        if f is not None:
            total += f
    result = VNumber(total)
    return result


def _sys_any(s: Value) -> Value:
    """True if any element in collection is truthy."""
    return VBool(any(_to_bool(v) for v in _iter_values(s)))


def _sys_all(s: Value) -> Value:
    """True if all elements in collection are truthy."""
    items = _iter_values(s)
    return VBool(bool(items) and all(_to_bool(v) for v in items))


# ---------------------------------------------------------------------------
# 4-4  Date/time and identifier generation
# ---------------------------------------------------------------------------

def _sys_today() -> Value:
    return VDate(date.today().isoformat())


def _sys_now() -> Value:
    return VText(datetime.now().isoformat(timespec="seconds"))


def _sys_date(y: Value, m: Value = VNumber(1), d: Value = VNumber(1)) -> Value:
    try:
        return VDate(f"{int(float(str(y))):04d}-{int(float(str(m))):02d}-{int(float(str(d))):02d}")
    except (ValueError, TypeError):
        return Empty


def _sys_ym(y: Value, m: Value) -> Value:
    try:
        return VText(f"{int(float(str(y))):04d}-{int(float(str(m))):02d}")
    except (ValueError, TypeError):
        return Empty


def _sys_strftime(o: Value, fmt: Value) -> Value:
    """Format a date/datetime value as a string."""
    try:
        d = date.fromisoformat(str(o))
        return VText(d.strftime(str(fmt)))
    except (ValueError, TypeError):
        return Empty


def _sys_strptime(st: Value, fmt: Value) -> Value:
    """Parse a date string into a VDate."""
    try:
        d = datetime.strptime(str(st), str(fmt)).date()
        return VDate(d.isoformat())
    except (ValueError, TypeError):
        return Empty


def _sys_uuid() -> Value:
    return VText(str(_uuid_mod.uuid4()))


def _sys_base58(s: Value) -> Value:
    """Base58-encode a string (UUID without hyphens)."""
    import hashlib
    ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    raw = str(s).replace("-", "")
    try:
        num = int(raw, 16)
    except ValueError:
        num = int.from_bytes(str(s).encode(), "big")
    result = []
    while num > 0:
        num, rem = divmod(num, 58)
        result.append(ALPHABET[rem])
    return VText("".join(reversed(result)))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _fd(name: str, params: list[tuple], impl) -> FuncDef:
    """Build a FuncDef from (param_name, default_or_None) pairs."""
    return FuncDef(
        name=name,
        params=[ParamDef(name=n, default=d) for n, d in params],
        impl=impl,
    )


def get_system_functions() -> list[FuncDef]:
    """Return all system FuncDef objects ready for registration."""
    return [
        # Structural
        _fd("sep",      [("st", None), ("sep", None)],          _sys_sep),
        _fd("cat",      [("s", None),  ("sep", None)],          _sys_cat),
        _fd("len",      [("obj", None)],                         _sys_len),
        _fd("get",      [("obj", None), ("key", None)],          _sys_get),
        # Comparison / logical
        _fd("eq",       [("a", None), ("b", None)],              _sys_eq),
        _fd("gt",       [("a", None), ("b", None)],              _sys_gt),
        _fd("lt",       [("a", None), ("b", None)],              _sys_lt),
        _fd("and",      [("a", None), ("b", None)],              _sys_and),
        _fd("or",       [("a", None), ("b", None)],              _sys_or),
        _fd("not",      [("obj", None)],                         _sys_not),
        _fd("eg",       [("a", None), ("b", None)],              _sys_eg),
        _fd("el",       [("a", None), ("b", None)],              _sys_el),
        _fd("contains", [("a", None), ("e", None)],              _sys_contains),
        # Aggregation
        _fd("size",     [("s", None)],                           _sys_size),
        _fd("sum",      [("s", None)],                           _sys_sum),
        _fd("any",      [("s", None)],                           _sys_any),
        _fd("all",      [("s", None)],                           _sys_all),
        # Date/time
        _fd("today",    [],                                       _sys_today),
        _fd("now",      [],                                       _sys_now),
        _fd("date",     [("y", None), ("m", VNumber(1)), ("d", VNumber(1))], _sys_date),
        _fd("ym",       [("y", None), ("m", None)],              _sys_ym),
        _fd("strftime", [("o", None), ("fmt", None)],            _sys_strftime),
        _fd("strptime", [("st", None), ("fmt", None)],           _sys_strptime),
        # Identifiers
        _fd("uuid",     [],                                       _sys_uuid),
        _fd("base58",   [("s", None)],                           _sys_base58),
    ]
