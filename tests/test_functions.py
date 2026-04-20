"""Tests for STN function system: =func(args), !=method(args), $var, =(...) return."""

import pytest
from stn_core import STNRepl, Empty, VText, VNumber, VBool, VList, VEntity


# ---------------------------------------------------------------------------
# 1. System function calls: =func(args)
# ---------------------------------------------------------------------------

class TestSep:
    def test_split_on_default_whitespace(self):
        repl = STNRepl()
        val = repl.eval("=sep([a b c])")
        assert isinstance(val, VList)
        assert [str(v) for v in val.items] == ["a", "b", "c"]

    def test_split_on_custom_separator(self):
        repl = STNRepl()
        val = repl.eval("=sep([a|b|c] [|])")
        assert [str(v) for v in val.items] == ["a", "b", "c"]

    def test_method_style(self):
        repl = STNRepl()
        repl.eval("@@s [a b c]")
        val = repl.eval("@s!=sep()")
        assert isinstance(val, VList)
        assert [str(v) for v in val.items] == ["a", "b", "c"]

    def test_method_style_with_separator(self):
        repl = STNRepl()
        val = repl.eval("[a|b|c]!=sep([|])")
        assert [str(v) for v in val.items] == ["a", "b", "c"]


class TestCat:
    def test_join_list(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VText("a"), VText("b"), VText("c")])
        val = repl.eval("=cat(@items [ ])")
        assert str(val) == "a b c"

    def test_join_with_default_empty(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VText("x"), VText("y")])
        val = repl.eval("=cat(@items)")
        assert str(val) == "xy"

    def test_roundtrip_sep_cat(self):
        repl = STNRepl()
        val = repl.eval("[a b c]!=sep()!=cat([-])")
        assert str(val) == "a-b-c"


class TestLen:
    def test_string_length(self):
        repl = STNRepl()
        val = repl.eval("=len([hello])")
        assert str(val) == "5"

    def test_list_length(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VText("a"), VText("b"), VText("c")])
        val = repl.eval("=len(@items)")
        assert str(val) == "3"

    def test_method_style(self):
        repl = STNRepl()
        val = repl.eval("[hello]!=len()")
        assert str(val) == "5"


class TestGet:
    def test_get_field(self):
        repl = STNRepl()
        repl.eval("@%Human (:name :job)")
        repl.eval("@@sato %Human(Taro Engineer)")
        val = repl.eval("=get(@sato [name])")
        assert str(val) == "Taro"


# ---------------------------------------------------------------------------
# 2. Comparison / logical functions
# ---------------------------------------------------------------------------

class TestComparisons:
    def test_eq_true(self):
        repl = STNRepl()
        assert str(repl.eval("=eq([hello] [hello])")) == "true"

    def test_eq_false(self):
        repl = STNRepl()
        assert str(repl.eval("=eq([hello] [world])")) == "false"

    def test_gt_true(self):
        repl = STNRepl()
        assert str(repl.eval("=gt(10 5)")) == "true"

    def test_gt_false(self):
        repl = STNRepl()
        assert str(repl.eval("=gt(3 7)")) == "false"

    def test_lt_true(self):
        repl = STNRepl()
        assert str(repl.eval("=lt(3 7)")) == "true"

    def test_eg_equal(self):
        repl = STNRepl()
        assert str(repl.eval("=eg(5 5)")) == "true"

    def test_eg_greater(self):
        repl = STNRepl()
        assert str(repl.eval("=eg(6 5)")) == "true"

    def test_eg_less(self):
        repl = STNRepl()
        assert str(repl.eval("=eg(4 5)")) == "false"

    def test_el_equal(self):
        repl = STNRepl()
        assert str(repl.eval("=el(5 5)")) == "true"

    def test_el_less(self):
        repl = STNRepl()
        assert str(repl.eval("=el(4 5)")) == "true"

    def test_not_false(self):
        repl = STNRepl()
        assert str(repl.eval("=not(false)")) == "true"

    def test_not_true(self):
        repl = STNRepl()
        assert str(repl.eval("=not(true)")) == "false"

    def test_and_both_true(self):
        repl = STNRepl()
        assert str(repl.eval("=and(true true)")) == "true"

    def test_and_one_false(self):
        repl = STNRepl()
        assert str(repl.eval("=and(true false)")) == "false"

    def test_or_one_true(self):
        repl = STNRepl()
        assert str(repl.eval("=or(false true)")) == "true"

    def test_contains_list(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VText("a"), VText("b"), VText("c")])
        assert str(repl.eval("=contains(@items [b])")) == "true"
        assert str(repl.eval("=contains(@items [z])")) == "false"

    def test_contains_string(self):
        repl = STNRepl()
        assert str(repl.eval("=contains([hello world] [world])")) == "true"


# ---------------------------------------------------------------------------
# 3. Aggregation functions
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_size(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VText("a"), VText("b")])
        assert str(repl.eval("=size(@items)")) == "2"

    def test_sum(self):
        repl = STNRepl()
        repl.doc.environment.locals_["nums"] = VList([VNumber(1), VNumber(2), VNumber(3)])
        val = repl.eval("=sum(@nums)")
        assert float(str(val)) == pytest.approx(6.0)

    def test_any_true(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VBool(False), VBool(True)])
        assert str(repl.eval("=any(@items)")) == "true"

    def test_all_true(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VBool(True), VBool(True)])
        assert str(repl.eval("=all(@items)")) == "true"

    def test_all_false(self):
        repl = STNRepl()
        repl.doc.environment.locals_["items"] = VList([VBool(True), VBool(False)])
        assert str(repl.eval("=all(@items)")) == "false"


# ---------------------------------------------------------------------------
# 4. Date/time functions
# ---------------------------------------------------------------------------

class TestDateTime:
    def test_today_returns_date_format(self):
        repl = STNRepl()
        val = repl.eval("=today()")
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", str(val))

    def test_now_returns_datetime_format(self):
        repl = STNRepl()
        val = repl.eval("=now()")
        assert "T" in str(val) or "-" in str(val)

    def test_date_construction(self):
        repl = STNRepl()
        val = repl.eval("=date(2026 4 20)")
        assert str(val) == "2026-04-20"

    def test_ym(self):
        repl = STNRepl()
        val = repl.eval("=ym(2026 4)")
        assert str(val) == "2026-04"

    def test_strptime(self):
        repl = STNRepl()
        val = repl.eval("=strptime([2026/04/20] [%Y/%m/%d])")
        assert str(val) == "2026-04-20"

    def test_strftime(self):
        repl = STNRepl()
        val = repl.eval("=strftime([2026-04-20] [%Y/%m/%d])")
        assert str(val) == "2026/04/20"


# ---------------------------------------------------------------------------
# 5. UUID
# ---------------------------------------------------------------------------

class TestUuid:
    def test_uuid_format(self):
        repl = STNRepl()
        val = repl.eval("=uuid()")
        import re
        assert re.match(r"[0-9a-f-]{36}", str(val))

    def test_uuid_unique(self):
        repl = STNRepl()
        a = str(repl.eval("=uuid()"))
        b = str(repl.eval("=uuid()"))
        assert a != b


# ---------------------------------------------------------------------------
# 6. Method chaining (!=func)
# ---------------------------------------------------------------------------

class TestMethodChain:
    def test_chained_functions(self):
        """[a b c]!=sep()!=cat([-]) → 'a-b-c'"""
        repl = STNRepl()
        val = repl.eval("[a b c]!=sep()!=cat([-])")
        assert str(val) == "a-b-c"

    def test_method_then_getter(self):
        """=sep returns VList; then !=len gives count"""
        repl = STNRepl()
        val = repl.eval("[a b c]!=sep()!=len()")
        assert str(val) == "3"

    def test_function_result_stored(self):
        repl = STNRepl()
        repl.eval("@@items [a b c]!=sep()")
        val = repl.eval("@items")
        assert isinstance(val, VList)
        assert len(val.items) == 3


# ---------------------------------------------------------------------------
# 7. User-defined functions with body
# ---------------------------------------------------------------------------

class TestUserDefinedFunctions:
    def test_simple_identity_return(self):
        """User function that returns its argument."""
        repl = STNRepl()
        repl.eval("@=[identity]($x) (=($x))")
        val = repl.eval("=[identity]([hello])")
        assert str(val) == "hello"

    def test_function_with_local_var(self):
        """User function with $var assignment."""
        repl = STNRepl()
        repl.eval("@=[greet]($name) ($msg [hello]  =($msg))")
        # Note: $msg assignment and =(expr) in body
        val = repl.eval("=[greet]([world])")
        assert str(val) == "hello"

    def test_function_with_scope_var_in_return(self):
        """Function body with intermediate function call as implicit return."""
        repl = STNRepl()
        # body: call =sep($x) — result is last expression, also explicit =(...)
        repl.eval("@=[split_it]($x) (=sep($x))")
        val = repl.eval("=[split_it]([a b])")
        assert isinstance(val, VList)
        assert len(val.items) == 2

    def test_user_function_overrides_system(self):
        """User can define a function with same name to override system."""
        repl = STNRepl()
        repl.eval("@=[len]($s) ([42])")
        val = repl.eval("=[len]([anything])")
        assert str(val) == "42"


# ---------------------------------------------------------------------------
# 8. $var in scope
# ---------------------------------------------------------------------------

class TestScopeVar:
    def test_scope_var_in_function_body(self):
        """$var inside function body resolves to bound param."""
        repl = STNRepl()
        repl.eval("@=[echo]($x) (=($x))")
        val = repl.eval("=[echo]([test])")
        assert str(val) == "test"

    def test_scope_var_in_nested_entity(self):
        """$var used as value inside (:key $var) inside =(...)."""
        repl = STNRepl()
        repl.eval("@=[make_entry]($k $v) (=(:key $k :val $v))")
        val = repl.eval("=[make_entry]([mykey] [myval])")
        assert isinstance(val, VEntity)
        assert str(val.fields["key"]) == "mykey"
        assert str(val.fields["val"]) == "myval"


# ---------------------------------------------------------------------------
# 9. =(...) return value expression (standalone)
# ---------------------------------------------------------------------------

class TestReturnExpr:
    def test_identity_grouping(self):
        """=([hello]) evaluates to VText('hello')."""
        repl = STNRepl()
        val = repl.eval("=([hello])")
        assert str(val) == "hello"

    def test_multiple_items_returns_list(self):
        """=( (:a 1) (:b 2) ) evaluates to VList of two VEntity."""
        repl = STNRepl()
        val = repl.eval("=((:a 1) (:b 2))")
        assert isinstance(val, VList)
        assert len(val.items) == 2
