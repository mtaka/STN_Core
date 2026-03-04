"""Document — the final output of STN Core evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .environment import Environment
from .values import Value
from .typedef import TypeDef


@dataclass
class Document:
    """Holds the fully evaluated result of an STN source."""

    environment: Environment = field(default_factory=Environment)
    results: list[Value] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Not dataclass fields — managed manually
        self._last_result: Value | None = None
        self._doc_entries: list[tuple[str | None, Value]] = []

    # -- Convenience accessors ------------------------------------------

    @property
    def locals_(self) -> dict[str, Value]:
        return self.environment.locals_

    @property
    def symbols(self) -> dict[str, Value]:
        return self.environment.symbols

    @property
    def publics(self) -> dict[str, Value]:  # backward compat alias
        return self.environment.symbols

    @property
    def typedefs(self) -> dict[str, TypeDef]:
        return self.environment.typedefs

    @property
    def last_result(self) -> Value | None:
        """The last expression value produced by the most recent merge()."""
        return self._last_result

    # -- Top-level SObject interface ------------------------------------

    def get(self, key: "str | int") -> Value:
        """Access top-level results by name or 1-origin index.

        - str  → first entry whose top-level key matches
        - int  → 1-origin index into all top-level result entries
        - Missing key / out-of-range index → Empty
        """
        from .values import Empty

        if isinstance(key, int):
            if key < 1:
                return Empty
            idx = key - 1
            if idx < len(self._doc_entries):
                return self._doc_entries[idx][1]
            return Empty

        for entry_key, val in self._doc_entries:
            if entry_key == key:
                return val
        return Empty

    # -- Incremental evaluation -----------------------------------------

    def merge(self, result) -> None:
        """Merge a ParseResult into this Document (used by STNRepl).

        - Type definitions (@%) → added/overwritten in typedefs
        - Local variables (@@) → added/overwritten in locals_
        - Public variables (@#) → added/overwritten in publics
        - Data blocks → merged into _DATA entity
        - Expression results → appended to results; last one stored in last_result
        """
        from .evaluator import _evaluate_into
        new_entries = _evaluate_into(result, self.environment)
        for key, val in new_entries:
            self.results.append(val)
            self._doc_entries.append((key, val))
        self._last_result = new_entries[-1][1] if new_entries else None
