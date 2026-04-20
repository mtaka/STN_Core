"""Tests for type extension: parent types, class props, pre/post constructor setters."""

import pytest
from stn_core import STNRepl, Empty, VText, VNumber, VEntity, VList
from stn_core.typedef import TypeDef


# ---------------------------------------------------------------------------
# 1. Basic parent type + class props (typedef level)
# ---------------------------------------------------------------------------

def test_typedef_with_parent():
    """@%Japanese %Human defines Japanese with Human as parent."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human")
    td = repl.doc.typedefs.get("Japanese")
    assert td is not None
    assert td.parent is not None
    assert td.parent.name == "Human"


def test_typedef_parent_inherits_constructor():
    """@%Japanese %Human inherits Human's constructor (name)."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human")
    td = repl.doc.typedefs["Japanese"]
    assert len(td.members) == 1
    assert td.members[0].name == "name"


def test_typedef_class_props_stored():
    """@%Japanese %Human!nationality(Japan) stores nationality in typedef.props."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)")
    td = repl.doc.typedefs["Japanese"]
    assert "nationality" in td.props
    assert str(td.props["nationality"]) == "Japan"


def test_typedef_multiple_class_props():
    """Multiple !setter chains all stored as class props."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)!language(Japanese)")
    td = repl.doc.typedefs["Japanese"]
    assert str(td.props["nationality"]) == "Japan"
    assert str(td.props["language"]) == "Japanese"


def test_typedef_constructor_override():
    """@%T %Parent!prop(v)(:a :b) — constructor override with new members."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)(:name :region)")
    td = repl.doc.typedefs["Japanese"]
    assert [m.name for m in td.members] == ["name", "region"]
    assert str(td.props["nationality"]) == "Japan"


def test_typedef_batch_class_props():
    """!+(:k1 v1 :k2 v2) as class props."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!+(:nationality Japan :language Japanese)")
    td = repl.doc.typedefs["Japanese"]
    assert str(td.props["nationality"]) == "Japan"
    assert str(td.props["language"]) == "Japanese"


# ---------------------------------------------------------------------------
# 2. Instance access to class props via typedef chain
# ---------------------------------------------------------------------------

def test_instance_inherits_class_prop():
    """Instance of subtype can access parent class props via getter."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)")
    repl.eval("@@sato %Japanese(Taro)")
    val = repl.eval("@sato.nationality")
    assert str(val) == "Japan"


def test_instance_own_field_takes_priority():
    """Instance field takes priority over typedef class prop of same key."""
    repl = STNRepl()
    repl.eval("@%Human (:name :nationality)")
    repl.eval("@%Japanese %Human!nationality(Japan)")
    repl.eval("@@sato %Japanese(Taro USA)")  # positional: name=Taro, nationality=USA
    val = repl.eval("@sato.nationality")
    assert str(val) == "USA"


def test_typedef_class_prop_accessible_as_default():
    """Typedef class prop is accessible when instance has no override."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)")
    repl.eval("@@sato %Japanese(Taro)")
    val = repl.eval("@sato.nationality")
    assert str(val) == "Japan"  # from typedef.props


def test_typedef_class_prop_overridable_by_instance_setter():
    """Typedef class prop CAN be overridden by instance !setter (customization)."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)")
    repl.eval("@@sato %Japanese(Taro)")
    repl.eval("@sato!nationality(USA)")  # instance override → props
    val = repl.eval("@sato.nationality")
    assert str(val) == "USA"  # props takes priority over typedef.props


def test_two_level_inheritance():
    """Three-level chain: Tokyoan → Japanese → Human."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)")
    repl.eval("@%Tokyoan %Japanese!living(Tokyo)")
    repl.eval("@@ken %Tokyoan(Ken)")
    assert str(repl.eval("@ken.nationality")) == "Japan"
    assert str(repl.eval("@ken.living")) == "Tokyo"
    assert str(repl.eval("@ken.name")) == "Ken"


def test_typedef_chain_stored_correctly():
    """TypeDef parent chain is correct."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@%Japanese %Human!nationality(Japan)")
    repl.eval("@%Tokyoan %Japanese!living(Tokyo)")
    td_tokyoan = repl.doc.typedefs["Tokyoan"]
    assert td_tokyoan.parent.name == "Japanese"
    assert td_tokyoan.parent.parent.name == "Human"


# ---------------------------------------------------------------------------
# 3. Pre-constructor setters during instantiation
# ---------------------------------------------------------------------------

def test_pre_constructor_setter_stored_in_fields():
    """Pre-constructor !setter goes to entity.fields (constant)."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    val = repl.eval("%Human!nationality(Japan)(Taro)")
    assert isinstance(val, VEntity)
    assert "nationality" in val.fields
    assert str(val.fields["nationality"]) == "Japan"
    assert str(val.fields["name"]) == "Taro"


def test_pre_constructor_setter_is_constant():
    """Pre-constructor !setter cannot be overridden by post-constructor setter."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human!nationality(Japan)(Taro)")
    repl.eval("@sato!nationality(China)")
    val = repl.eval("@sato.nationality")
    assert str(val) == "Japan"


def test_post_constructor_setter_goes_to_props():
    """Post-constructor !setter goes to entity.props."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    val = repl.eval("%Human(Taro)!commutes(Company)")
    assert isinstance(val, VEntity)
    assert "commutes" in val.props
    assert str(val.props["commutes"]) == "Company"


def test_pre_and_post_constructor_setters():
    """Both pre and post constructor setters work correctly."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human!nationality(Japan)(Taro)!commutes(Company)")
    e = repl.doc.locals_["sato"]
    assert str(e.fields["nationality"]) == "Japan"   # pre-constructor → fields
    assert str(e.fields["name"]) == "Taro"           # constructor arg → fields
    assert str(e.props["commutes"]) == "Company"     # post-constructor → props
    # All accessible via getter
    assert str(repl.eval("@sato.nationality")) == "Japan"
    assert str(repl.eval("@sato.name")) == "Taro"
    assert str(repl.eval("@sato.commutes")) == "Company"


def test_pre_constructor_batch_setter():
    """Pre-constructor !+(:k v ...) batch setter."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    val = repl.eval("%Human!+(:nationality Japan :language Japanese)(Taro)")
    assert str(val.fields["nationality"]) == "Japan"
    assert str(val.fields["language"]) == "Japanese"
    assert str(val.fields["name"]) == "Taro"
