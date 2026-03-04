"""Tests for symbols system: @#name, #name, #(#name), !(#name), !#(#name), .(#name), ?()."""

import pytest
from stn_core import STNRepl, Empty, VText, VNumber, VEntity, VList
from stn_core.repl import _show_symbols, _process_line
import io


# ---------------------------------------------------------------------------
# @# symbol definition and # reference
# ---------------------------------------------------------------------------

def test_symbol_def_and_ref():
    """@#name defines a symbol; #name retrieves it."""
    repl = STNRepl()
    repl.eval("@#joe (:name Joe :age 36)")
    val = repl.eval("#joe")
    assert isinstance(val, VEntity)
    assert str(val.fields["name"]) == "Joe"


def test_symbol_ref_undefined():
    """#undefined returns Empty."""
    repl = STNRepl()
    val = repl.eval("#nobody")
    assert val is Empty


def test_symbol_def_scalar():
    """@#x 42 — symbols can hold scalars."""
    repl = STNRepl()
    repl.eval("@#x 42")
    val = repl.eval("#x")
    assert isinstance(val, VNumber)
    assert float(val.value) == 42.0


def test_symbol_def_stores_in_symbols():
    """@# definitions appear in doc.symbols."""
    repl = STNRepl()
    repl.eval("@#foo 1")
    assert "foo" in repl.doc.symbols


def test_symbol_def_not_in_locals():
    """@# definitions must NOT appear in doc.locals_."""
    repl = STNRepl()
    repl.eval("@#bar 2")
    assert "bar" not in repl.doc.locals_


# ---------------------------------------------------------------------------
# !(#name) — id shortcut setter
# ---------------------------------------------------------------------------

def test_id_setter_sets_reserved_id():
    """!(#name) sets __(:id name) in entity.reserved."""
    repl = STNRepl()
    repl.eval("@@e (:x 1)!(#myid)")
    e = repl.doc.locals_["e"]
    assert isinstance(e, VEntity)
    reserved_obj = e.reserved.get("__")
    assert isinstance(reserved_obj, VEntity)
    assert str(reserved_obj.fields["id"]) == "myid"


def test_id_setter_non_overridable():
    """Second !(#name) on same entity does NOT overwrite the id."""
    repl = STNRepl()
    # Chaining two !(#name) setters: second should not overwrite first
    val = repl.eval("(:x 1)!(#first)!(#second)")
    assert isinstance(val, VEntity)
    reserved_obj = val.reserved.get("__")
    assert isinstance(reserved_obj, VEntity)
    assert str(reserved_obj.fields["id"]) == "first"


def test_id_setter_on_empty_is_noop():
    """!(#name) on Empty returns Empty without error."""
    repl = STNRepl()
    val = repl.eval("@undef!(#x)")
    assert val is Empty


def test_id_setter_bare_expr():
    """Bare expr (:v 1)!(#x) applies setter and returns entity."""
    repl = STNRepl()
    val = repl.eval("(:v 1)!(#x)")
    assert isinstance(val, VEntity)
    reserved_obj = val.reserved.get("__")
    assert isinstance(reserved_obj, VEntity)
    assert str(reserved_obj.fields["id"]) == "x"


# ---------------------------------------------------------------------------
# !#(#name) — symbol registration setter
# ---------------------------------------------------------------------------

def test_symbol_reg_setter():
    """@@e (:v 99)!#(#myreg) — !# registers entity in env.symbols."""
    repl = STNRepl()
    repl.eval("@@e (:v 99)!#(#myreg)")
    assert "myreg" in repl.doc.symbols
    assert str(repl.doc.symbols["myreg"].fields["v"]) == "99"


def test_symbol_reg_setter_via_chain():
    """@e!#(#name) — chain on local ref also registers."""
    repl = STNRepl()
    repl.eval("@@e (:z 7)")
    val = repl.eval("@e!#(#zreg)")
    assert "zreg" in repl.doc.symbols
    assert isinstance(val, VEntity)


def test_symbol_reg_setter_bare_expr():
    """Bare expr (:v 5)!#(#sym) registers and returns entity."""
    repl = STNRepl()
    val = repl.eval("(:v 5)!#(#sym)")
    assert "sym" in repl.doc.symbols
    assert isinstance(val, VEntity)


# ---------------------------------------------------------------------------
# #(#name) — document symbol locator
# ---------------------------------------------------------------------------

def test_doc_symbol_locator():
    """#(#name) looks up a symbol registered via @#."""
    repl = STNRepl()
    repl.eval("@#alpha (:label hello)")
    val = repl.eval("#(#alpha)")
    assert isinstance(val, VEntity)
    assert str(val.fields["label"]) == "hello"


def test_doc_symbol_locator_with_chain():
    """#(#name).field chains getter after document locator."""
    repl = STNRepl()
    repl.eval("@#city (:name Tokyo :pop 14000000)")
    val = repl.eval("#(#city).name")
    assert str(val) == "Tokyo"


def test_doc_symbol_locator_undefined():
    """#(#unknown) returns Empty."""
    repl = STNRepl()
    val = repl.eval("#(#unknown)")
    assert val is Empty


# ---------------------------------------------------------------------------
# .(#name) — object symbol getter (id lookup in collection)
# Note: VList is created directly since STN [..] syntax is a text literal
# ---------------------------------------------------------------------------

def _make_entity_with_id(repl: STNRepl, fields_str: str, id_name: str) -> VEntity:
    """Create a VEntity with __(:id id_name) set."""
    val = repl.eval(f"({fields_str})!(#{id_name})")
    assert isinstance(val, VEntity)
    return val


def test_symbol_getter_in_list():
    """.(#id) finds an element in a VList by __(:id)."""
    repl = STNRepl()
    e1 = _make_entity_with_id(repl, ":a 1", "x")
    e2 = _make_entity_with_id(repl, ":b 2", "y")
    repl.doc.environment.locals_["items"] = VList(items=[e1, e2])
    val = repl.eval("@items.(#x)")
    assert isinstance(val, VEntity)
    assert str(val.fields["a"]) == "1"


def test_symbol_getter_in_entity():
    """.(#id) finds a sub-entity in a VEntity by __(:id)."""
    repl = STNRepl()
    e1 = _make_entity_with_id(repl, ":v 10", "f1")
    e2 = _make_entity_with_id(repl, ":v 20", "f2")
    parent = VEntity(typedef=None, type_name=None, fields={"first": e1, "second": e2})
    repl.doc.environment.locals_["parent"] = parent
    val = repl.eval("@parent.(#f2)")
    assert isinstance(val, VEntity)
    assert str(val.fields["v"]) == "20"


def test_symbol_getter_not_found():
    """.(#missing) returns Empty."""
    repl = STNRepl()
    e1 = _make_entity_with_id(repl, ":a 1", "x")
    repl.doc.environment.locals_["items"] = VList(items=[e1])
    val = repl.eval("@items.(#nothere)")
    assert val is Empty


# ---------------------------------------------------------------------------
# ?() — query locator
# Note: VList is created directly since STN [..] syntax is a text literal
# ---------------------------------------------------------------------------

def _make_vlist(repl: STNRepl, *field_strs: str) -> VList:
    """Create a VList of VEntities from field string tuples."""
    items = []
    for fs in field_strs:
        val = repl.eval(f"({fs})")
        items.append(val)
    return VList(items=items)


def test_query_locator_single_match():
    """?(conditions) returns the single matching entity from a VList."""
    repl = STNRepl()
    vlist = _make_vlist(repl, ":name Alice :age 30", ":name Bob :age 25")
    repl.doc.environment.locals_["people"] = vlist
    val = repl.eval("@people?(:name Bob)")
    assert isinstance(val, VEntity)
    assert str(val.fields["name"]) == "Bob"


def test_query_locator_multiple_matches():
    """?(conditions) returns a VList when multiple entities match."""
    repl = STNRepl()
    vlist = _make_vlist(repl, ":type A :v 1", ":type A :v 2", ":type B :v 3")
    repl.doc.environment.locals_["items"] = vlist
    val = repl.eval("@items?(:type A)")
    assert isinstance(val, VList)
    assert len(val.items) == 2


def test_query_locator_no_match():
    """?(conditions) returns Empty when nothing matches."""
    repl = STNRepl()
    vlist = _make_vlist(repl, ":name Alice")
    repl.doc.environment.locals_["items"] = vlist
    val = repl.eval("@items?(:name Charlie)")
    assert val is Empty


def test_query_locator_multi_condition():
    """?(k1 v1 k2 v2) filters on both conditions."""
    repl = STNRepl()
    vlist = _make_vlist(
        repl,
        ":name Alice :age 30",
        ":name Alice :age 25",
        ":name Bob :age 30",
    )
    repl.doc.environment.locals_["items"] = vlist
    val = repl.eval("@items?(:name Alice :age 30)")
    assert isinstance(val, VEntity)
    assert str(val.fields["age"]) == "30"


def test_query_locator_then_getter():
    """?() followed by getter chain works."""
    repl = STNRepl()
    vlist = _make_vlist(repl, ":id 1 :val hello", ":id 2 :val world")
    repl.doc.environment.locals_["data"] = vlist
    val = repl.eval("@data?(:id 2).val")
    assert str(val) == "world"


# ---------------------------------------------------------------------------
# :symbols REPL command
# ---------------------------------------------------------------------------

def test_show_symbols_empty():
    repl = STNRepl()
    buf = io.StringIO()
    _show_symbols(repl, buf)
    assert "no symbols" in buf.getvalue()


def test_show_symbols_with_entries():
    repl = STNRepl()
    repl.eval("@#alpha (:name test)")
    buf = io.StringIO()
    _show_symbols(repl, buf)
    assert "alpha" in buf.getvalue()


def test_process_line_symbols_command():
    repl = STNRepl()
    repl.eval("@#tag 99")
    buf = io.StringIO()
    _process_line(repl, ":symbols", buf)
    assert "tag" in buf.getvalue()
