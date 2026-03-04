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
from .getter import (
    apply_getter,
    apply_symbol_getter,
    apply_node_getter,
    apply_query_locator,
)
from .setter import apply_setter, apply_batch_setter


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def evaluate(result) -> Document:
    """Evaluate a ParseResult (from stn.parse) and return a new Document."""
    env = Environment()
    doc = Document(environment=env)
    entries = _evaluate_into(result, env)
    for key, val in entries:
        doc.results.append(val)
        doc._doc_entries.append((key, val))
    return doc


def _evaluate_into(result, env: Environment) -> "list[tuple[str | None, Value]]":
    """Evaluate *result* into an existing *env*, returning (key, value) pairs.

    Used both by ``evaluate()`` and ``Document.merge()``.
    - Type definitions are added/overwritten in *env*.
    - Variable definitions are added/overwritten in *env*.
    - Data blocks are merged into the existing ``_DATA`` entity (or created).
    - Expression results are returned as (top-level-key, value) pairs.
    """
    # Merge _DATA into existing entity, or create a new one
    if result.data:
        existing = env.locals_.get("_DATA")
        if isinstance(existing, VEntity):
            for key, content in result.data.items():
                existing.fields[key] = VText(content)
        else:
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
    new_results: list[tuple[str | None, Value]] = []
    for stmt in statements:
        kind = _classify(stmt)
        if kind in ("local_def", "public_def", "typedef"):
            _eval_stmt(stmt, kind, env)  # side effects only, no result
            continue

        if kind == "expr":
            top_key, rhs_items = _extract_top_key(stmt)
            val, consumed = _eval_rhs_n(rhs_items, env)
            val = _eval_chain(val, rhs_items, consumed, env)
        else:
            # local_ref / symbol_ref / symbol_locator
            top_key = None
            val = _eval_stmt(stmt, kind, env)

        new_results.append((top_key, val))

    return new_results


def _extract_top_key(items: list) -> "tuple[str | None, list]":
    """If *items* starts with ':name', return (name, rest). Else (None, items)."""
    if (
        len(items) >= 2
        and isinstance(items[0], Token)
        and items[0].type == TokenType.SIGIL
        and items[0].value == ":"
        and items[0].word_head
        and not items[0].word_tail
        and isinstance(items[1], Token)
        and items[1].type == TokenType.ATOM
        and not items[1].word_head
    ):
        return items[1].value, items[2:]
    return None, items


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
            return "symbol_ref"
        if isinstance(i1, Node) and not i1.word_head:
            return "symbol_locator"  # #(#name) document locator

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
    if kind == "symbol_ref":
        return _eval_symbol_ref(items, env)
    if kind == "symbol_locator":
        return _eval_symbol_locator(items, env)
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
    rhs_items = items[3:]
    val, consumed = _eval_rhs_n(rhs_items, env)
    val = _eval_chain(val, rhs_items, consumed, env)
    env.set_local(name, val)


def _eval_public_def(items: list, env: Environment) -> None:
    """@#name value  →  env.symbols[name] = value"""
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    name = name_tok.value
    rhs_items = items[3:]
    val, consumed = _eval_rhs_n(rhs_items, env)
    val = _eval_chain(val, rhs_items, consumed, env)
    env.set_symbol(name, val)


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

    # Extract reserved __ entry (if any) before building TypeDef
    reserved: dict[str, Value] = {}
    for entry in parse_chunk_tokens(def_node.items):
        if entry.key == "__":
            if isinstance(entry.value, SObject):
                reserved["__"] = _entries_to_ventity(entry.value.entries, None, None, env)
            elif isinstance(entry.value, str) and entry.value:
                reserved["__"] = atom_to_value(entry.value)
            break

    # Regular members exclude __
    members = [m for m in parse_member_defs(def_node.items) if m.name != "__"]

    td = TypeDef(name=type_name, members=members)
    td.reserved.update(reserved)
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


def _eval_symbol_ref(items: list, env: Environment) -> Value:
    """#name [chain...]  →  resolve symbol and apply getters/setters"""
    if len(items) < 2:
        return Empty
    name_tok = items[1]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return Empty
    value: Value = env.get_symbol(name_tok.value)
    return _eval_chain(value, items, 2, env)


def _eval_symbol_locator(items: list, env: Environment) -> Value:
    """#(#name)  →  look up symbol 'name' in env.symbols"""
    if len(items) < 2:
        return Empty
    node = items[1]
    if not isinstance(node, Node):
        return Empty
    sym_name = _extract_symbol_name(node)
    if sym_name is None:
        return Empty
    value = env.get_symbol(sym_name)
    return _eval_chain(value, items, 2, env)


# ---------------------------------------------------------------------------
# RHS expression evaluation
# ---------------------------------------------------------------------------

def _eval_rhs(items: list, env: Environment) -> Value:
    """Evaluate the right-hand side of a definition or a bare expression."""
    val, _ = _eval_rhs_n(items, env)
    return val


def _eval_rhs_n(items: list, env: Environment) -> "tuple[Value, int]":
    """Like _eval_rhs but also returns the number of items consumed.

    Used when a getter/setter chain may follow the initial value.
    """
    if not items:
        return Empty, 0

    i0 = items[0]

    # Anonymous S-object: bare Node
    if isinstance(i0, Node):
        return _node_to_ventity(i0, None, None, env), 1

    if isinstance(i0, Token):
        # Typed instantiation: %TypeName(args) or %(args)
        if i0.type == TokenType.SIGIL and i0.value == "%":
            consumed = 1  # skip %
            if (
                consumed < len(items)
                and isinstance(items[consumed], Token)
                and items[consumed].type == TokenType.ATOM
                and not items[consumed].word_head
            ):
                consumed += 1  # skip TypeName
            if (
                consumed < len(items)
                and isinstance(items[consumed], Node)
                and not items[consumed].word_head
            ):
                consumed += 1  # skip (args)
            return _eval_instantiation(items, 0, env), consumed

        # Simple scalar
        if i0.type == TokenType.ATOM:
            return atom_to_value(unwrap_literal(i0.value)), 1
        if i0.type == TokenType.NUMBER:
            return VNumber(float(i0.value)), 1

    return Empty, 0


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

    # Inherit reserved from TypeDef (cannot be overridden by instance data)
    if td and td.reserved:
        entity.reserved.update(td.reserved)

    entries = parse_chunk_tokens(node.items)

    has_keys = any(e.key is not None for e in entries)

    if has_keys:
        for entry in entries:
            if entry.key == "__":
                # Only set if NOT already inherited from TypeDef (non-overridable)
                if "__" not in entity.reserved:
                    if isinstance(entry.value, SObject):
                        entity.reserved["__"] = _entries_to_ventity(
                            entry.value.entries, None, None, env
                        )
                continue
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
            # . followed by a glued Node: .(#name) or .(name) or .(N)
            if isinstance(nxt, Node) and not nxt.word_head:
                sym_name = _extract_symbol_name(nxt)
                if sym_name is not None:
                    value = apply_symbol_getter(value, sym_name)
                else:
                    value = apply_node_getter(value, nxt)
                i += 2
                continue
            # . followed by a glued Token: .name or .N
            if isinstance(nxt, Token) and not nxt.word_head:
                value = apply_getter(value, nxt.value)
                i += 2
                continue

        # Query locator: ?(conditions)
        if (
            item.type == TokenType.SIGIL
            and item.value == "?"
            and not item.word_head
            and i + 1 < len(items)
            and isinstance(items[i + 1], Node)
            and not items[i + 1].word_head
        ):
            value = apply_query_locator(value, items[i + 1], env)
            i += 2
            continue

        # Setter: !name(args) or !+(args) or !(#name) or !#(#name)
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

            # Symbol registration setter: !#(#name)
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.SIGIL
                and nxt.value == "#"
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Node)
                and not items[i + 2].word_head
            ):
                sym_name = _extract_symbol_name(items[i + 2])
                if sym_name is not None:
                    env.set_symbol(sym_name, value)
                i += 3
                continue

            # id shortcut setter: !(#name)
            if isinstance(nxt, Node) and not nxt.word_head:
                sym_name = _extract_symbol_name(nxt)
                if sym_name is not None:
                    value = _apply_id_setter(value, sym_name)
                    i += 2
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


def _extract_symbol_name(node: Node) -> "str | None":
    """Extract symbol name from a (#name) node. Returns 'name' or None."""
    items = node.items
    if (
        len(items) >= 2
        and isinstance(items[0], Token)
        and items[0].type == TokenType.SIGIL
        and items[0].value == "#"
        and isinstance(items[1], Token)
        and items[1].type == TokenType.ATOM
        and not items[1].word_head
    ):
        return items[1].value
    return None


def _apply_id_setter(value: Value, sym_name: str) -> Value:
    """!(#name) — set __(:id name) on an entity."""
    if not isinstance(value, VEntity):
        return value
    reserved_obj = value.reserved.get("__")
    if reserved_obj is None or not isinstance(reserved_obj, VEntity):
        reserved_obj = VEntity(typedef=None, type_name=None)
        value.reserved["__"] = reserved_obj
    # id is set only once (non-overridable)
    if "id" not in reserved_obj.fields:
        from .values import VText
        reserved_obj.fields["id"] = VText(sym_name)
    return value
