"""STNRepl — incremental REPL for notebook / interactive use.

Also provides the ``stn-repl`` CLI entry point via ``main()``.
"""

from __future__ import annotations

import sys
from typing import IO

from stn import parse

from .document import Document
from .values import Value, VText, VNumber, VDate, VBool, VEnum, VList, VEntity, _Empty, Empty


# ---------------------------------------------------------------------------
# STNRepl class (notebook / programmatic use)
# ---------------------------------------------------------------------------

class STNRepl:
    """Stateful REPL that accumulates variable and type definitions across calls.

    Usage::

        repl = STNRepl()
        repl.eval("@%Person (:name :age %)")
        repl.eval("@@joe %Person(:name [Joe Smith] :age 36)")
        repl.eval("@joe.name")   # → VText("Joe Smith")

        repl.doc.locals_   # all defined variables
        repl.doc.typedefs  # all defined types
        repl.reset()       # clear state
    """

    def __init__(self) -> None:
        self.doc = Document()

    def eval(self, text: str) -> Value | None:
        """Evaluate *text* and merge results into the accumulated Document.

        Returns the last expression value, or ``None`` if the input
        contained only definitions (no expression statements).
        """
        result = parse(text)
        self.doc.merge(result)
        return self.doc.last_result

    def reset(self) -> None:
        """Clear all accumulated state (variables, types, results)."""
        self.doc = Document()


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _fmt_inline(value: Value) -> str:
    """Format a single value for compact one-line display."""
    if isinstance(value, VText):
        return f'"{value.value}"'
    if isinstance(value, (VNumber, VDate, VBool, VEnum)):
        return str(value)
    if isinstance(value, VList):
        return "[" + ", ".join(_fmt_inline(v) for v in value.items) + "]"
    if isinstance(value, VEntity):
        return str(value)
    return repr(value)


def _fmt_inspect(value: Value) -> str:
    """Pretty-print a value for inspect() / i()."""
    if isinstance(value, _Empty):
        return "Empty"

    if isinstance(value, VEntity):
        type_str = f"({value.type_name})" if value.type_name else ""
        all_fields = {**value.fields, **value.props}
        if not all_fields:
            return f"VEntity{type_str} {{}}"
        width = max(len(k) for k in all_fields)
        lines = [f"VEntity{type_str} {{"]
        for k, v in all_fields.items():
            lines.append(f"  {k:<{width}}: {_fmt_inline(v)}")
        lines.append("}")
        return "\n".join(lines)

    if isinstance(value, VList):
        lines = ["VList ["]
        for i, v in enumerate(value.items, 1):
            lines.append(f"  {i}: {_fmt_inline(v)}")
        lines.append("]")
        return "\n".join(lines)

    return _fmt_inline(value)


def _eval_expr(repl: STNRepl, expr: str, dest: IO[str]) -> None:
    """Evaluate *expr* as STN and print the result to *dest*."""
    result = repl.eval(expr)
    if result is not None:
        print(str(result), file=dest)


def _inspect_expr(repl: STNRepl, expr: str, dest: IO[str]) -> None:
    """Evaluate *expr* as STN and pretty-print to *dest*."""
    result = repl.eval(expr)
    if result is not None:
        print(_fmt_inspect(result), file=dest)


def _show_vars(repl: STNRepl, dest: IO[str]) -> None:
    """Print all local variables (skips internal _ prefixed names)."""
    entries = {k: v for k, v in repl.doc.locals_.items() if not k.startswith("_")}
    if not entries:
        print("  (no variables defined)", file=dest)
        return
    width = max(len(k) for k in entries)
    for name, value in entries.items():
        print(f"  @{name:<{width}} : {str(value)}", file=dest)


def _show_types(repl: STNRepl, dest: IO[str]) -> None:
    """Print all defined type names."""
    if not repl.doc.typedefs:
        print("  (no types defined)", file=dest)
        return
    for name in repl.doc.typedefs:
        td = repl.doc.typedefs[name]
        member_names = ", ".join(m.name for m in td.members)
        print(f"  @%{name}  ({member_names})", file=dest)


def _process_line(repl: STNRepl, line: str, dest: IO[str]) -> bool:
    """Process one input line.  Returns False when the session should end."""
    line = line.strip()
    if not line:
        return True

    # ── Exit ──────────────────────────────────────────────────────────────
    if line in (":q", ":quit"):
        return False

    # ── Control commands ──────────────────────────────────────────────────
    if line == ":vars":
        _show_vars(repl, dest)
        return True

    if line == ":types":
        _show_types(repl, dest)
        return True

    if line == ":reset":
        repl.reset()
        return True

    # ── inspect() / i() ───────────────────────────────────────────────────
    for prefix in ("inspect(", "i("):
        if line.startswith(prefix) and line.endswith(")"):
            expr = line[len(prefix):-1].strip()
            _inspect_expr(repl, expr, dest)
            return True

    # ── ? expression ──────────────────────────────────────────────────────
    if line.startswith("? "):
        _eval_expr(repl, line[2:].strip(), dest)
        return True

    # ── Batch file (also usable from _process_line, e.g. in ?<< files) ───
    if line.startswith("?<< "):
        filepath = line[4:].strip()
        try:
            with open(filepath, encoding="utf-8") as fh:
                for file_line in fh:
                    _process_line(repl, file_line.rstrip("\n"), dest)
        except OSError as exc:
            print(f"Error reading '{filepath}': {exc}", file=sys.stderr)
        return True

    # ── Regular STN input ─────────────────────────────────────────────────
    repl.eval(line)
    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Interactive STN shell (``stn-repl`` / ``python -m stn_core.repl``)."""
    repl = STNRepl()
    dest: IO[str] = sys.stdout
    _file: IO[str] | None = None

    print("STN REPL  (:q to quit  |  :vars  :types  :reset  |  ? <expr>  inspect(<expr>))")

    while True:
        try:
            line = input("STN> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue

        if not line:
            continue

        # ── Output redirect: ?>> filepath  /  ?>> ─────────────────────────
        if line.startswith("?>> "):
            filepath = line[4:].strip()
            if _file:
                _file.close()
            try:
                _file = open(filepath, "w", encoding="utf-8")
                dest = _file
            except OSError as exc:
                print(f"Error opening '{filepath}': {exc}", file=sys.stderr)
            continue

        if line == "?>>":
            if _file:
                _file.close()
                _file = None
            dest = sys.stdout
            continue

        # ── Batch execute: ?<< filepath ───────────────────────────────────
        if line.startswith("?<< "):
            filepath = line[4:].strip()
            try:
                with open(filepath, encoding="utf-8") as fh:
                    for file_line in fh:
                        _process_line(repl, file_line.rstrip("\n"), dest)
            except OSError as exc:
                print(f"Error reading '{filepath}': {exc}", file=sys.stderr)
            continue

        # ── All other commands ────────────────────────────────────────────
        if not _process_line(repl, line, dest):
            break

    if _file:
        _file.close()


if __name__ == "__main__":
    main()
