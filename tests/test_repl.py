"""Tests for STNRepl and Document.merge()."""

import pytest
from stn import parse
from stn_core import STNRepl, Empty, VText, VNumber, VEntity, TypeDef
from stn_core.document import Document


# ---------------------------------------------------------------------------
# STNRepl.eval() basics
# ---------------------------------------------------------------------------

def test_eval_definition_returns_none():
    """Definitions produce no expression result → None."""
    repl = STNRepl()
    assert repl.eval("@@joe (:name Joe)") is None


def test_eval_expression_returns_value():
    repl = STNRepl()
    repl.eval("@@joe (:name [Joe Smith])")
    result = repl.eval("@joe.name")
    assert isinstance(result, VText)
    assert str(result) == "Joe Smith"


def test_eval_undefined_returns_empty():
    repl = STNRepl()
    result = repl.eval("@nobody")
    assert result is Empty


def test_eval_number_expression():
    repl = STNRepl()
    repl.eval("@@x 42")
    result = repl.eval("@x")
    assert isinstance(result, VNumber)
    assert result.value == 42.0


# ---------------------------------------------------------------------------
# State accumulation across multiple eval() calls
# ---------------------------------------------------------------------------

def test_typedef_persists_across_evals():
    repl = STNRepl()
    repl.eval("@%Person (:name :age %)")
    repl.eval("@@joe %Person(:name [Joe Smith] :age 36)")
    joe = repl.doc.locals_["joe"]
    assert isinstance(joe, VEntity)
    assert joe.typedef is not None
    assert joe.typedef.name == "Person"


def test_variable_persists_across_evals():
    repl = STNRepl()
    repl.eval("@@taro (:name 山田太郎 :age 26)")
    repl.eval("@@hanako (:name 山田花子 :age 24)")
    assert "taro" in repl.doc.locals_
    assert "hanako" in repl.doc.locals_


def test_getter_across_evals():
    repl = STNRepl()
    repl.eval("@@joe (:name [Joe Smith] :age 36)")
    result = repl.eval("@joe.name")
    assert str(result) == "Joe Smith"


def test_multi_line_eval():
    repl = STNRepl()
    repl.eval("@@taro (:name 山田太郎 :age 26)\n@@hanako (:name 山田花子 :age 24)")
    assert "taro" in repl.doc.locals_
    assert "hanako" in repl.doc.locals_
    result = repl.eval("@taro.name")
    assert str(result) == "山田太郎"


def test_last_result_updates_each_eval():
    repl = STNRepl()
    repl.eval("@@a (:x 1)")
    assert repl.doc.last_result is None  # only definition
    repl.eval("@a.x")
    assert repl.doc.last_result is not None
    assert repl.doc.last_result.value == 1.0


def test_results_accumulate():
    repl = STNRepl()
    repl.eval("@@a 1")
    repl.eval("@a")
    repl.eval("@a")
    assert len(repl.doc.results) == 2


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

def test_reset_clears_locals():
    repl = STNRepl()
    repl.eval("@@joe (:name Joe)")
    repl.reset()
    result = repl.eval("@joe")
    assert result is Empty


def test_reset_clears_typedefs():
    repl = STNRepl()
    repl.eval("@%Person (:name)")
    repl.reset()
    assert "Person" not in repl.doc.typedefs


def test_reset_clears_results():
    repl = STNRepl()
    repl.eval("@@x 1\n@x")
    repl.reset()
    assert len(repl.doc.results) == 0
    assert repl.doc.last_result is None


def test_reset_then_redefine():
    repl = STNRepl()
    repl.eval("@@x 1")
    repl.reset()
    repl.eval("@@x 99")
    result = repl.eval("@x")
    assert result.value == 99.0


# ---------------------------------------------------------------------------
# Document.merge() directly
# ---------------------------------------------------------------------------

def test_merge_typedef():
    doc = Document()
    r = parse("@%Person (:name :age %)")
    doc.merge(r)
    assert "Person" in doc.typedefs
    assert doc.last_result is None


def test_merge_local_var():
    doc = Document()
    r = parse("@@joe (:name Joe)")
    doc.merge(r)
    assert "joe" in doc.locals_


def test_merge_accumulates_across_calls():
    doc = Document()
    doc.merge(parse("@@a 1"))
    doc.merge(parse("@@b 2"))
    assert "a" in doc.locals_
    assert "b" in doc.locals_


def test_merge_last_result_expression():
    doc = Document()
    doc.merge(parse("@@joe (:name Joe)"))
    doc.merge(parse("@joe.name"))
    assert str(doc.last_result) == "Joe"


def test_merge_last_result_none_for_definitions():
    doc = Document()
    doc.merge(parse("@@joe (:name Joe)"))
    assert doc.last_result is None


def test_merge_data_block():
    doc = Document()
    text = "@@x 1\n====data====\n---- @sec1\nhello\n"
    doc.merge(parse(text))
    assert "_DATA" in doc.locals_
    data = doc.locals_["_DATA"]
    assert "sec1" in data.fields


def test_merge_data_merges_incrementally():
    """Second merge with a data block adds to existing _DATA."""
    doc = Document()
    doc.merge(parse("@@x 1\n====data====\n---- @sec1\nhello\n"))
    doc.merge(parse("@@y 2\n====data====\n---- @sec2\nworld\n"))
    data = doc.locals_["_DATA"]
    assert "sec1" in data.fields
    assert "sec2" in data.fields


# ---------------------------------------------------------------------------
# doc property access via repl.doc
# ---------------------------------------------------------------------------

def test_repl_doc_locals():
    repl = STNRepl()
    repl.eval("@@joe (:name Joe)")
    assert "joe" in repl.doc.locals_


def test_repl_doc_typedefs():
    repl = STNRepl()
    repl.eval("@%Person (:name)")
    assert "Person" in repl.doc.typedefs


def test_repl_doc_publics():
    repl = STNRepl()
    repl.eval("@#answer 42")
    assert "answer" in repl.doc.publics
