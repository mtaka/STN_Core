"""Tests for typedef parsing via evaluate()."""

import pytest
from stn import parse
from stn_core import evaluate


def test_typedef_basic():
    r = parse("@%Person (:name :age % :sex %e(F M))")
    doc = evaluate(r)
    td = doc.typedefs["Person"]
    assert [m.name for m in td.members] == ["name", "age", "sex"]
    assert td.members[0].kind == "text"
    assert td.members[1].kind == "number"
    assert td.members[2].kind == "enum"
    assert td.members[2].choices == ["F", "M"]


def test_typedef_registered():
    r = parse("@%Person (:name :age %)")
    doc = evaluate(r)
    assert "Person" in doc.typedefs


def test_typedef_no_result():
    """Type definitions do not produce a result value."""
    r = parse("@%Person (:name)")
    doc = evaluate(r)
    assert len(doc.results) == 0


def test_typedef_date_member():
    r = parse("@%Task (:title :duedate %d)")
    doc = evaluate(r)
    td = doc.typedefs["Task"]
    assert td.members[1].kind == "date"


def test_typedef_bool_member():
    r = parse("@%Setting (:enabled %b)")
    doc = evaluate(r)
    td = doc.typedefs["Setting"]
    assert td.members[0].kind == "bool"


def test_typedef_multi_member():
    r = parse("@%Person (:name :tasks *%Task)")
    doc = evaluate(r)
    td = doc.typedefs["Person"]
    tasks_member = td.members[1]
    assert tasks_member.kind == "Task"
    assert tasks_member.multi is True


def test_typedef_sobject_member():
    r = parse("@%Person (:name :body %())")
    doc = evaluate(r)
    td = doc.typedefs["Person"]
    assert td.members[1].kind == "sobject"
