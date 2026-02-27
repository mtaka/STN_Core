"""Tests for setter operations."""

import pytest
from stn import parse
from stn_core import evaluate, VNumber, VText, VEntity


def test_single_setter():
    r = parse("@@joe (:name Joe :age 20)\n@joe!age(36)")
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert "age" in joe.props
    assert joe.props["age"].value == 36.0


def test_setter_returns_entity():
    r = parse("@@joe (:name Joe)\n@joe!age(36)")
    doc = evaluate(r)
    assert isinstance(doc.results[0], VEntity)


def test_batch_setter():
    r = parse("@@joe (:name Joe)\n@joe!+(:age 36 :city Tokyo)")
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert joe.props["age"].value == 36.0
    assert str(joe.props["city"]) == "Tokyo"


def test_setter_on_empty():
    r = parse("@nobody!age(36)")
    doc = evaluate(r)
    from stn_core import Empty
    assert doc.results[0] is Empty
