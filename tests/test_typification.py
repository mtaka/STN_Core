"""Tests for typification (%(@var)) and unsetter (!-)."""

import pytest
from stn_core import STNRepl, Empty, VText, VNumber, VEntity, VList
from stn_core.typedef import TypeDef


# ---------------------------------------------------------------------------
# 1. Typification: @%Name %(@var)
# ---------------------------------------------------------------------------

def test_typification_creates_typedef():
    """@%SatolikePerson %(@sato) creates a TypeDef named SatolikePerson."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@%SatolikePerson %(@sato)")
    td = repl.doc.typedefs.get("SatolikePerson")
    assert td is not None


def test_typification_copies_fields_to_props():
    """TypeDef from typification has entity fields in td.props."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@%SatolikePerson %(@sato)")
    td = repl.doc.typedefs["SatolikePerson"]
    assert str(td.props["name"]) == "Taro"
    assert str(td.props["job"]) == "Engineer"


def test_typification_inherits_constructor():
    """Typification typedef inherits constructor members from source entity's typedef."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@%SatolikePerson %(@sato)")
    td = repl.doc.typedefs["SatolikePerson"]
    member_names = [m.name for m in td.members]
    assert member_names == ["name", "job"]


def test_typification_instance_access_props():
    """Instance of typification type can access typedef props via getter."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@%SatolikePerson %(@sato)")
    repl.eval("@@person2 %SatolikePerson()")
    assert str(repl.eval("@person2.name")) == "Taro"
    assert str(repl.eval("@person2.job")) == "Engineer"


def test_typification_instance_constructor_override():
    """Positional constructor args override typification props in instance fields."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@%SatolikePerson %(@sato)")
    repl.eval("@@person2 %SatolikePerson(Hanako)")
    assert str(repl.eval("@person2.name")) == "Hanako"
    assert str(repl.eval("@person2.job")) == "Engineer"  # from typedef.props


def test_typification_from_entity_props():
    """Typification also copies entity.props (post-constructor set values)."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human(Taro)!nationality(Japan)")
    repl.eval("@%SatolikePerson %(@sato)")
    td = repl.doc.typedefs["SatolikePerson"]
    assert str(td.props["name"]) == "Taro"
    assert str(td.props["nationality"]) == "Japan"


def test_typification_no_parent_chain():
    """Typification typedef has no parent (props are flattened, not chain-walked)."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human(Taro)")
    repl.eval("@%SatolikePerson %(@sato)")
    td = repl.doc.typedefs["SatolikePerson"]
    assert td.parent is None


def test_typification_with_extra_class_props():
    """@%T %(@var)!extra(val) adds extra class props on top of typification."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human(Taro)")
    repl.eval("@%SatolikePerson %(@sato)!role(admin)")
    td = repl.doc.typedefs["SatolikePerson"]
    assert str(td.props["name"]) == "Taro"
    assert str(td.props["role"]) == "admin"


def test_typification_pass3_ordering():
    """Typification typedef defined BEFORE the source variable still works (Pass 3)."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    # Define the typification typedef BEFORE the source variable — same eval call
    src = "@%SatolikePerson %(@sato)\n@@sato %Human(Taro)"
    repl.eval(src)
    td = repl.doc.typedefs.get("SatolikePerson")
    assert td is not None
    assert str(td.props["name"]) == "Taro"


# ---------------------------------------------------------------------------
# 2. Unsetter in typification: !-(keys)
# ---------------------------------------------------------------------------

def test_unsetter_removes_key_from_typification():
    """@%T %(@var)!-(name) excludes 'name' from typification props."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@%AnonymousPerson %(@sato)!-(name)")
    td = repl.doc.typedefs["AnonymousPerson"]
    assert "name" not in td.props
    assert str(td.props["job"]) == "Engineer"


def test_unsetter_removes_multiple_keys():
    """@%T %(@var)!-(key1 key2) excludes multiple keys."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job :age)")
    repl.eval("@@sato %Human(:name Taro :job Engineer :age 30)")
    repl.eval("@%Stripped %(@sato)!-(name age)")
    td = repl.doc.typedefs["Stripped"]
    assert "name" not in td.props
    assert "age" not in td.props
    assert str(td.props["job"]) == "Engineer"


def test_unsetter_with_constructor_override():
    """Excluded key becomes a normal constructor param (not from typedef.props)."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@%AnonymousPerson %(@sato)!-(name)")
    repl.eval("@@person2 %AnonymousPerson(Alice)")
    # positional arg fills name (first member)
    assert str(repl.eval("@person2.name")) == "Alice"
    # job comes from typedef.props
    assert str(repl.eval("@person2.job")) == "Engineer"


# ---------------------------------------------------------------------------
# 3. Instance-level unsetter: @var!-(keys)
# ---------------------------------------------------------------------------

def test_instance_unsetter_removes_prop():
    """@var!-(key) removes a property from the instance."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human(Taro)!nationality(Japan)")
    repl.eval("@sato!-(nationality)")
    val = repl.eval("@sato.nationality")
    assert isinstance(val, type(Empty))


def test_instance_unsetter_removes_field():
    """@var!-(key) also removes a field from the instance."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@sato!-(job)")
    val = repl.eval("@sato.job")
    assert isinstance(val, type(Empty))


def test_instance_unsetter_multiple_keys():
    """@var!-(k1 k2) removes multiple properties."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human(Taro)!nationality(Japan)!job(Engineer)")
    repl.eval("@sato!-(nationality job)")
    assert isinstance(repl.eval("@sato.nationality"), type(Empty))
    assert isinstance(repl.eval("@sato.job"), type(Empty))
    assert str(repl.eval("@sato.name")) == "Taro"  # unaffected


def test_instance_unsetter_chained_with_setter():
    """Chain: @var!-(old)!new(val) removes then adds."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human(Taro)!role(admin)")
    repl.eval("@sato!-(role)!role(user)")
    assert str(repl.eval("@sato.role")) == "user"


# ---------------------------------------------------------------------------
# 4. Inline typification instantiation: %(@var)(args)
# ---------------------------------------------------------------------------

def test_inline_typification_instantiation():
    """Inline %(@var)(args) creates an entity typed from the var."""
    repl = STNRepl()
    repl.eval("@%Human (:name :job)")
    repl.eval("@@sato %Human(Taro Engineer)")
    repl.eval("@@person2 %(@sato)(Hanako)")
    assert str(repl.eval("@person2.name")) == "Hanako"
    assert str(repl.eval("@person2.job")) == "Engineer"  # from typification props


def test_inline_typification_empty_constructor():
    """Inline %(@var)() with empty constructor still gets typedef.props."""
    repl = STNRepl()
    repl.eval("@%Human (:name)")
    repl.eval("@@sato %Human(Taro)!nationality(Japan)")
    repl.eval("@@person2 %(@sato)()")
    assert str(repl.eval("@person2.nationality")) == "Japan"
