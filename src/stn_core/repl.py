"""STNRepl — incremental REPL for notebook / interactive use."""

from __future__ import annotations

from stn import parse

from .document import Document
from .values import Value


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
