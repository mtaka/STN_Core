"""Tests for variable definition and reference."""

import pytest
from stn import parse
from stn_core import evaluate, Empty, VText, VNumber, VEntity


def test_local_var_anonymous_entity():
    """@@joe (:name [Joe Smith] :age 36) → VEntity in locals_"""
    r = parse("@@joe (:name [Joe Smith] :age 36)")
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert isinstance(joe, VEntity)
    assert isinstance(joe.fields["name"], VText)
    assert str(joe.fields["name"]) == "Joe Smith"
    assert isinstance(joe.fields["age"], VNumber)
    assert joe.fields["age"].value == 36.0


def test_local_var_no_result():
    """Variable definition does not add to results."""
    r = parse("@@joe (:name Joe)")
    doc = evaluate(r)
    assert len(doc.results) == 0


def test_undefined_ref_is_empty():
    r = parse("@nobody")
    doc = evaluate(r)
    assert doc.results[0] is Empty


def test_local_ref_returns_entity():
    r = parse("@@joe (:name Joe)\n@joe")
    doc = evaluate(r)
    assert isinstance(doc.results[0], VEntity)


def test_public_var_definition():
    r = parse("@#answer 42")
    doc = evaluate(r)
    assert isinstance(doc.publics["answer"], VNumber)
    assert doc.publics["answer"].value == 42.0


def test_public_ref():
    r = parse("@#answer 42\n#answer")
    doc = evaluate(r)
    assert isinstance(doc.results[0], VNumber)
    assert doc.results[0].value == 42.0


def test_undefined_public_ref_is_empty():
    r = parse("#nobody")
    doc = evaluate(r)
    assert doc.results[0] is Empty


def test_local_var_scalar_number():
    r = parse("@@x 42")
    doc = evaluate(r)
    val = doc.locals_["x"]
    assert isinstance(val, VNumber)
    assert val.value == 42.0


def test_local_var_scalar_text():
    r = parse("@@greeting hello")
    doc = evaluate(r)
    val = doc.locals_["greeting"]
    assert isinstance(val, VText)
    assert val.value == "hello"


def test_local_var_literal():
    r = parse("@@msg [Hello World]")
    doc = evaluate(r)
    assert str(doc.locals_["msg"]) == "Hello World"


def test_multiple_statements():
    r = parse("@@a 1\n@@b 2\n@a\n@b")
    doc = evaluate(r)
    assert doc.results[0].value == 1.0
    assert doc.results[1].value == 2.0
