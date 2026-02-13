"""Tests for stn_core.evaluator."""

import stn
from stn_core import Empty, evaluate, VEntity, VNumber, VRef, VText


class TestTypeDefRegistration:
    def test_register_typedef(self):
        doc = evaluate(stn.parse("@%Rect (x y w h)").ast)
        assert "Rect" in doc.typedefs
        td = doc.typedefs["Rect"]
        assert td.params == ["x", "y", "w", "h"]

    def test_typedef_not_in_results(self):
        doc = evaluate(stn.parse("@%Rect (x y w h)").ast)
        assert doc.results == []


class TestGlobalVarDef:
    def test_simple_entity(self):
        doc = evaluate(stn.parse("@%Rect (x y w h) ; @#R1 %Rect(10 20 100 50)").ast)
        val = doc.globals_["R1"]
        assert isinstance(val, VEntity)
        assert val.entity.fields["x"] == VNumber(10)
        assert val.entity.fields["h"] == VNumber(50)


class TestGetter:
    def test_field_access(self):
        doc = evaluate(
            stn.parse("@%Rect (x y w h) ; @#R1 %Rect(10 20 100 50) ; #R1.x").ast
        )
        assert doc.results == [VNumber(10)]

    def test_getter_missing_field_returns_empty(self):
        doc = evaluate(
            stn.parse("@%Rect (x y) ; @#R1 %Rect(10 20) ; #R1.z").ast
        )
        assert doc.results == [Empty]

    def test_getter_on_undefined_ref_returns_empty(self):
        doc = evaluate(stn.parse("#NONEXISTENT.x").ast)
        assert doc.results == [Empty]


class TestSetter:
    def test_setter_prop(self):
        doc = evaluate(
            stn.parse("@%Rect (x y w h) ; @#R1 %Rect(10 20 100 50)!id(#01)").ast
        )
        entity = doc.globals_["R1"]
        assert isinstance(entity, VEntity)
        assert entity.entity.props["id"] == VRef("01")

    def test_setter_overwrites_field(self):
        doc = evaluate(
            stn.parse("@%Pt (x y) ; @#P1 %Pt(1 2)!x(99)").ast
        )
        entity = doc.globals_["P1"]
        assert isinstance(entity, VEntity)
        assert entity.entity.fields["x"] == VNumber(99)


class TestBatchSetter:
    def test_batch_set(self):
        doc = evaluate(
            stn.parse("@%Pt (x y) ; @#P1 %Pt(0 0)!+(x 10 y 20)").ast
        )
        entity = doc.globals_["P1"]
        assert isinstance(entity, VEntity)
        assert entity.entity.fields["x"] == VNumber(10)
        assert entity.entity.fields["y"] == VNumber(20)


class TestLocalVarDef:
    def test_local_var_simple(self):
        doc = evaluate(stn.parse("@myvar (10 20)").ast)
        from stn_core import VList
        val = doc.locals_["myvar"]
        assert val == VList([VNumber(10), VNumber(20)])

    def test_local_var_single_value(self):
        doc = evaluate(stn.parse("@name (hello)").ast)
        assert doc.locals_["name"] == VText("hello")

    def test_local_ref(self):
        doc = evaluate(stn.parse("@val (42) ; @val").ast)
        assert doc.results == [VNumber(42)]


class TestVRef:
    def test_unresolved_global_in_child(self):
        doc = evaluate(
            stn.parse("@%Pt (x y) ; @#P1 %Pt(1 2)!tag(#unknown)").ast
        )
        entity = doc.globals_["P1"]
        assert isinstance(entity, VEntity)
        assert entity.entity.props["tag"] == VRef("unknown")

    def test_resolved_global_in_child(self):
        doc = evaluate(
            stn.parse("@#A (99) ; @%Pt (x y) ; @#P1 %Pt(1 2)!ref(#A)").ast
        )
        entity = doc.globals_["P1"]
        assert isinstance(entity, VEntity)
        # @#A (99) stores VNumber(99), and !ref(#A) resolves the reference
        assert entity.entity.props["ref"] == VNumber(99)


class TestUndefinedRef:
    def test_undefined_global_returns_empty(self):
        doc = evaluate(stn.parse("#NOPE").ast)
        assert doc.results == [Empty]
