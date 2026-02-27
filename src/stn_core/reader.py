"""Reader layer: converts STN Lexer AST to intermediate S-objects."""

from __future__ import annotations

import re

from stn.tokenizer import Token, TokenType
from stn.nodes import Node

from .sobject import SObject, SEntry, SValue
from .typedef import MemberDef


_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Literal handling
# ---------------------------------------------------------------------------

def unwrap_literal(atom: str) -> str:
    """Remove [...] brackets and unescape \\]."""
    if atom.startswith("[") and atom.endswith("]"):
        inner = atom[1:-1]
        return inner.replace(r"\]", "]")
    return atom


def atom_to_value(s: str):
    """Convert a raw (already-unwrapped) string to a Value."""
    from .values import VNumber, VDate, VText
    if _NUMBER_RE.match(s):
        return VNumber(float(s))
    if _DATE_RE.match(s):
        return VDate(s)
    return VText(s)


# ---------------------------------------------------------------------------
# Chunk / statement splitting
# ---------------------------------------------------------------------------

def split_chunks(items: list) -> list[list]:
    """; トークンでitemsをチャンクのリストに分割。"""
    chunks: list[list] = []
    current: list = []
    for item in items:
        if (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == ";"
        ):
            chunks.append(current)
            current = []
        else:
            current.append(item)
    chunks.append(current)
    return chunks


def split_statements(items: list) -> list[list]:
    """Split root-level items into statements.

    Splits on:
    - Explicit ``;`` SIGIL tokens
    - Implicit: ``@`` or ``#`` SIGIL at word_head=True after an item
      that has word_tail=True (a new top-level expression starts).
    """
    statements: list[list] = []
    current: list = []

    for item in items:
        # Explicit split on ;
        if (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == ";"
        ):
            if current:
                statements.append(current)
                current = []
            continue

        # Implicit split: new top-level @ / # at a word boundary
        if (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value in ("@", "#")
            and item.word_head
            and current
            and _last_word_tail(current)
        ):
            statements.append(current)
            current = []

        current.append(item)

    if current:
        statements.append(current)

    return statements


def _last_word_tail(items: list) -> bool:
    if not items:
        return True
    last = items[-1]
    if isinstance(last, (Token, Node)):
        return last.word_tail
    return True


# ---------------------------------------------------------------------------
# Key-value detection helpers
# ---------------------------------------------------------------------------

def _is_colon_key(items: list, i: int) -> bool:
    """Return True if items[i] starts a :key gluing pattern."""
    if i + 1 >= len(items):
        return False
    item = items[i]
    nxt = items[i + 1]
    return (
        isinstance(item, Token)
        and item.type == TokenType.SIGIL
        and item.value == ":"
        and item.word_head
        and not item.word_tail
        and isinstance(nxt, Token)
        and nxt.type in (TokenType.ATOM, TokenType.NUMBER)
        and not nxt.word_head
    )


def _item_to_svalue(item) -> SValue:
    if isinstance(item, Token):
        return unwrap_literal(item.value)
    else:
        return _node_to_sobject(item)


def _node_to_sobject(node: Node) -> SObject:
    return SObject(parse_chunk_tokens(node.items))


# ---------------------------------------------------------------------------
# parse_chunk_tokens
# ---------------------------------------------------------------------------

def parse_chunk_tokens(items: list) -> list[SEntry]:
    """Parse items using gluing flags to detect :key value pairs.

    :(word_head=T, word_tail=F) + ATOM/NUMBER(word_head=F) → key start.
    Everything else → unnamed value (key=None).
    """
    entries: list[SEntry] = []
    i = 0

    while i < len(items):
        if _is_colon_key(items, i):
            key = items[i + 1].value
            i += 2

            # Collect value items until next :key or end
            val_items: list = []
            while i < len(items) and not _is_colon_key(items, i):
                val_items.append(items[i])
                i += 1

            if not val_items:
                entries.append(SEntry(key=key, value=""))
            elif len(val_items) == 1:
                entries.append(SEntry(key=key, value=_item_to_svalue(val_items[0])))
            else:
                sub = SObject(
                    [SEntry(key=None, value=_item_to_svalue(v)) for v in val_items]
                )
                entries.append(SEntry(key=key, value=sub))
        else:
            entries.append(SEntry(key=None, value=_item_to_svalue(items[i])))
            i += 1

    return entries


# ---------------------------------------------------------------------------
# Member definition parsing (for @% type definitions)
# ---------------------------------------------------------------------------

def parse_member_defs(items: list) -> list[MemberDef]:
    """Parse type definition member list from Node items.

    Each :name [annotation...] pair becomes a MemberDef.
    """
    members: list[MemberDef] = []
    i = 0

    while i < len(items):
        if not _is_colon_key(items, i):
            i += 1
            continue

        name = items[i + 1].value
        i += 2

        # Collect annotation tokens until next :key
        ann_items: list = []
        while i < len(items) and not _is_colon_key(items, i):
            ann_items.append(items[i])
            i += 1

        kind, choices, multi = _parse_type_annotation(ann_items)
        members.append(MemberDef(name=name, kind=kind, choices=choices, multi=multi))

    return members


def _parse_type_annotation(tokens: list) -> tuple[str, list[str], bool]:
    """Parse a type annotation token sequence.

    Examples:
        []            → ("text", [], False)
        [%]           → ("number", [], False)
        [%, d]        → ("date", [], False)
        [%, b]        → ("bool", [], False)
        [%, e, Node]  → ("enum", [...choices], False)
        [*, %, Type]  → ("Type", [], True)
        [%, ()]       → ("sobject", [], False)
    """
    if not tokens:
        return "text", [], False

    idx = 0
    multi = False

    # Optional leading *
    if (
        isinstance(tokens[idx], Token)
        and tokens[idx].type == TokenType.SIGIL
        and tokens[idx].value == "*"
    ):
        multi = True
        idx += 1
        if idx >= len(tokens):
            return "text", [], multi

    item = tokens[idx]

    if not (
        isinstance(item, Token)
        and item.type == TokenType.SIGIL
        and item.value == "%"
    ):
        # No % annotation
        return "text", [], False

    idx += 1

    if idx >= len(tokens):
        # Just % alone → number
        return "number", [], multi

    nxt = tokens[idx]

    # % glued to ATOM: %d, %b, %e, %f, %TypeName …
    if isinstance(nxt, Token) and not nxt.word_head:
        if nxt.type == TokenType.ATOM:
            shorthand = nxt.value
            idx += 1
            if shorthand in ("i", "int", "n", "num", "number"):
                return "number", [], multi
            if shorthand == "f":
                return "float", [], multi
            if shorthand == "d":
                return "date", [], multi
            if shorthand in ("dt", "datetime"):
                return "datetime", [], multi
            if shorthand == "b":
                return "bool", [], multi
            if shorthand == "e":
                # enum: choices in the next (glued) Node
                choices: list[str] = []
                if (
                    idx < len(tokens)
                    and isinstance(tokens[idx], Node)
                    and not tokens[idx].word_head
                ):
                    choice_node: Node = tokens[idx]
                    for c in choice_node.items:
                        if isinstance(c, Token):
                            choices.append(unwrap_literal(c.value))
                return "enum", choices, multi
            # User-defined type name
            return shorthand, [], multi

        if nxt.type == TokenType.NUMBER:
            return "number", [], multi

    # % glued to Node: %(...) → sobject
    if isinstance(nxt, Node) and not nxt.word_head:
        return "sobject", [], multi

    # % alone
    return "number", [], multi
