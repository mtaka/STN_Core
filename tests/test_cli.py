"""Tests for CLI helpers: _fmt_inspect, _show_vars, _show_types, _process_line."""

import io
import pytest

from stn_core import STNRepl, Empty, VText, VNumber, VEntity
from stn_core.repl import (
    _fmt_inline,
    _fmt_inspect,
    _show_vars,
    _show_types,
    _process_line,
)


# ---------------------------------------------------------------------------
# _fmt_inline
# ---------------------------------------------------------------------------

def test_fmt_inline_text():
    assert _fmt_inline(VText("hello")) == '"hello"'

def test_fmt_inline_number_int():
    assert _fmt_inline(VNumber(42.0)) == "42"

def test_fmt_inline_number_float():
    assert _fmt_inline(VNumber(3.14)) == "3.14"

def test_fmt_inline_entity():
    e = VEntity(typedef=None, type_name="Person")
    assert "VEntity" in _fmt_inline(e)


# ---------------------------------------------------------------------------
# _fmt_inspect
# ---------------------------------------------------------------------------

def test_fmt_inspect_empty():
    assert _fmt_inspect(Empty) == "Empty"

def test_fmt_inspect_entity_with_fields():
    e = VEntity(typedef=None, type_name="Person",
                fields={"name": VText("Joe"), "age": VNumber(36)})
    out = _fmt_inspect(e)
    assert "VEntity(Person)" in out
    assert '"Joe"' in out
    assert "36" in out

def test_fmt_inspect_entity_no_type():
    e = VEntity(typedef=None, type_name=None, fields={"x": VNumber(1)})
    out = _fmt_inspect(e)
    assert "VEntity {" in out

def test_fmt_inspect_entity_empty_fields():
    e = VEntity(typedef=None, type_name="Empty")
    out = _fmt_inspect(e)
    assert "{}" in out

def test_fmt_inspect_scalar():
    assert _fmt_inspect(VText("hi")) == '"hi"'
    assert _fmt_inspect(VNumber(7)) == "7"


# ---------------------------------------------------------------------------
# _show_vars / _show_types
# ---------------------------------------------------------------------------

def test_show_vars_empty():
    repl = STNRepl()
    buf = io.StringIO()
    _show_vars(repl, buf)
    assert "no variables" in buf.getvalue()

def test_show_vars_with_entries():
    repl = STNRepl()
    repl.eval("@@joe (:name Joe)")
    buf = io.StringIO()
    _show_vars(repl, buf)
    assert "@joe" in buf.getvalue()

def test_show_vars_skips_underscore():
    repl = STNRepl()
    # _DATA is set internally when a data block is present
    repl.eval("@@x 1\n====data====\n---- @sec1\nhello\n")
    buf = io.StringIO()
    _show_vars(repl, buf)
    assert "_DATA" not in buf.getvalue()
    assert "@x" in buf.getvalue()

def test_show_types_empty():
    repl = STNRepl()
    buf = io.StringIO()
    _show_types(repl, buf)
    assert "no types" in buf.getvalue()

def test_show_types_with_entries():
    repl = STNRepl()
    repl.eval("@%Person (:name :age %)")
    buf = io.StringIO()
    _show_types(repl, buf)
    assert "Person" in buf.getvalue()
    assert "name" in buf.getvalue()


# ---------------------------------------------------------------------------
# _process_line
# ---------------------------------------------------------------------------

def test_process_line_quit():
    repl = STNRepl()
    buf = io.StringIO()
    assert _process_line(repl, ":q", buf) is False
    assert _process_line(repl, ":quit", buf) is False

def test_process_line_empty():
    repl = STNRepl()
    buf = io.StringIO()
    assert _process_line(repl, "", buf) is True
    assert _process_line(repl, "   ", buf) is True

def test_process_line_vars():
    repl = STNRepl()
    repl.eval("@@x 1")
    buf = io.StringIO()
    _process_line(repl, ":vars", buf)
    assert "@x" in buf.getvalue()

def test_process_line_types():
    repl = STNRepl()
    repl.eval("@%T (:a)")
    buf = io.StringIO()
    _process_line(repl, ":types", buf)
    assert "T" in buf.getvalue()

def test_process_line_reset():
    repl = STNRepl()
    repl.eval("@@x 1")
    buf = io.StringIO()
    _process_line(repl, ":reset", buf)
    assert "x" not in repl.doc.locals_

def test_process_line_question_mark():
    repl = STNRepl()
    repl.eval("@@x 42")
    buf = io.StringIO()
    _process_line(repl, "? @x", buf)
    assert "42" in buf.getvalue()

def test_process_line_inspect():
    repl = STNRepl()
    repl.eval("@@joe (:name [Joe Smith] :age 36)")
    buf = io.StringIO()
    _process_line(repl, "inspect(@joe)", buf)
    out = buf.getvalue()
    assert "VEntity" in out
    assert "Joe Smith" in out

def test_process_line_inspect_short():
    repl = STNRepl()
    repl.eval("@@joe (:name Joe)")
    buf = io.StringIO()
    _process_line(repl, "i(@joe)", buf)
    assert "VEntity" in buf.getvalue()

def test_process_line_stn_eval():
    repl = STNRepl()
    buf = io.StringIO()
    _process_line(repl, "@@x 99", buf)
    assert "x" in repl.doc.locals_
    assert buf.getvalue() == ""  # no output for definitions


# ---------------------------------------------------------------------------
# Batch execution via _process_line with ?<< (file)
# ---------------------------------------------------------------------------

def test_batch_file(tmp_path):
    from stn_core.repl import _process_line
    stn_file = tmp_path / "input.stn"
    stn_file.write_text(
        "@@taro (:name 山田太郎)\n"
        "@@hanako (:name 山田花子)\n"
        "? @taro.name\n"
        "? @hanako.name\n",
        encoding="utf-8",
    )
    repl = STNRepl()
    buf = io.StringIO()
    _process_line(repl, f"?<< {stn_file}", buf)
    out = buf.getvalue()
    assert "山田太郎" in out
    assert "山田花子" in out


# ---------------------------------------------------------------------------
# Entrypoint smoke test
# ---------------------------------------------------------------------------

def test_main_importable():
    """main() must be importable and callable without error when stdin is empty."""
    from stn_core.repl import main
    import sys
    old_stdin = sys.stdin
    sys.stdin = io.StringIO("")  # EOF immediately
    try:
        main()  # should exit cleanly on EOF
    finally:
        sys.stdin = old_stdin
