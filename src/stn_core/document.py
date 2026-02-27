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
        # Not a dataclass field — tracks last result from the most recent merge()
        self._last_result: Value | None = None

    # -- Convenience accessors ------------------------------------------

    @property
    def locals_(self) -> dict[str, Value]:
        return self.environment.locals_

    @property
    def publics(self) -> dict[str, Value]:
        return self.environment.publics

    @property
    def typedefs(self) -> dict[str, TypeDef]:
        return self.environment.typedefs

    @property
    def last_result(self) -> Value | None:
        """The last expression value produced by the most recent merge()."""
        return self._last_result

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
        new_results = _evaluate_into(result, self.environment)
        self.results.extend(new_results)
        self._last_result = new_results[-1] if new_results else None
