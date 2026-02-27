"""End-to-end integration tests."""

import pytest
from stn import parse
from stn_core import evaluate, Empty, VText, VNumber, VEntity, VEnum


def test_completion_condition_entity():
    """@@joe (:name [Joe Smith] :age 36) → doc.locals_['joe'] has VEntity."""
    r = parse("@@joe (:name [Joe Smith] :age 36)")
    doc = evaluate(r)
    assert isinstance(doc.locals_["joe"], VEntity)


def test_completion_condition_getter():
    """@joe.name → VText('Joe Smith')."""
    r = parse("@@joe (:name [Joe Smith] :age 36)\n@joe.name")
    doc = evaluate(r)
    assert str(doc.results[0]) == "Joe Smith"


def test_completion_condition_typedef():
    """@%Person (:name :age %) → TypeDef registered."""
    r = parse("@%Person (:name :age %)")
    doc = evaluate(r)
    assert "Person" in doc.typedefs
    td = doc.typedefs["Person"]
    assert len(td.members) == 2


def test_completion_condition_undefined():
    """@nobody → Empty (no error)."""
    r = parse("@nobody")
    doc = evaluate(r)
    assert doc.results[0] is Empty


def test_completion_condition_data_block():
    """@_DATA.sec1 → VText from data block."""
    text = "@_DATA.sec1\n====data====\n---- @sec1\nhello world\n"
    r = parse(text)
    doc = evaluate(r)
    result = doc.results[0]
    assert isinstance(result, VText)
    assert "hello world" in str(result)


def test_typed_entity_with_typedef():
    r = parse(
        "@%Person (:name :age %)\n"
        "@@joe %Person(:name [Joe Smith] :age 36)"
    )
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert isinstance(joe, VEntity)
    assert joe.typedef is not None
    assert joe.typedef.name == "Person"
    assert str(joe.fields["name"]) == "Joe Smith"
    assert joe.fields["age"].value == 36.0


def test_typed_entity_with_enum():
    r = parse(
        "@%Person (:name :sex %e(F M))\n"
        "@@joe %Person(:name Joe :sex M)"
    )
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert isinstance(joe.fields["sex"], VEnum)
    assert joe.fields["sex"].value == "M"
    assert joe.fields["sex"].choices == ["F", "M"]


def test_multiple_vars_and_getters():
    r = parse(
        "@@a (:x 1)\n"
        "@@b (:x 2)\n"
        "@a.x\n"
        "@b.x"
    )
    doc = evaluate(r)
    assert doc.results[0].value == 1.0
    assert doc.results[1].value == 2.0


def test_setter_chain():
    r = parse("@@joe (:name Joe)\n@joe!age(36)!city(Tokyo)")
    doc = evaluate(r)
    joe = doc.results[0]
    assert isinstance(joe, VEntity)
    assert joe.props["age"].value == 36.0
    assert str(joe.props["city"]) == "Tokyo"


def test_public_and_local():
    r = parse("@@local_x 1\n@#pub_y 2\n@local_x\n#pub_y")
    doc = evaluate(r)
    assert doc.results[0].value == 1.0
    assert doc.results[1].value == 2.0


def test_positional_args():
    """Positional args assigned by TypeDef member order."""
    r = parse(
        "@%Person (:name :age %)\n"
        "@@joe %Person(Joe 36)"
    )
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert str(joe.fields["name"]) == "Joe"
    assert joe.fields["age"].value == 36.0


def test_str_representations():
    assert str(VText("hello")) == "hello"
    assert str(VNumber(42.0)) == "42"
    assert str(VNumber(3.14)) == "3.14"
    assert str(Empty) == "Empty"
