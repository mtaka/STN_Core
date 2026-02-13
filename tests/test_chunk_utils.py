"""Tests for stn_core.chunk_utils."""

from stn_core.chunk_utils import atom_to_value, normalize_implicit_dict
from stn_core.model import VDate, VDict, VList, VNumber, VText


class TestAtomToValue:
    def test_integer(self):
        assert atom_to_value("42") == VNumber(42.0)

    def test_negative_number(self):
        assert atom_to_value("-5") == VNumber(-5.0)

    def test_float(self):
        assert atom_to_value("3.14") == VNumber(3.14)

    def test_plain_text(self):
        assert atom_to_value("hello") == VText("hello")

    def test_literal_brackets_stripped(self):
        assert atom_to_value("[Some Text]") == VText("Some Text")

    def test_not_a_number(self):
        assert atom_to_value("12abc") == VText("12abc")

    def test_date_in_literal(self):
        assert atom_to_value("[2024-01-15]") == VDate("2024-01-15")

    def test_non_date_literal(self):
        assert atom_to_value("[hello world]") == VText("hello world")


class TestNormalizeImplicitDict:
    def test_basic(self):
        result = normalize_implicit_dict([":x", "10", "20", ":y", "30"])
        assert isinstance(result, VDict)
        assert result.entries["x"] == VList([VNumber(10), VNumber(20)])
        assert result.entries["y"] == VNumber(30)

    def test_single_values(self):
        result = normalize_implicit_dict([":a", "1", ":b", "2"])
        assert result.entries["a"] == VNumber(1)
        assert result.entries["b"] == VNumber(2)

    def test_empty_value(self):
        result = normalize_implicit_dict([":key"])
        assert result.entries["key"] == VText("")

    def test_sigil_separated_format(self):
        """Lexer produces ':' as separate atom from key name."""
        result = normalize_implicit_dict([":", "x", "10", "20", ":", "y", "30"])
        assert isinstance(result, VDict)
        assert result.entries["x"] == VList([VNumber(10), VNumber(20)])
        assert result.entries["y"] == VNumber(30)

    def test_mixed_formats(self):
        """Both sigil-separated and pre-joined should work."""
        result = normalize_implicit_dict([":", "a", "1"])
        assert result.entries["a"] == VNumber(1)
