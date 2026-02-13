"""Tests for stn_core.environment."""

from stn_core.environment import Environment, _coerce
from stn_core.model import (
    Empty,
    EnumKind,
    PrimitiveKind,
    TypeDef,
    VDate,
    VEnum,
    VNumber,
    VText,
)


class TestCoerce:
    def test_number(self):
        assert _coerce("42", PrimitiveKind.Number) == VNumber(42)

    def test_number_invalid(self):
        assert _coerce("abc", PrimitiveKind.Number) == VText("abc")

    def test_date(self):
        assert _coerce("2024-01-15", PrimitiveKind.Date) == VDate("2024-01-15")

    def test_date_literal(self):
        assert _coerce("[2024-01-15]", PrimitiveKind.Date) == VDate("2024-01-15")

    def test_enum(self):
        kind = EnumKind(choices=["active", "inactive"])
        result = _coerce("active", kind)
        assert isinstance(result, VEnum)
        assert result.value == "active"
        assert result.choices == ["active", "inactive"]

    def test_text(self):
        assert _coerce("hello", PrimitiveKind.Text) == VText("hello")


class TestEnvironment:
    def test_global_roundtrip(self):
        env = Environment()
        env.set_global("x", VNumber(10))
        assert env.get_global("x") == VNumber(10)

    def test_local_roundtrip(self):
        env = Environment()
        env.set_local("y", VText("hello"))
        assert env.get_local("y") == VText("hello")

    def test_undefined_returns_empty(self):
        env = Environment()
        assert env.get_global("nope") is Empty
        assert env.get_local("nope") is Empty

    def test_create_entity_with_typedef(self):
        env = Environment()
        env.register_typedef(TypeDef(name="Pt", params=["x", "y"]))
        entity = env.create_entity("Pt", ["10", "20"])
        assert entity.fields["x"] == VNumber(10)
        assert entity.fields["y"] == VNumber(20)

    def test_create_entity_without_typedef(self):
        env = Environment()
        entity = env.create_entity("Unknown", ["a", "b"])
        assert entity.fields["_0"] == VText("a")
        assert entity.fields["_1"] == VText("b")

    def test_create_entity_missing_args(self):
        env = Environment()
        env.register_typedef(TypeDef(name="Pt", params=["x", "y"]))
        entity = env.create_entity("Pt", ["10"])
        assert entity.fields["x"] == VNumber(10)
        assert entity.fields["y"] is Empty
