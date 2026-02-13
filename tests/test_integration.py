"""Integration tests: stn.parse() → stn_core.evaluate() → Document."""

import stn
from stn_core import Empty, evaluate, VEntity, VNumber, VRef, VText


class TestSpecExample:
    """The primary example from the spec:

    @%Rect (x y w h)
    @#R1 %Rect(10 20 100 50)!id(#01)
    #R1.x
    """

    def test_full_pipeline(self):
        source = "@%Rect (x y w h) ; @#R1 %Rect(10 20 100 50)!id(#01) ; #R1.x"
        doc = evaluate(stn.parse(source).ast)

        # TypeDef registered
        assert "Rect" in doc.typedefs
        assert doc.typedefs["Rect"].params == ["x", "y", "w", "h"]

        # Global var registered
        r1 = doc.globals_["R1"]
        assert isinstance(r1, VEntity)
        assert r1.entity.type_name == "Rect"
        assert r1.entity.fields == {
            "x": VNumber(10),
            "y": VNumber(20),
            "w": VNumber(100),
            "h": VNumber(50),
        }
        assert r1.entity.props == {"id": VRef("01")}

        # Getter result
        assert doc.results == [VNumber(10)]


class TestMultipleGetters:
    def test_access_all_fields(self):
        source = (
            "@%Rect (x y w h) ; "
            "@#R1 %Rect(10 20 100 50) ; "
            "#R1.x ; #R1.y ; #R1.w ; #R1.h"
        )
        doc = evaluate(stn.parse(source).ast)
        assert doc.results == [
            VNumber(10),
            VNumber(20),
            VNumber(100),
            VNumber(50),
        ]


class TestSetterThenGetter:
    def test_prop_getter(self):
        source = (
            "@%Rect (x y w h) ; "
            "@#R1 %Rect(10 20 100 50)!color([red]) ; "
            "#R1.color"
        )
        doc = evaluate(stn.parse(source).ast)
        assert doc.results == [VText("red")]


class TestBatchSetterIntegration:
    def test_batch_then_getter(self):
        source = (
            "@%Pt (x y) ; "
            "@#P1 %Pt(0 0)!+(x 5 y 10) ; "
            "#P1.x ; #P1.y"
        )
        doc = evaluate(stn.parse(source).ast)
        assert doc.results == [VNumber(5), VNumber(10)]


class TestBatchSetterWithKeyFormat:
    def test_batch_set_with_colon_keys(self):
        source = (
            "@%Pt (x y) ; "
            "@#P1 %Pt(0 0)!+(:x 5 :y 10) ; "
            "#P1.x ; #P1.y"
        )
        doc = evaluate(stn.parse(source).ast)
        assert doc.results == [VNumber(5), VNumber(10)]


class TestLocalVarDefIntegration:
    def test_local_def_and_ref(self):
        source = "@val (42) ; @val"
        doc = evaluate(stn.parse(source).ast)
        assert doc.results == [VNumber(42)]

    def test_local_def_list(self):
        from stn_core import VList
        source = "@items (a b c)"
        doc = evaluate(stn.parse(source).ast)
        val = doc.locals_["items"]
        assert isinstance(val, VList)
        assert len(val.items) == 3


class TestVRefIntegration:
    def test_setter_with_ref_value(self):
        source = "@%Pt (x y) ; @#P1 %Pt(1 2)!tag(#myid)"
        doc = evaluate(stn.parse(source).ast)
        entity = doc.globals_["P1"]
        assert isinstance(entity, VEntity)
        assert entity.entity.props["tag"] == VRef("myid")


class TestVDateIntegration:
    def test_date_in_literal(self):
        from stn_core import VDate
        source = "@born ([2024-01-15])"
        doc = evaluate(stn.parse(source).ast)
        assert doc.locals_["born"] == VDate("2024-01-15")


class TestEmptyDocument:
    def test_empty_source(self):
        doc = evaluate(stn.parse("").ast)
        assert doc.results == []
        assert doc.globals_ == {}
        assert doc.typedefs == {}
