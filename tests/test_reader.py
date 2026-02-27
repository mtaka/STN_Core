"""Tests for the Reader layer."""

import pytest
from stn import parse
from stn.tokenizer import TokenType

from stn_core.reader import (
    split_chunks,
    split_statements,
    parse_chunk_tokens,
    parse_member_defs,
    unwrap_literal,
    atom_to_value,
)
from stn_core.sobject import SEntry, SObject
from stn_core.values import VNumber, VDate, VText


# ---------------------------------------------------------------------------
# unwrap_literal
# ---------------------------------------------------------------------------

def test_unwrap_literal_brackets():
    assert unwrap_literal("[Joe Smith]") == "Joe Smith"

def test_unwrap_literal_plain():
    assert unwrap_literal("hello") == "hello"

def test_unwrap_literal_escape():
    assert unwrap_literal(r"[a\]b]") == "a]b"


# ---------------------------------------------------------------------------
# atom_to_value
# ---------------------------------------------------------------------------

def test_atom_to_value_number():
    assert atom_to_value("36") == VNumber(36.0)

def test_atom_to_value_float():
    assert atom_to_value("3.14") == VNumber(3.14)

def test_atom_to_value_negative():
    assert atom_to_value("-5") == VNumber(-5.0)

def test_atom_to_value_date():
    assert atom_to_value("2024-01-15") == VDate("2024-01-15")

def test_atom_to_value_text():
    assert atom_to_value("hello") == VText("hello")


# ---------------------------------------------------------------------------
# split_chunks
# ---------------------------------------------------------------------------

def test_split_chunks_with_semicolon():
    r = parse("(a b ; c d)")
    node = r.ast.items[0]
    chunks = split_chunks(node.items)
    assert len(chunks) == 2
    assert chunks[0][0].value == "a"
    assert chunks[1][0].value == "c"

def test_split_chunks_no_semicolon():
    r = parse("(:name Joe :age 36)")
    node = r.ast.items[0]
    chunks = split_chunks(node.items)
    assert len(chunks) == 1

def test_split_chunks_multiple():
    r = parse("(a ; b ; c)")
    node = r.ast.items[0]
    chunks = split_chunks(node.items)
    assert len(chunks) == 3


# ---------------------------------------------------------------------------
# split_statements
# ---------------------------------------------------------------------------

def test_split_statements_newline_boundary():
    r = parse("@@joe (x)\n@joe.name")
    stmts = split_statements(r.ast.items)
    assert len(stmts) == 2

def test_split_statements_single():
    r = parse("@@joe (x)")
    stmts = split_statements(r.ast.items)
    assert len(stmts) == 1

def test_split_statements_explicit_semicolon():
    r = parse("@@a x ; @@b y")
    stmts = split_statements(r.ast.items)
    assert len(stmts) == 2


# ---------------------------------------------------------------------------
# parse_chunk_tokens
# ---------------------------------------------------------------------------

def test_colon_kv_by_glue():
    r = parse("(:name Joe :age 36)")
    node = r.ast.items[0]
    entries = parse_chunk_tokens(node.items)
    assert entries[0].key == "name"
    assert entries[0].value == "Joe"
    assert entries[1].key == "age"
    assert entries[1].value == "36"

def test_literal_unwrap():
    r = parse("(:name [Joe Smith])")
    node = r.ast.items[0]
    entries = parse_chunk_tokens(node.items)
    assert entries[0].key == "name"
    assert entries[0].value == "Joe Smith"

def test_unnamed_values():
    r = parse("(Joe Smith)")
    node = r.ast.items[0]
    entries = parse_chunk_tokens(node.items)
    assert all(e.key is None for e in entries)
    assert entries[0].value == "Joe"
    assert entries[1].value == "Smith"

def test_nested_node_as_value():
    r = parse("(:data (a b))")
    node = r.ast.items[0]
    entries = parse_chunk_tokens(node.items)
    assert entries[0].key == "data"
    assert isinstance(entries[0].value, SObject)

def test_preceded_by_ws_not_used():
    """Core uses word_head/tail, not preceded_by_ws."""
    r = parse("(:name Joe)")
    token = r.ast.items[0].items[0]  # ":"
    assert token.type == TokenType.SIGIL
    assert token.word_head is True


# ---------------------------------------------------------------------------
# parse_member_defs
# ---------------------------------------------------------------------------

def test_member_defs_text_default():
    r = parse("(:name)")
    node = r.ast.items[0]
    members = parse_member_defs(node.items)
    assert len(members) == 1
    assert members[0].name == "name"
    assert members[0].kind == "text"

def test_member_defs_number():
    r = parse("(:age %)")
    node = r.ast.items[0]
    members = parse_member_defs(node.items)
    assert members[0].kind == "number"

def test_member_defs_date():
    r = parse("(:duedate %d)")
    node = r.ast.items[0]
    members = parse_member_defs(node.items)
    assert members[0].kind == "date"

def test_member_defs_bool():
    r = parse("(:flag %b)")
    node = r.ast.items[0]
    members = parse_member_defs(node.items)
    assert members[0].kind == "bool"

def test_member_defs_enum():
    r = parse("(:sex %e(F M))")
    node = r.ast.items[0]
    members = parse_member_defs(node.items)
    assert members[0].kind == "enum"
    assert members[0].choices == ["F", "M"]

def test_member_defs_multi():
    r = parse("(:tasks *%Task)")
    node = r.ast.items[0]
    members = parse_member_defs(node.items)
    assert members[0].kind == "Task"
    assert members[0].multi is True

def test_member_defs_combined():
    r = parse("(:name :age % :sex %e(F M))")
    node = r.ast.items[0]
    members = parse_member_defs(node.items)
    assert [m.name for m in members] == ["name", "age", "sex"]
    assert members[0].kind == "text"
    assert members[1].kind == "number"
    assert members[2].kind == "enum"
    assert members[2].choices == ["F", "M"]
