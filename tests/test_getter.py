"""Tests for getter access."""

import pytest
from stn import parse
from stn_core import evaluate, Empty, VText, VNumber


def test_getter_field_name():
    r = parse("@@joe (:name [Joe Smith] :age 36)\n@joe.name")
    doc = evaluate(r)
    assert str(doc.locals_["joe"].fields["name"]) == "Joe Smith"
    assert str(doc.results[0]) == "Joe Smith"


def test_getter_number_field():
    r = parse("@@joe (:name Joe :age 36)\n@joe.age")
    doc = evaluate(r)
    assert isinstance(doc.results[0], VNumber)
    assert doc.results[0].value == 36.0


def test_getter_index():
    r = parse("@@joe (:name Joe :age 36)\n@joe.1")
    doc = evaluate(r)
    assert str(doc.results[0]) == "Joe"


def test_getter_undefined_field():
    r = parse("@@joe (:name Joe)\n@joe.missing")
    doc = evaluate(r)
    assert doc.results[0] is Empty


def test_getter_on_empty():
    r = parse("@nobody.name")
    doc = evaluate(r)
    assert doc.results[0] is Empty


def test_getter_chain():
    r = parse("@@org (:boss (:name Joe))\n@org.boss")
    doc = evaluate(r)
    # boss is a nested S-object
    from stn_core import VEntity
    assert isinstance(doc.results[0], VEntity)


def test_data_block_getter():
    text = "@@x 1\n====data====\n---- @sec1\nhello\n"
    r = parse(text)
    doc = evaluate(r)
    result = doc.locals_.get("_DATA")
    assert result is not None
    from stn_core import VEntity
    assert isinstance(result, VEntity)
    assert str(result.fields["sec1"]).strip() == "hello"
