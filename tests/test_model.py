"""Tests for stn_core.model."""

from stn_core.model import (
    Empty,
    EnumKind,
    Entity,
    PrimitiveKind,
    TypeDef,
    VDate,
    VDict,
    VEntity,
    VEnum,
    VList,
    VNumber,
    VText,
    _EmptyType,
)


class TestEmpty:
    def test_singleton(self):
        assert Empty is _EmptyType()

    def test_falsy(self):
        assert not Empty

    def test_repr(self):
        assert repr(Empty) == "Empty"


class TestTypeDef:
    def test_default_kinds(self):
        td = TypeDef(name="Rect", params=["x", "y", "w", "h"])
        assert len(td.kinds) == 4
        assert all(k == PrimitiveKind.Text for k in td.kinds)

    def test_explicit_kinds(self):
        td = TypeDef(
            name="Pt",
            params=["x", "y"],
            kinds=[PrimitiveKind.Number, PrimitiveKind.Number],
        )
        assert td.kinds == [PrimitiveKind.Number, PrimitiveKind.Number]


class TestEntity:
    def test_fields_and_props(self):
        e = Entity(
            type_name="Rect",
            fields={"x": VNumber(10), "y": VNumber(20)},
        )
        assert e.type_name == "Rect"
        assert e.fields["x"] == VNumber(10)
        assert e.props == {}


class TestValueTypes:
    def test_vtext(self):
        assert VText("hello").value == "hello"

    def test_vnumber(self):
        assert VNumber(42.0).value == 42.0

    def test_vlist(self):
        lst = VList([VNumber(1), VNumber(2)])
        assert len(lst.items) == 2

    def test_vdict(self):
        d = VDict({"a": VNumber(1)})
        assert d.entries["a"] == VNumber(1)

    def test_ventity(self):
        e = Entity(type_name="T", fields={})
        v = VEntity(e)
        assert v.entity.type_name == "T"

    def test_vdate(self):
        assert VDate("2024-01-15").value == "2024-01-15"

    def test_venum(self):
        v = VEnum("active", ["active", "inactive"])
        assert v.value == "active"
        assert v.choices == ["active", "inactive"]

    def test_enum_kind(self):
        ek = EnumKind(choices=["a", "b", "c"])
        assert ek.choices == ["a", "b", "c"]
