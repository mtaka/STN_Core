"""Tests for Document.get(), SObject.get(), and top-level key tracking."""

import pytest

from stn import parse
from stn_core import evaluate, STNRepl, Empty
from stn_core.values import VNumber, VText, VEntity
from stn_core.sobject import SObject, SEntry


# ---------------------------------------------------------------------------
# SObject.get()
# ---------------------------------------------------------------------------

def test_sobject_get_by_name():
    obj = SObject(entries=[
        SEntry(key="foo", value="hello"),
        SEntry(key="bar", value="world"),
    ])
    assert obj.get("foo") == "hello"
    assert obj.get("bar") == "world"


def test_sobject_get_by_index():
    obj = SObject(entries=[
        SEntry(key=None, value="a"),
        SEntry(key="x", value="b"),
    ])
    assert obj.get(1) == "a"
    assert obj.get(2) == "b"


def test_sobject_get_missing_key():
    obj = SObject(entries=[SEntry(key="foo", value="v")])
    assert obj.get("missing") is Empty


def test_sobject_get_zero_index():
    obj = SObject(entries=[SEntry(key=None, value="v")])
    assert obj.get(0) is Empty


def test_sobject_get_out_of_range():
    obj = SObject(entries=[SEntry(key=None, value="v")])
    assert obj.get(2) is Empty


def test_sobject_get_negative_index():
    obj = SObject(entries=[SEntry(key=None, value="v")])
    assert obj.get(-1) is Empty


# ---------------------------------------------------------------------------
# Document.get() — index access
# ---------------------------------------------------------------------------

def test_doc_get_single_number():
    doc = evaluate(parse("1"))
    assert doc.get(1) == VNumber(1)


def test_doc_get_index_out_of_range():
    doc = evaluate(parse("1"))
    assert doc.get(2) is Empty


def test_doc_get_zero_is_invalid():
    doc = evaluate(parse("1"))
    assert doc.get(0) is Empty


def test_doc_get_ref_result():
    doc = evaluate(parse("@@joe (:name [Joe Smith])\n@joe.name"))
    # @@joe definition doesn't produce an entry; @joe.name does
    assert doc.get(1) == VText("Joe Smith")


def test_doc_get_multiple_exprs():
    doc = evaluate(parse("@@x 1\n@x\n@x"))
    # @x appears twice as expressions → entries at index 1 and 2
    assert doc.get(1) == VNumber(1)
    assert doc.get(2) == VNumber(1)
    assert doc.get(3) is Empty


# ---------------------------------------------------------------------------
# Document.get() — named key access
# ---------------------------------------------------------------------------

def test_doc_get_named_key():
    doc = evaluate(parse(":something (:key value)"))
    result = doc.get("something")
    assert isinstance(result, VEntity)
    assert result.fields["key"] == VText("value")


def test_doc_get_named_key_missing():
    doc = evaluate(parse(":foo 1"))
    assert doc.get("bar") is Empty


def test_doc_get_named_scalar():
    doc = evaluate(parse(":count 42"))
    assert doc.get("count") == VNumber(42)


def test_doc_get_named_text():
    doc = evaluate(parse(":title [Hello World]"))
    assert doc.get("title") == VText("Hello World")


def test_doc_get_mixed_named_and_unnamed():
    # ; is required to split :name ... and 42 into separate statements
    doc = evaluate(parse(":name [Joe] ; 42"))
    assert doc.get("name") == VText("Joe")
    assert doc.get(2) == VNumber(42)


# ---------------------------------------------------------------------------
# Document.get() via REPL (merge)
# ---------------------------------------------------------------------------

def test_repl_doc_get_named():
    repl = STNRepl()
    repl.eval(":section (:title Hello)")
    result = repl.doc.get("section")
    assert isinstance(result, VEntity)
    assert result.fields["title"] == VText("Hello")


def test_repl_doc_get_index_across_calls():
    repl = STNRepl()
    repl.eval("1")
    repl.eval("2")
    assert repl.doc.get(1) == VNumber(1)
    assert repl.doc.get(2) == VNumber(2)


def test_repl_doc_get_defs_not_counted():
    repl = STNRepl()
    repl.eval("@@x 10")  # definition — not counted as entry
    repl.eval("@x")      # expression → entry 1
    assert repl.doc.get(1) == VNumber(10)
    assert repl.doc.get(2) is Empty
