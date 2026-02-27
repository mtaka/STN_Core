"""Evaluator: 2-pass evaluation of ParseResult → Document."""

from __future__ import annotations

from stn.tokenizer import Token, TokenType
from stn.nodes import Node

from .document import Document
from .environment import Environment
from .values import Value, VText, VNumber, VEntity, VList, _Empty, Empty
from .typedef import TypeDef, MemberDef
from .sobject import SObject, SEntry, SValue
from .reader import (
    split_statements,
    parse_chunk_tokens,
    parse_member_defs,
    unwrap_literal,
    atom_to_value,
)
from .getter import apply_getter
from .setter import apply_setter, apply_batch_setter


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate(result) -> Document:
    """Evaluate a ParseResult (from stn.parse) and return a Document."""
    env = Environment()
    doc = Document(environment=env)

    # Set up _DATA from the data block
    if result.data:
        data_entity = VEntity(typedef=None, type_name="_DATA")
        for key, content in result.data.items():
            data_entity.fields[key] = VText(content)
        env.set_local("_DATA", data_entity)

    statements = split_statements(result.ast.items)

    # Pass 1: collect type definitions
    for stmt in statements:
        if _classify(stmt) == "typedef":
            _eval_typedef(stmt, env)

    # Pass 2: evaluate all statements
    for stmt in statements:
        kind = _classify(stmt)
        val = _eval_stmt(stmt, kind, env)
        if val is not None:
            doc.results.append(val)

    return doc


# ---------------------------------------------------------------------------
# Statement classification
# ---------------------------------------------------------------------------

def _classify(items: list) -> str:
    """Classify a statement by its leading tokens.

    Returns one of:
        'local_def'  — @@name ...
        'public_def' — @#name ...
        'typedef'    — @%Name ...
        'local_ref'  — @name ...
        'public_ref' — #name ...
        'expr'       — anything else
    """
    if not items:
        return "expr"

    i0 = items[0]
    if not isinstance(i0, Token) or i0.type != TokenType.SIGIL:
        return "expr"

    if i0.value == "@" and len(items) >= 2:
        i1 = items[1]
        if isinstance(i1, Token) and not i1.word_head:
            if i1.type == TokenType.SIGIL:
                if i1.value == "@":
                    return "local_def"
                if i1.value == "#":
                    return "public_def"
                if i1.value == "%":
                    return "typedef"
            elif i1.type == TokenType.ATOM:
                return "local_ref"

    if i0.value == "#" and len(items) >= 2:
        i1 = items[1]
        if isinstance(i1, Token) and i1.type == TokenType.ATOM and not i1.word_head:
            return "public_ref"

    return "expr"


# ---------------------------------------------------------------------------
# Per-statement evaluation
# ---------------------------------------------------------------------------

def _eval_stmt(items: list, kind: str, env: Environment) -> Value | None:
    if kind == "local_def":
        _eval_local_def(items, env)
        return None
    if kind == "public_def":
        _eval_public_def(items, env)
        return None
    if kind == "typedef":
        # Already done in Pass 1; skip
        return None
    if kind == "local_ref":
        return _eval_local_ref(items, env)
    if kind == "public_ref":
        return _eval_public_ref(items, env)
    # expr
    return _eval_rhs(items, env)


# ---------------------------------------------------------------------------
# Definition statements
# ---------------------------------------------------------------------------

def _eval_local_def(items: list, env: Environment) -> None:
    """@@name value  →  env.locals_[name] = value"""
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    name = name_tok.value
    rhs = _eval_rhs(items[3:], env)
    env.set_local(name, rhs)


def _eval_public_def(items: list, env: Environment) -> None:
    """@#name value  →  env.publics[name] = value"""
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    name = name_tok.value
    rhs = _eval_rhs(items[3:], env)
    env.set_public(name, rhs)


def _eval_typedef(items: list, env: Environment) -> None:
    """@%Name (...)  →  env.typedefs[Name] = TypeDef"""
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    type_name = name_tok.value

    def_node: Node | None = None
    for item in items[3:]:
        if isinstance(item, Node):
            def_node = item
            break

    if def_node is None:
        return

    members = parse_member_defs(def_node.items)
    td = TypeDef(name=type_name, members=members)
    env.register_typedef(td)


# ---------------------------------------------------------------------------
# Reference statements (return a Value)
# ---------------------------------------------------------------------------

def _eval_local_ref(items: list, env: Environment) -> Value:
    """@name [chain...]  →  resolve and apply getters/setters"""
    if len(items) < 2:
        return Empty
    name_tok = items[1]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return Empty
    value: Value = env.get_local(name_tok.value)
    return _eval_chain(value, items, 2, env)


def _eval_public_ref(items: list, env: Environment) -> Value:
    """#name [chain...]  →  resolve and apply getters/setters"""
    if len(items) < 2:
        return Empty
    name_tok = items[1]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return Empty
    value: Value = env.get_public(name_tok.value)
    return _eval_chain(value, items, 2, env)


# ---------------------------------------------------------------------------
# RHS expression evaluation
# ---------------------------------------------------------------------------

def _eval_rhs(items: list, env: Environment) -> Value:
    """Evaluate the right-hand side of a definition or a bare expression."""
    if not items:
        return Empty

    i0 = items[0]

    # Anonymous S-object: bare Node
    if isinstance(i0, Node):
        return _node_to_ventity(i0, None, None, env)

    if isinstance(i0, Token):
        # Typed instantiation: %TypeName(args) or %(args)
        if i0.type == TokenType.SIGIL and i0.value == "%":
            return _eval_instantiation(items, 0, env)

        # Simple scalar
        if i0.type == TokenType.ATOM:
            return atom_to_value(unwrap_literal(i0.value))
        if i0.type == TokenType.NUMBER:
            return VNumber(float(i0.value))

    return Empty


def _eval_instantiation(items: list, start: int, env: Environment) -> Value:
    """Evaluate %TypeName(args) or %(args) starting at *start*."""
    i = start + 1  # skip the %

    type_name: str | None = None

    # Optional glued type name
    if i < len(items):
        nxt = items[i]
        if isinstance(nxt, Token) and nxt.type == TokenType.ATOM and not nxt.word_head:
            type_name = nxt.value
            i += 1

    td = env.resolve_typedef(type_name) if type_name else None

    # Glued args Node
    if i < len(items) and isinstance(items[i], Node) and not items[i].word_head:
        return _node_to_ventity(items[i], type_name, td, env)

    return VEntity(typedef=td, type_name=type_name)


# ---------------------------------------------------------------------------
# Node → VEntity
# ---------------------------------------------------------------------------

def _node_to_ventity(
    node: Node,
    type_name: str | None,
    td: TypeDef | None,
    env: Environment,
) -> VEntity:
    entity = VEntity(typedef=td, type_name=type_name)
    entries = parse_chunk_tokens(node.items)

    has_keys = any(e.key is not None for e in entries)

    if has_keys:
        for entry in entries:
            if entry.key == "__":
                continue  # reserved — Phase 2
            if entry.key is not None:
                member = _find_member(td, entry.key) if td else None
                entity.fields[entry.key] = _svalue_to_value(entry.value, member, env)
    else:
        # Positional args
        if td:
            non_reserved = [m for m in td.members if m.name != "__"]
            for idx, member in enumerate(non_reserved):
                if idx < len(entries):
                    entity.fields[member.name] = _svalue_to_value(
                        entries[idx].value, member, env
                    )
                else:
                    entity.fields[member.name] = Empty
        else:
            for idx, entry in enumerate(entries):
                entity.fields[f"_{idx}"] = _svalue_to_value(entry.value, None, env)

    return entity


def _find_member(td: TypeDef | None, name: str) -> MemberDef | None:
    if td is None:
        return None
    for m in td.members:
        if m.name == name:
            return m
    return None


def _svalue_to_value(sval: SValue, member: MemberDef | None, env: Environment) -> Value:
    """Convert an SValue to a proper Value, guided by MemberDef if available."""
    if isinstance(sval, str):
        if member is None:
            return atom_to_value(sval)
        return _coerce_str(sval, member, env)

    if isinstance(sval, SObject):
        if member is not None and member.kind not in (
            "text", "number", "float", "date", "datetime", "bool", "enum", "sobject"
        ):
            sub_td = env.resolve_typedef(member.kind)
            return _entries_to_ventity(sval.entries, member.kind, sub_td, env)
        return _entries_to_ventity(sval.entries, None, None, env)

    if isinstance(sval, list):
        return VList([
            _entries_to_ventity(s.entries, None, None, env)
            if isinstance(s, SObject)
            else Empty
            for s in sval
        ])

    return Empty


def _entries_to_ventity(
    entries: list[SEntry],
    type_name: str | None,
    td: TypeDef | None,
    env: Environment,
) -> VEntity:
    entity = VEntity(typedef=td, type_name=type_name)
    for entry in entries:
        if entry.key is not None:
            member = _find_member(td, entry.key) if td else None
            entity.fields[entry.key] = _svalue_to_value(entry.value, member, env)
        else:
            idx = len(entity.fields)
            entity.fields[f"_{idx}"] = _svalue_to_value(entry.value, None, env)
    return entity


def _coerce_str(raw: str, member: MemberDef, env: Environment) -> Value:
    """Coerce a raw string to the type specified by a MemberDef."""
    from .values import VBool, VEnum, VDate, VNumber, VText
    kind = member.kind

    if kind in ("number", "float"):
        try:
            return VNumber(float(raw))
        except ValueError:
            return VText(raw)

    if kind == "date":
        return VDate(raw)

    if kind == "bool":
        return VBool(raw.lower() in ("true", "1", "yes", "t"))

    if kind == "enum":
        return VEnum(raw, member.choices)

    return atom_to_value(raw)


# ---------------------------------------------------------------------------
# Getter / setter chain evaluation
# ---------------------------------------------------------------------------

def _eval_chain(value: Value, items: list, start: int, env: Environment) -> Value:
    """Walk a getter / setter chain starting at index *start*."""
    i = start
    while i < len(items):
        item = items[i]

        if not isinstance(item, Token):
            break

        # Getter: . ATOM/NUMBER (glued)
        if (
            item.type == TokenType.SIGIL
            and item.value == "."
            and not item.word_head
            and i + 1 < len(items)
        ):
            nxt = items[i + 1]
            if isinstance(nxt, Token) and not nxt.word_head:
                value = apply_getter(value, nxt.value)
                i += 2
                continue

        # Setter: !name(args) or !+(args)
        if (
            item.type == TokenType.SIGIL
            and item.value == "!"
            and not item.word_head
            and i + 1 < len(items)
        ):
            nxt = items[i + 1]

            # Batch setter: !+(args)
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.SIGIL
                and nxt.value == "+"
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Node)
                and not items[i + 2].word_head
            ):
                value = apply_batch_setter(value, items[i + 2])
                i += 3
                continue

            # Single setter: !name(args)
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.ATOM
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Node)
                and not items[i + 2].word_head
            ):
                value = apply_setter(value, nxt.value, items[i + 2])
                i += 3
                continue

        break

    return value
