"""Leader / Unit / MetaUnit reconstruction from lexer chunks.

The STN_Lexer produces flat chunk lists where sigils (``#``, ``@``, ``.``,
``!``, ``:``, ``%``) appear as individual atoms.  The lexer also splits new
chunks on ``;``, ``%`` and ``:`` boundaries — so a single STN expression may
span multiple chunks.

This module flattens the chunk list back into a single token stream, detects
real statement boundaries (which correspond to ``;`` in the source), and
reconstitutes structured *Unit* chains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from stn.nodes import Node


# ---------------------------------------------------------------------------
# LeaderType
# ---------------------------------------------------------------------------

class LeaderType(Enum):
    GlobalRef = auto()    # #
    LocalRef = auto()     # @
    Getter = auto()       # .
    Setter = auto()       # !
    Key = auto()          # :
    TypeCall = auto()     # %


_SIGIL_MAP: dict[str, LeaderType] = {
    "#": LeaderType.GlobalRef,
    "@": LeaderType.LocalRef,
    ".": LeaderType.Getter,
    "!": LeaderType.Setter,
    ":": LeaderType.Key,
    "%": LeaderType.TypeCall,
}

_SIGILS = frozenset(_SIGIL_MAP)


# ---------------------------------------------------------------------------
# Unit / Leader
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Leader:
    kind: LeaderType


@dataclass(slots=True)
class Unit:
    """A Leader combined with its operand and optional child node."""
    leader: Leader
    operand: str | None = None
    child: Node | None = None


@dataclass(slots=True)
class Statement:
    """A full statement: optional meta-leader + unit chain.

    ``is_define`` is True when the statement starts with ``@`` meta-leader,
    making this a definition statement.
    """
    units: list[Unit] = field(default_factory=list)
    is_define: bool = False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_chunks_to_statements(node: Node) -> list[Statement]:
    """Walk the root node and build a list of *Statement* objects.

    Chunks are grouped into statements. Since the lexer splits chunks on
    ``;``, ``%`` and ``:`` boundaries, we need to re-group them. The approach:
    flatten all chunks, detect statement starts (``@`` define or standalone
    expression start), and parse unit chains.
    """
    # Flatten all chunks into a single atom stream, inserting a sentinel
    # at each original chunk boundary so we can track child assignment.
    flat: list[str] = []
    chunk_boundaries: list[int] = []  # positions in flat where new chunks start
    for chunk in node.chunks:
        chunk_boundaries.append(len(flat))
        flat.extend(chunk)

    children = node.children
    child_idx = 0

    # Identify statement boundaries by scanning for patterns that start
    # a new statement. We use the chunk boundaries to help: a ';' in the
    # source creates a chunk boundary AND the prior chunk was complete,
    # while '%'/'%:' splits happen mid-expression.
    #
    # Strategy: split into statements at chunk boundaries where the chunk
    # starts with '@' or '#' and is NOT a continuation (not '%' or ':').
    # The first chunk always starts a statement.

    stmt_start_chunks: list[int] = []  # indices into node.chunks
    for ci, boundary_pos in enumerate(chunk_boundaries):
        if ci == 0:
            stmt_start_chunks.append(ci)
            continue
        chunk = node.chunks[ci]
        if not chunk:
            # Empty chunk from trailing ';'
            continue
        first_atom = chunk[0]
        # A new statement starts when:
        # - chunk begins with '@' (define)
        # - chunk begins with '#' (global ref) and previous chunk doesn't
        #   end with a sigil that expects a continuation
        if first_atom == "@":
            stmt_start_chunks.append(ci)
        elif first_atom == "#":
            # Check if previous chunk looks "complete" (not ending with sigil needing operand)
            prev_chunk = node.chunks[ci - 1]
            if prev_chunk and prev_chunk[-1] not in _SIGILS:
                stmt_start_chunks.append(ci)
        # '%' and ':' at chunk start are continuations, not new statements

    # Group chunks into statements
    stmt_chunk_groups: list[list[int]] = []
    for si, start_ci in enumerate(stmt_start_chunks):
        end_ci = stmt_start_chunks[si + 1] if si + 1 < len(stmt_start_chunks) else len(node.chunks)
        stmt_chunk_groups.append(list(range(start_ci, end_ci)))

    # Parse each statement group
    statements: list[Statement] = []
    for group in stmt_chunk_groups:
        # Flatten atoms for this group
        atoms: list[str] = []
        for ci in group:
            atoms.extend(node.chunks[ci])

        stmt, child_idx = _parse_atoms_to_statement(atoms, children, child_idx)
        statements.append(stmt)

    return statements


def _parse_atoms_to_statement(
    atoms: list[str],
    children: list[Node],
    child_idx: int,
) -> tuple[Statement, int]:
    """Parse a flat atom list into a Statement, consuming children as needed."""
    units: list[Unit] = []
    is_define = False
    i = 0

    # Check for meta-leader '@' at start:
    #   @#name → GlobalVarDef, @%Type → TypeDef, @name(...) → LocalVarDef
    #   @name (no child) → local reference (not a define)
    local_def_candidate = False
    if atoms and atoms[0] == "@":
        if len(atoms) > 1 and atoms[1] in ("#", "%", "@"):
            is_define = True
            i = 1  # skip '@', next sigil starts the unit chain
        else:
            # Tentatively mark as define; will be reverted if no child consumed
            local_def_candidate = True
            is_define = True

    while i < len(atoms):
        atom = atoms[i]

        if atom in _SIGIL_MAP:
            leader = Leader(_SIGIL_MAP[atom])

            # Check for '!+' batch setter
            if leader.kind == LeaderType.Setter and i + 1 < len(atoms) and atoms[i + 1] == "+":
                unit = Unit(leader=Leader(LeaderType.Setter), operand="+")
                i += 2
                if child_idx < len(children):
                    unit.child = children[child_idx]
                    child_idx += 1
                units.append(unit)
                continue

            # Consume operand (next non-sigil atom)
            operand = None
            if i + 1 < len(atoms) and atoms[i + 1] not in _SIGILS:
                operand = atoms[i + 1]
                i += 2
            else:
                i += 1

            unit = Unit(leader=leader, operand=operand)

            # Units that consume a child node (parenthesized block)
            if operand is not None and operand != "+":
                should_consume = False
                if leader.kind in (LeaderType.TypeCall, LeaderType.Setter):
                    should_consume = True
                elif leader.kind in (LeaderType.LocalRef, LeaderType.GlobalRef) and is_define and len(units) == 0:
                    # @name (...) or @#name (...) — first unit in a define, only
                    # if no more sigils follow (otherwise the child belongs to
                    # the next unit like %Type)
                    if i >= len(atoms) or atoms[i] not in _SIGILS:
                        should_consume = True
                if should_consume and child_idx < len(children):
                    unit.child = children[child_idx]
                    child_idx += 1

            units.append(unit)
        else:
            # Bare atom — skip (shouldn't appear at top level normally)
            i += 1

    # If this was a local_def_candidate but no child was consumed,
    # it's a local reference expression, not a definition.
    if local_def_candidate and units and units[0].child is None:
        is_define = False

    return Statement(units=units, is_define=is_define), child_idx
