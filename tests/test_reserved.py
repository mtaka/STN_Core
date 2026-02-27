"""Tests for reserved elements (__) in TypeDef and VEntity."""

import pytest
from stn import parse
from stn_core import evaluate, Empty, VText, VNumber, VEntity


# ---------------------------------------------------------------------------
# TypeDef.reserved は定義時に設定される
# ---------------------------------------------------------------------------

def test_typedef_reserved_populated():
    """`@%Person (:__ (:type Person))` → TypeDef.reserved["__"] が設定される"""
    r = parse("@%Person (:__ (:type Person))")
    doc = evaluate(r)
    td = doc.typedefs["Person"]
    assert "__" in td.reserved
    reserved_val = td.reserved["__"]
    assert isinstance(reserved_val, VEntity)
    assert str(reserved_val.fields["type"]) == "Person"


def test_typedef_reserved_not_in_members():
    """`__` はメンバーリストに含まれない"""
    r = parse("@%Person (:__ (:type Person) :name :age %)")
    doc = evaluate(r)
    td = doc.typedefs["Person"]
    names = [m.name for m in td.members]
    assert "__" not in names
    assert "name" in names
    assert "age" in names


def test_typedef_no_reserved():
    """予約要素なしの TypeDef は reserved が空"""
    r = parse("@%Person (:name :age %)")
    doc = evaluate(r)
    td = doc.typedefs["Person"]
    assert td.reserved == {}


# ---------------------------------------------------------------------------
# VEntity.reserved はインスタンス化時に TypeDef から継承される
# ---------------------------------------------------------------------------

def test_instance_inherits_reserved_from_typedef():
    """`%Person(...)` でインスタンス化すると TypeDef.reserved が継承される"""
    r = parse(
        "@%Person (:__ (:type Person) :name)\n"
        "@@joe %Person(:name Joe)"
    )
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert "__" in joe.reserved
    reserved_val = joe.reserved["__"]
    assert isinstance(reserved_val, VEntity)
    assert str(reserved_val.fields["type"]) == "Person"


def test_instance_reserved_getter():
    """`@joe.__` でインスタンスの予約要素を取得できる"""
    r = parse(
        "@%Person (:__ (:type Person) :name)\n"
        "@@joe %Person(:name Joe)\n"
        "@joe.__"
    )
    doc = evaluate(r)
    result = doc.results[0]
    assert isinstance(result, VEntity)
    assert str(result.fields["type"]) == "Person"


def test_instance_reserved_chain_getter():
    """`@joe.__.type` でネストしたフィールドにアクセスできる"""
    r = parse(
        "@%Person (:__ (:type Person) :name)\n"
        "@@joe %Person(:name Joe)\n"
        "@joe.__.type"
    )
    doc = evaluate(r)
    result = doc.results[0]
    assert isinstance(result, VText)
    assert str(result) == "Person"


# ---------------------------------------------------------------------------
# インスタンスレベルの __ 設定（TypeDef なし）
# ---------------------------------------------------------------------------

def test_anonymous_entity_reserved():
    """TypeDef なしで `(:__ (:type Foo) :name bar)` → reserved に入る"""
    r = parse("@@x (:__ (:type Foo) :name bar)")
    doc = evaluate(r)
    x = doc.locals_["x"]
    assert "__" in x.reserved
    assert str(x.reserved["__"].fields["type"]) == "Foo"
    # name は通常フィールド
    assert "name" in x.fields
    assert str(x.fields["name"]) == "bar"


def test_anonymous_entity_reserved_getter():
    r = parse("@@x (:__ (:type Foo) :name bar)\n@x.__")
    doc = evaluate(r)
    result = doc.results[0]
    assert isinstance(result, VEntity)
    assert str(result.fields["type"]) == "Foo"


# ---------------------------------------------------------------------------
# TypeDef の __ はインスタンスで上書き不可
# ---------------------------------------------------------------------------

def test_typedef_reserved_not_overridable():
    """TypeDef の __ はインスタンスデータで上書きされない"""
    r = parse(
        "@%Person (:__ (:type Person) :name)\n"
        "@@joe %Person(:name Joe :__ (:type Override))"
    )
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    # TypeDef の __ が保たれる
    assert str(joe.reserved["__"].fields["type"]) == "Person"


# ---------------------------------------------------------------------------
# __ があっても通常フィールドは正常に設定される
# ---------------------------------------------------------------------------

def test_reserved_and_normal_fields_coexist():
    r = parse(
        "@%Person (:__ (:type Person) :name :age %)\n"
        "@@joe %Person(:name [Joe Smith] :age 36)"
    )
    doc = evaluate(r)
    joe = doc.locals_["joe"]
    assert str(joe.fields["name"]) == "Joe Smith"
    assert joe.fields["age"].value == 36.0
    assert "__" in joe.reserved


# ---------------------------------------------------------------------------
# REPL でも同様に動作する
# ---------------------------------------------------------------------------

def test_repl_reserved():
    from stn_core import STNRepl
    repl = STNRepl()
    repl.eval("@%Person (:__ (:type Person) :name)")
    repl.eval("@@joe %Person(:name Joe)")
    result = repl.eval("@joe.__.type")
    assert str(result) == "Person"
