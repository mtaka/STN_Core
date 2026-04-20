"""Tests for typedef parsing via evaluate()."""

import pytest
from stn import parse
from stn_core import evaluate, VEntity, VNumber, VText


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


# ---------------------------------------------------------------------------
# Space-separated %TypeName (args) inside nested () — reader.py fix
# ---------------------------------------------------------------------------

def test_nested_percent_type_space_args():
    """'%TypeName (args)' with a space is equivalent to '%TypeName(args)' inside nodes."""
    src = """\
@%BBox (:x1 % :y1 % :x2 % :y2 %)
@%R    (:bbox %BBox :label)
;
:container (
  :item %R (:bbox (:x1 1 :y1 2 :x2 3 :y2 4) :label [hello])
)
"""
    doc = evaluate(parse(src))
    c = doc.results[0]
    item = c.fields["item"]
    assert isinstance(item, VEntity)
    assert item.type_name == "R"
    bbox = item.fields["bbox"]
    assert isinstance(bbox, VEntity)
    assert bbox.fields["x1"] == VNumber(1.0)
    assert bbox.fields["y1"] == VNumber(2.0)
    assert item.fields["label"] == VText("hello")


def test_nested_percent_type_space_with_symbol_setter():
    """%TypeName (args)!#(#name) with space registers entity as symbol."""
    src = """\
@%R (:bbox %BBox :label)
;
:list (
  %R (:bbox (:x1 10 :y1 20 :x2 100 :y2 80) :label [test])!#(#myR)
)
"""
    doc = evaluate(parse(src))
    assert "myR" in doc.environment.symbols
    r = doc.environment.symbols["myR"]
    assert isinstance(r, VEntity)
    assert r.fields["label"] == VText("test")


def test_nested_percent_type_space_with_id_setter():
    """%TypeName (args)!(#name) with space sets id on entity."""
    src = """\
@%R (:bbox %BBox :label)
;
:list (
  %R (:bbox (:x1 10 :y1 20 :x2 100 :y2 80))!(#R999)
)
"""
    doc = evaluate(parse(src))
    lst = doc.results[0]
    entity = lst.fields.get("_0")
    assert isinstance(entity, VEntity)
    reserved_obj = entity.reserved.get("__")
    assert isinstance(reserved_obj, VEntity)
    assert reserved_obj.fields["id"] == VText("R999")
