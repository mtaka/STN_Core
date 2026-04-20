"""Evaluator: 2-pass evaluation of ParseResult → Document."""

from __future__ import annotations

from stn.tokenizer import Token, TokenType
from stn.nodes import Node

from .document import Document
from .environment import Environment
from .values import Value, VText, VNumber, VEntity, VList, _Empty, Empty
from .typedef import TypeDef, MemberDef
from .sobject import SObject, SEntry, SValue
from .reader import (
    split_statements,
    parse_chunk_tokens,
    parse_member_defs,
    unwrap_literal,
    atom_to_value,
)
from .getter import (
    apply_getter,
    apply_symbol_getter,
    apply_node_getter,
    apply_query_locator,
)
from .setter import apply_setter, apply_batch_setter
from .funcdef import FuncDef


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def evaluate(result) -> Document:
    """Evaluate a ParseResult (from stn.parse) and return a new Document."""
    env = Environment()
    doc = Document(environment=env)
    entries = _evaluate_into(result, env)
    for key, val in entries:
        doc.results.append(val)
        doc._doc_entries.append((key, val))
    return doc


def _evaluate_into(result, env: Environment) -> "list[tuple[str | None, Value]]":
    """Evaluate *result* into an existing *env*, returning (key, value) pairs.

    Used both by ``evaluate()`` and ``Document.merge()``.
    - Type definitions are added/overwritten in *env*.
    - Variable definitions are added/overwritten in *env*.
    - Data blocks are merged into the existing ``_DATA`` entity (or created).
    - Expression results are returned as (top-level-key, value) pairs.
    """
    # Merge _DATA into existing entity, or create a new one
    if result.data:
        existing = env.locals_.get("_DATA")
        if isinstance(existing, VEntity):
            for key, content in result.data.items():
                existing.fields[key] = VText(content)
        else:
            data_entity = VEntity(typedef=None, type_name="_DATA")
            for key, content in result.data.items():
                data_entity.fields[key] = VText(content)
            env.set_local("_DATA", data_entity)

    statements = split_statements(result.ast.items)

    # Pass 1: collect typedefs and funcdefs (skip typification — needs Pass 3)
    typification_stmts: list[list] = []
    for stmt in statements:
        kind = _classify(stmt)
        if kind == "typedef":
            if _is_typification_typedef(stmt):
                typification_stmts.append(stmt)
            else:
                _eval_typedef(stmt, env)
        elif kind == "funcdef":
            _eval_funcdef(stmt, env)

    # Pass 2: evaluate all statements
    new_results: list[tuple[str | None, Value]] = []
    for stmt in statements:
        kind = _classify(stmt)
        if kind in ("local_def", "public_def", "typedef", "funcdef"):
            _eval_stmt(stmt, kind, env)  # side effects only (already done in pass 1)
            continue

        if kind == "expr":
            top_key, rhs_items = _extract_top_key(stmt)
            val, consumed = _eval_rhs_n(rhs_items, env)
            val = _eval_chain(val, rhs_items, consumed, env)
        else:
            # local_ref / symbol_ref / symbol_locator
            top_key = None
            val = _eval_stmt(stmt, kind, env)

        new_results.append((top_key, val))

    # Pass 3: typification typedefs (deferred — depend on @@vars from Pass 2)
    for stmt in typification_stmts:
        _eval_typedef(stmt, env)

    return new_results


def _extract_top_key(items: list) -> "tuple[str | None, list]":
    """If *items* starts with ':name', return (name, rest). Else (None, items)."""
    if (
        len(items) >= 2
        and isinstance(items[0], Token)
        and items[0].type == TokenType.SIGIL
        and items[0].value == ":"
        and items[0].word_head
        and not items[0].word_tail
        and isinstance(items[1], Token)
        and items[1].type == TokenType.ATOM
        and not items[1].word_head
    ):
        return items[1].value, items[2:]
    return None, items


# ---------------------------------------------------------------------------
# Statement classification
# ---------------------------------------------------------------------------

def _classify(items: list) -> str:
    """Classify a statement by its leading tokens.

    Returns one of:
        'local_def'  — @@name ...
        'public_def' — @#name ...
        'typedef'    — @%Name ...
        'local_ref'  — @name ...
        'public_ref' — #name ...
        'expr'       — anything else
    """
    if not items:
        return "expr"

    i0 = items[0]
    if not isinstance(i0, Token) or i0.type != TokenType.SIGIL:
        return "expr"

    if i0.value == "@" and len(items) >= 2:
        i1 = items[1]
        if isinstance(i1, Token) and not i1.word_head:
            if i1.type == TokenType.SIGIL:
                if i1.value == "@":
                    return "local_def"
                if i1.value == "#":
                    return "public_def"
                if i1.value == "%":
                    return "typedef"
                if i1.value == "=":
                    return "funcdef"
            elif i1.type == TokenType.ATOM:
                return "local_ref"

    if i0.value == "#" and len(items) >= 2:
        i1 = items[1]
        if isinstance(i1, Token) and i1.type == TokenType.ATOM and not i1.word_head:
            return "symbol_ref"
        if isinstance(i1, Node) and not i1.word_head:
            return "symbol_locator"  # #(#name) document locator

    return "expr"


# ---------------------------------------------------------------------------
# Per-statement evaluation
# ---------------------------------------------------------------------------

def _eval_stmt(items: list, kind: str, env: Environment) -> Value | None:
    if kind == "local_def":
        _eval_local_def(items, env)
        return None
    if kind == "public_def":
        _eval_public_def(items, env)
        return None
    if kind in ("typedef", "funcdef"):
        # Already done in Pass 1; skip
        return None
    if kind == "local_ref":
        return _eval_local_ref(items, env)
    if kind == "symbol_ref":
        return _eval_symbol_ref(items, env)
    if kind == "symbol_locator":
        return _eval_symbol_locator(items, env)
    # expr
    return _eval_rhs(items, env)


# ---------------------------------------------------------------------------
# Definition statements
# ---------------------------------------------------------------------------

def _eval_local_def(items: list, env: Environment) -> None:
    """@@name value  →  env.locals_[name] = value"""
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    name = name_tok.value
    rhs_items = items[3:]
    val, consumed = _eval_rhs_n(rhs_items, env)
    val = _eval_chain(val, rhs_items, consumed, env)
    env.set_local(name, val)


def _eval_public_def(items: list, env: Environment) -> None:
    """@#name value  →  env.symbols[name] = value"""
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    name = name_tok.value
    rhs_items = items[3:]
    val, consumed = _eval_rhs_n(rhs_items, env)
    val = _eval_chain(val, rhs_items, consumed, env)
    env.set_symbol(name, val)


def _eval_setter_node_value(node: Node, env: Environment) -> Value:
    """Evaluate a setter argument Node to a Value.

    ``(Japan)`` → VText("Japan"),  ``(:x 1 :y 2)`` → VEntity,
    ``(0 5000)`` → VEntity with positional fields.
    """
    entries = parse_chunk_tokens(node.items)
    if not entries:
        return Empty
    if len(entries) == 1 and entries[0].key is None:
        return _svalue_to_value(entries[0].value, None, env)
    return _entries_to_ventity(entries, None, None, env)


def _register_system_functions(env: Environment) -> None:
    """Register all built-in system functions into *env*."""
    from .system_funcs import get_system_functions
    for fd in get_system_functions():
        env.register_function(fd)


def _parse_params(node: Node) -> "list":
    """Parse a function parameter node ($a $b default ...) into list[ParamDef]."""
    from .funcdef import ParamDef
    params = []
    items = node.items
    i = 0
    while i < len(items):
        item = items[i]
        # $varname — new parameter
        if (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == "$"
            and i + 1 < len(items)
            and isinstance(items[i + 1], Token)
            and items[i + 1].type == TokenType.ATOM
            and not items[i + 1].word_head
        ):
            params.append(ParamDef(name=items[i + 1].value))
            i += 2
        elif params:
            # This is a default value for the most recently declared param
            if params[-1].default is None:
                if isinstance(item, Token) and item.type == TokenType.ATOM:
                    params[-1].default = atom_to_value(unwrap_literal(item.value))
                elif isinstance(item, Token) and item.type == TokenType.NUMBER:
                    from .values import VNumber as _VN
                    params[-1].default = _VN(float(item.value))
            i += 1
        else:
            i += 1
    return params


def _eval_funcdef(items: list, env: Environment) -> None:
    """@=funcname($params...) body? → env.functions[name] = FuncDef

    Supported forms:
      @=name($a $b default)        — declaration / override (no body)
      @=[literal name]($a) ( ... ) — user-defined function with body
    """
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    func_name = unwrap_literal(name_tok.value)

    idx = 3
    params = []
    body = None

    # Params node
    if idx < len(items) and isinstance(items[idx], Node) and not items[idx].word_head:
        params = _parse_params(items[idx])
        idx += 1

    # Body node (user-defined) — accept regardless of word_head (may be space-separated)
    if idx < len(items) and isinstance(items[idx], Node):
        body = items[idx]

    from .funcdef import FuncDef as _FD
    if body is not None:
        # User-defined: always register (overrides system function)
        env.register_function(_FD(name=func_name, params=params, body=body))
    elif env.get_function(func_name) is None:
        # Declaration only: register with no impl
        env.register_function(_FD(name=func_name, params=params))


def _parse_func_args(args_node, env: Environment) -> "list[Value]":
    """Evaluate each argument expression in *args_node* using the full evaluator.

    Arguments are separated by any word_head boundary, so ``(@items [ ])``
    yields two values: the VList for ``@items`` and VText(" ").
    """
    if args_node is None:
        return []
    stmts = _split_func_args(args_node.items)
    values = []
    for stmt in stmts:
        if stmt:
            val, consumed = _eval_rhs_n(stmt, env)
            val = _eval_chain(val, stmt, consumed, env)
            values.append(val)
    return values


def _call_function(name: str, args_node, receiver: "Value | None", env: Environment) -> Value:
    """Execute function *name* with args from *args_node* (and optional *receiver*)."""
    fd = env.get_function(name)
    if fd is None:
        return Empty

    arg_values: list[Value] = [receiver] if receiver is not None else []
    arg_values.extend(_parse_func_args(args_node, env))

    # Bind params
    scope: dict[str, Value] = {}
    for idx, param in enumerate(fd.params):
        if idx < len(arg_values):
            scope[param.name] = arg_values[idx]
        elif param.default is not None:
            scope[param.name] = param.default
        else:
            scope[param.name] = Empty

    # Execute
    if fd.impl is not None:
        call_args = [scope.get(p.name, Empty) for p in fd.params]
        try:
            return fd.impl(*call_args)
        except Exception:
            return Empty

    if fd.body is not None:
        return _eval_func_body(fd.body, scope, env)

    return Empty


def _eval_func_body(body_node, scope: "dict[str, Value]", env: Environment) -> Value:
    """Evaluate a user-defined function body with local scope."""
    env.push_scope(scope)
    try:
        stmts = _split_body_stmts(body_node.items)
        return_val: Value = Empty

        for stmt in stmts:
            if not stmt:
                continue
            s0 = stmt[0]

            # $var value — local variable assignment
            if (
                isinstance(s0, Token)
                and s0.type == TokenType.SIGIL
                and s0.value == "$"
                and len(stmt) >= 2
                and isinstance(stmt[1], Token)
                and stmt[1].type == TokenType.ATOM
                and not stmt[1].word_head
            ):
                var_name = stmt[1].value
                val, consumed = _eval_rhs_n(stmt[2:], env)
                val = _eval_chain(val, stmt[2:], consumed, env)
                env.set_scope_var(var_name, val)
                continue

            # =(expr) — explicit return value (= followed directly by Node)
            if (
                isinstance(s0, Token)
                and s0.type == TokenType.SIGIL
                and s0.value == "="
                and len(stmt) >= 2
                and isinstance(stmt[1], Node)
                and not stmt[1].word_head
            ):
                return_val = _eval_return_node(stmt[1], env)
                continue

            # Regular expression — evaluate and keep as implicit return
            val, consumed = _eval_rhs_n(stmt, env)
            val = _eval_chain(val, stmt, consumed, env)
            return_val = val

        return return_val
    finally:
        env.pop_scope()


def _split_func_args(items: list) -> "list[list]":
    """Split function argument items into per-argument lists.

    Splits on *any* token/Node with ``word_head=True``, so space-separated
    argument tokens each become their own argument expression.
    Used by ``_parse_func_args``.
    """
    if not items:
        return []
    stmts: list[list] = []
    current: list = []
    for item in items:
        is_head = (isinstance(item, Token) and item.word_head) or (
            isinstance(item, Node) and item.word_head
        )
        if is_head and current:
            stmts.append(current)
            current = []
        current.append(item)
    if current:
        stmts.append(current)
    return stmts


def _split_body_stmts(items: list) -> "list[list]":
    """Split function body items into mini-statements.

    A new statement starts only when a ``$``, ``=``, ``@``, or ``#`` SIGIL token
    appears with ``word_head=True``.  Other word_head tokens (e.g. ``[value]``
    as a default value after ``$var``) remain part of the current statement,
    so ``$x [default]`` is parsed as a single assignment.
    Used by ``_eval_func_body``.
    """
    if not items:
        return []
    stmts: list[list] = []
    current: list = []
    for item in items:
        is_stmt_start = (
            isinstance(item, Token)
            and item.word_head
            and item.type == TokenType.SIGIL
            and item.value in ("$", "=", "@", "#")
        )
        if is_stmt_start and current:
            stmts.append(current)
            current = []
        current.append(item)
    if current:
        stmts.append(current)
    return stmts


def _eval_return_node(node, env: Environment) -> Value:
    """Evaluate =(node) — creates VEntity for keyed entries, else VList/single Value."""
    entries = parse_chunk_tokens(node.items)
    if not entries:
        return Empty
    has_keys = any(e.key is not None for e in entries)
    if has_keys:
        return _entries_to_ventity(entries, None, None, env)
    values = [_svalue_to_value(e.value, None, env) for e in entries]
    if len(values) == 1:
        return values[0]
    return VList(values)


def _extract_at_name(node: Node) -> "str | None":
    """Extract local var name from an (@name) node."""
    items = node.items
    if (
        len(items) >= 2
        and isinstance(items[0], Token)
        and items[0].type == TokenType.SIGIL
        and items[0].value == "@"
        and isinstance(items[1], Token)
        and items[1].type == TokenType.ATOM
        and not items[1].word_head
    ):
        return items[1].value
    return None


def _typify_var(var_name: str, env: Environment) -> "TypeDef | None":
    """Create a TypeDef from a variable's properties (typification).

    All entity fields (non-auto-named) and props are flattened into td.props.
    The entity's typedef members are inherited for constructor support.
    """
    entity = env.get_local(var_name)
    if not isinstance(entity, VEntity):
        return None
    members: list[MemberDef] = []
    if entity.typedef:
        members = list(entity.typedef.members)
    td = TypeDef(name=f"_typify_{var_name}", members=members)
    for k, v in entity.fields.items():
        if not k.startswith("_"):
            td.props[k] = v
    for k, v in entity.props.items():
        td.props[k] = v
    return td


def _is_typification_typedef(stmt: list) -> bool:
    """Return True if stmt is @%Name %(@var) — a typification typedef."""
    if len(stmt) < 5:
        return False
    rhs = stmt[3:]
    if not (
        len(rhs) >= 2
        and isinstance(rhs[0], Token)
        and rhs[0].type == TokenType.SIGIL
        and rhs[0].value == "%"
        and rhs[0].word_head
        and isinstance(rhs[1], Node)
        and not rhs[1].word_head
    ):
        return False
    return _extract_at_name(rhs[1]) is not None


def _eval_typedef(items: list, env: Environment) -> None:
    """@%Name ... → env.typedefs[Name] = TypeDef

    Supported forms:
      @%Name (:members...)                        — simple member definition
      @%Name %Parent                               — extend parent, inherit constructor
      @%Name %Parent!prop(val)...                  — extend + class props
      @%Name %Parent!prop(val)...(:members)        — extend + class props + constructor override
      @%Name %(@var)                               — typification: create type from variable
      @%Name %(@var)!-(key ...)                    — typification with exclusions
      @%Name %(@var)!prop(val)...                  — typification + extra class props
    """
    if len(items) < 3:
        return
    name_tok = items[2]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return
    type_name = name_tok.value

    rhs = items[3:]
    i = 0

    # Detect parent type or typification source
    parent_td: TypeDef | None = None
    is_typification = False

    if i < len(rhs) and isinstance(rhs[i], Token) and rhs[i].type == TokenType.SIGIL and rhs[i].value == "%" and rhs[i].word_head:
        # Typification: %(@var) — % followed by a glued Node
        if (
            i + 1 < len(rhs)
            and isinstance(rhs[i + 1], Node)
            and not rhs[i + 1].word_head
        ):
            var_name = _extract_at_name(rhs[i + 1])
            if var_name is not None:
                parent_td = _typify_var(var_name, env)
                is_typification = True
                i += 2
        # Regular named parent: %ParentName — % followed by a glued ATOM
        elif (
            i + 1 < len(rhs)
            and isinstance(rhs[i + 1], Token)
            and rhs[i + 1].type == TokenType.ATOM
            and not rhs[i + 1].word_head
        ):
            parent_name = rhs[i + 1].value
            parent_td = env.resolve_typedef(parent_name)
            i += 2

    # Collect class-level props and exclusion keys from setter chains
    td_props: dict[str, Value] = {}
    td_exclude: set[str] = set()
    while i < len(rhs):
        item = rhs[i]
        # !-(keys) unsetter
        if (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == "!"
            and not item.word_head
            and i + 1 < len(rhs)
            and isinstance(rhs[i + 1], Token)
            and rhs[i + 1].type == TokenType.SIGIL
            and rhs[i + 1].value == "-"
            and not rhs[i + 1].word_head
        ):
            if i + 2 < len(rhs) and isinstance(rhs[i + 2], Node) and not rhs[i + 2].word_head:
                for entry in parse_chunk_tokens(rhs[i + 2].items):
                    if entry.key is None and isinstance(entry.value, str):
                        td_exclude.add(entry.value)
                i += 3
            else:
                i += 2
        # !name(val)
        elif (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == "!"
            and not item.word_head
            and i + 2 < len(rhs)
            and isinstance(rhs[i + 1], Token)
            and rhs[i + 1].type == TokenType.ATOM
            and not rhs[i + 1].word_head
            and isinstance(rhs[i + 2], Node)
            and not rhs[i + 2].word_head
        ):
            key = rhs[i + 1].value
            td_props[key] = _eval_setter_node_value(rhs[i + 2], env)
            i += 3
        # !+(batch)
        elif (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == "!"
            and not item.word_head
            and i + 2 < len(rhs)
            and isinstance(rhs[i + 1], Token)
            and rhs[i + 1].type == TokenType.SIGIL
            and rhs[i + 1].value == "+"
            and not rhs[i + 1].word_head
            and isinstance(rhs[i + 2], Node)
            and not rhs[i + 2].word_head
        ):
            for entry in parse_chunk_tokens(rhs[i + 2].items):
                if entry.key is not None:
                    td_props[entry.key] = _svalue_to_value(entry.value, None, env)
            i += 3
        else:
            break

    # Constructor definition (remaining Node = member list or override)
    members: list[MemberDef] = []
    reserved: dict[str, Value] = {}
    if i < len(rhs) and isinstance(rhs[i], Node):
        def_node = rhs[i]
        for entry in parse_chunk_tokens(def_node.items):
            if entry.key == "__":
                if isinstance(entry.value, SObject):
                    reserved["__"] = _entries_to_ventity(entry.value.entries, None, None, env)
                elif isinstance(entry.value, str) and entry.value:
                    reserved["__"] = atom_to_value(entry.value)
                break
        members = [m for m in parse_member_defs(def_node.items) if m.name != "__"]
    elif parent_td is not None:
        members = list(parent_td.members)  # inherit constructor from parent

    # For typification, flatten parent props (minus exclusions) into td.props directly.
    # For named parent, rely on chain walk via td.parent (no copying needed).
    if is_typification and parent_td is not None:
        td = TypeDef(name=type_name, members=members, parent=None)
        for k, v in parent_td.props.items():
            if k not in td_exclude:
                td.props[k] = v
    else:
        td = TypeDef(name=type_name, members=members, parent=parent_td)

    td.props.update(td_props)  # explicit props override inherited
    td.reserved.update(reserved)
    env.register_typedef(td)


# ---------------------------------------------------------------------------
# Reference statements (return a Value)
# ---------------------------------------------------------------------------

def _eval_local_ref(items: list, env: Environment) -> Value:
    """@name [chain...]  →  resolve and apply getters/setters"""
    if len(items) < 2:
        return Empty
    name_tok = items[1]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return Empty
    value: Value = env.get_local(name_tok.value)
    return _eval_chain(value, items, 2, env)


def _eval_symbol_ref(items: list, env: Environment) -> Value:
    """#name [chain...]  →  resolve symbol and apply getters/setters"""
    if len(items) < 2:
        return Empty
    name_tok = items[1]
    if not isinstance(name_tok, Token) or name_tok.type != TokenType.ATOM:
        return Empty
    value: Value = env.get_symbol(name_tok.value)
    return _eval_chain(value, items, 2, env)


def _eval_symbol_locator(items: list, env: Environment) -> Value:
    """#(#name)  →  look up symbol 'name' in env.symbols"""
    if len(items) < 2:
        return Empty
    node = items[1]
    if not isinstance(node, Node):
        return Empty
    sym_name = _extract_symbol_name(node)
    if sym_name is None:
        return Empty
    value = env.get_symbol(sym_name)
    return _eval_chain(value, items, 2, env)


# ---------------------------------------------------------------------------
# RHS expression evaluation
# ---------------------------------------------------------------------------

def _eval_rhs(items: list, env: Environment) -> Value:
    """Evaluate the right-hand side of a definition or a bare expression."""
    val, _ = _eval_rhs_n(items, env)
    return val


def _eval_rhs_n(items: list, env: Environment) -> "tuple[Value, int]":
    """Like _eval_rhs but also returns the number of items consumed.

    Used when a getter/setter chain may follow the initial value.
    """
    if not items:
        return Empty, 0

    i0 = items[0]

    # Anonymous S-object: bare Node
    if isinstance(i0, Node):
        return _node_to_ventity(i0, None, None, env), 1

    if isinstance(i0, Token):
        # Typed instantiation: %TypeName[!pre_setters](args)
        if i0.type == TokenType.SIGIL and i0.value == "%":
            val, consumed = _eval_instantiation(items, 0, env)
            return val, consumed

        # Function call: =funcname(args)
        if (
            i0.type == TokenType.SIGIL
            and i0.value == "="
            and len(items) >= 3
            and isinstance(items[1], Token)
            and items[1].type == TokenType.ATOM
            and not items[1].word_head
            and isinstance(items[2], Node)
            and not items[2].word_head
        ):
            val = _call_function(unwrap_literal(items[1].value), items[2], None, env)
            return val, 3

        # Return-value expression: =(node) — identity/grouping
        if (
            i0.type == TokenType.SIGIL
            and i0.value == "="
            and len(items) >= 2
            and isinstance(items[1], Node)
            and not items[1].word_head
        ):
            val = _eval_return_node(items[1], env)
            return val, 2

        # Scope variable: $varname
        if (
            i0.type == TokenType.SIGIL
            and i0.value == "$"
            and len(items) >= 2
            and isinstance(items[1], Token)
            and items[1].type == TokenType.ATOM
            and not items[1].word_head
        ):
            return env.get_scope_var(items[1].value), 2

        # Local var reference: @varname (for use in function args, body etc.)
        if (
            i0.type == TokenType.SIGIL
            and i0.value == "@"
            and len(items) >= 2
            and isinstance(items[1], Token)
            and items[1].type == TokenType.ATOM
            and not items[1].word_head
        ):
            return env.get_local(items[1].value), 2

        # Symbol reference: #name
        if (
            i0.type == TokenType.SIGIL
            and i0.value == "#"
            and len(items) >= 2
            and isinstance(items[1], Token)
            and items[1].type == TokenType.ATOM
            and not items[1].word_head
        ):
            return env.get_symbol(items[1].value), 2

        # Simple scalar
        if i0.type == TokenType.ATOM:
            return atom_to_value(unwrap_literal(i0.value)), 1
        if i0.type == TokenType.NUMBER:
            return VNumber(float(i0.value)), 1

    return Empty, 0


def _eval_instantiation(items: list, start: int, env: Environment) -> "tuple[Value, int]":
    """Evaluate %TypeName[!pre_setters](args) starting at *start*.

    Returns ``(entity, items_consumed_from_start)``.

    Pre-constructor ``!setter(val)`` values are stored in ``entity.fields``
    so they take precedence over later ``!setter`` calls (which go to
    ``entity.props``).  This gives class-variable / constant semantics.
    """
    i = start + 1  # skip %

    # Optional glued type name OR typification var %(@var)
    type_name: str | None = None
    td: TypeDef | None = None
    if i < len(items):
        nxt = items[i]
        if isinstance(nxt, Token) and nxt.type == TokenType.ATOM and not nxt.word_head:
            type_name = nxt.value
            td = env.resolve_typedef(type_name)
            i += 1
        elif isinstance(nxt, Node) and not nxt.word_head:
            var_name = _extract_at_name(nxt)
            if var_name is not None:
                type_name = f"_typify_{var_name}"
                td = _typify_var(var_name, env)
                i += 1

    # Pre-constructor !setter chains → class-level props
    pre_props: dict[str, Value] = {}
    while i < len(items):
        item = items[i]
        # !name(val)
        if (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == "!"
            and not item.word_head
            and i + 2 < len(items)
            and isinstance(items[i + 1], Token)
            and items[i + 1].type == TokenType.ATOM
            and not items[i + 1].word_head
            and isinstance(items[i + 2], Node)
            and not items[i + 2].word_head
        ):
            key = items[i + 1].value
            pre_props[key] = _eval_setter_node_value(items[i + 2], env)
            i += 3
        # !+(batch)
        elif (
            isinstance(item, Token)
            and item.type == TokenType.SIGIL
            and item.value == "!"
            and not item.word_head
            and i + 2 < len(items)
            and isinstance(items[i + 1], Token)
            and items[i + 1].type == TokenType.SIGIL
            and items[i + 1].value == "+"
            and not items[i + 1].word_head
            and isinstance(items[i + 2], Node)
            and not items[i + 2].word_head
        ):
            for entry in parse_chunk_tokens(items[i + 2].items):
                if entry.key is not None:
                    pre_props[entry.key] = _svalue_to_value(entry.value, None, env)
            i += 3
        else:
            break

    # Constructor Node (glued to chain)
    entity: VEntity
    if i < len(items) and isinstance(items[i], Node) and not items[i].word_head:
        entity = _node_to_ventity(items[i], type_name, td, env)
        i += 1
    else:
        entity = VEntity(typedef=td, type_name=type_name)
        if td and td.reserved:
            entity.reserved.update(td.reserved)

    # Pre-props → fields (checked before props → constant semantics)
    for k, v in pre_props.items():
        if k not in entity.fields:
            entity.fields[k] = v

    return entity, i - start


# ---------------------------------------------------------------------------
# Node → VEntity
# ---------------------------------------------------------------------------

def _node_to_ventity(
    node: Node,
    type_name: str | None,
    td: TypeDef | None,
    env: Environment,
) -> VEntity:
    entity = VEntity(typedef=td, type_name=type_name)

    # Inherit reserved from TypeDef (cannot be overridden by instance data)
    if td and td.reserved:
        entity.reserved.update(td.reserved)

    entries = parse_chunk_tokens(node.items)

    has_keys = any(e.key is not None for e in entries)

    if has_keys:
        for entry in entries:
            if entry.key == "__":
                # Only set if NOT already inherited from TypeDef (non-overridable)
                if "__" not in entity.reserved:
                    if isinstance(entry.value, SObject):
                        entity.reserved["__"] = _entries_to_ventity(
                            entry.value.entries, None, None, env
                        )
                continue
            if entry.key is not None:
                member = _find_member(td, entry.key) if td else None
                entity.fields[entry.key] = _svalue_to_value(entry.value, member, env)
    else:
        # Positional args
        if td:
            non_reserved = [m for m in td.members if m.name != "__"]
            for idx, member in enumerate(non_reserved):
                if idx < len(entries):
                    entity.fields[member.name] = _svalue_to_value(
                        entries[idx].value, member, env
                    )
                # else: omit — allows typedef.props lookup for missing constructor args
        else:
            for idx, entry in enumerate(entries):
                entity.fields[f"_{idx}"] = _svalue_to_value(entry.value, None, env)

    return entity


def _find_member(td: TypeDef | None, name: str) -> MemberDef | None:
    if td is None:
        return None
    for m in td.members:
        if m.name == name:
            return m
    return None


def _sym_name_from_sentry(sval: "SValue") -> "str | None":
    """Extract symbol name from an SObject representing a (#name) node.

    parse_chunk_tokens converts ``(#name)`` Node items to
    ``SObject([SEntry(None,'#'), SEntry(None,'name')])``.
    """
    if not isinstance(sval, SObject):
        return None
    entries = sval.entries
    if (
        len(entries) >= 2
        and entries[0].key is None
        and entries[0].value == "#"
        and entries[1].key is None
        and isinstance(entries[1].value, str)
    ):
        return entries[1].value
    return None


def _apply_sentry_chain(value: Value, entries: "list[SEntry]", env: Environment) -> Value:
    """Apply setter chain SEntry items to *value*.

    Mirrors the logic in ``_eval_chain`` but operates on SEntry objects
    produced by parse_chunk_tokens, enabling setter chains inside nested ().

    Handles:
        SEntry('!')  SEntry(SObject{#name})            →  !(#name) id setter
        SEntry('!')  SEntry('#')  SEntry(SObject{#n})  →  !#(#name) symbol reg.
        SEntry('!')  SEntry('+')  SEntry(SObject{args}) →  !+(args) batch setter
        SEntry('!')  SEntry('name') SEntry(SObject{})  →  !name(args) named setter
    """
    i = 0
    while i < len(entries):
        entry = entries[i]
        if entry.key is not None or entry.value != "!":
            break
        i += 1
        if i >= len(entries) or entries[i].key is not None:
            break

        nxt = entries[i].value

        # !(#name) — id shortcut setter
        if isinstance(nxt, SObject):
            sym_name = _sym_name_from_sentry(nxt)
            if sym_name is not None:
                value = _apply_id_setter(value, sym_name)
            i += 1
            continue

        if not isinstance(nxt, str):
            break

        # !#(#name) — symbol registration setter
        if nxt == "#":
            i += 1
            if i < len(entries) and entries[i].key is None:
                sym_name = _sym_name_from_sentry(entries[i].value)
                if sym_name is not None:
                    env.set_symbol(sym_name, value)
                i += 1
            continue

        # !+(args) — batch setter: apply to value.props
        if nxt == "+":
            i += 1
            if i < len(entries) and entries[i].key is None and isinstance(entries[i].value, SObject):
                args_entries = entries[i].value.entries
                if isinstance(value, VEntity):
                    for ae in args_entries:
                        if ae.key is not None and isinstance(ae.value, str):
                            from .reader import atom_to_value as _atv
                            value.props[ae.key] = _atv(ae.value)
                i += 1
            continue

        # !name(args) — named setter: set value.props[name]
        if isinstance(nxt, str) and nxt not in ("%", ""):
            name = nxt
            i += 1
            if i < len(entries) and entries[i].key is None and isinstance(entries[i].value, SObject):
                args_entries = entries[i].value.entries
                if isinstance(value, VEntity) and args_entries:
                    ae = args_entries[0]
                    if ae.key is None and isinstance(ae.value, str):
                        from .reader import atom_to_value as _atv
                        value.props[name] = _atv(ae.value)
                i += 1
            continue

        break

    return value


def _try_typed_instantiation(sval: SObject, env: Environment) -> "Value | None":
    """Detect a %TypeName?(args)[setters]* pattern inside an SObject and evaluate it.

    parse_chunk_tokens groups glued ``%TypeName?(Node) setter*`` sequences into
    a single SObject.  The entries layout is:
        SEntry(None,'%')
        SEntry(None,'TypeName')?
        SEntry(None,SObject{args})?
        [setter entries …]
    Evaluate the instantiation and apply any trailing setter chain.
    """
    entries = sval.entries
    if not entries or entries[0].key is not None or entries[0].value != "%":
        return None

    idx = 1
    type_name: str | None = None

    # Optional glued TypeName
    if (
        idx < len(entries)
        and entries[idx].key is None
        and isinstance(entries[idx].value, str)
        and entries[idx].value not in ("%", "")
    ):
        type_name = entries[idx].value
        idx += 1

    # Glued args SObject → evaluate the instantiation
    if idx < len(entries) and entries[idx].key is None and isinstance(entries[idx].value, SObject):
        args_sobj = entries[idx].value
        td = env.resolve_typedef(type_name) if type_name else None
        value: Value = _entries_to_ventity(args_sobj.entries, type_name, td, env)
        # Apply trailing setter chain (!(#id), !#(#name), etc.)
        value = _apply_sentry_chain(value, entries[idx + 1 :], env)
        return value

    # %TypeName with no args → empty entity (+ possible setters)
    if type_name is not None and idx <= len(entries):
        td = env.resolve_typedef(type_name)
        value = VEntity(typedef=td, type_name=type_name)
        value = _apply_sentry_chain(value, entries[idx:], env)
        return value

    return None


def _svalue_to_value(sval: SValue, member: MemberDef | None, env: Environment) -> Value:
    """Convert an SValue to a proper Value, guided by MemberDef if available."""
    if isinstance(sval, str):
        # $varname — scope variable reference
        if sval.startswith("$") and len(sval) > 1:
            return env.get_scope_var(sval[1:])
        if member is None:
            return atom_to_value(sval)
        return _coerce_str(sval, member, env)

    if isinstance(sval, SObject):
        # Priority: detect nested %TypeName(args) typed instantiation.
        # parse_chunk_tokens groups these into a single SObject so we can
        # recognise the pattern here and evaluate it correctly.
        inst = _try_typed_instantiation(sval, env)
        if inst is not None:
            return inst

        if member is not None and member.kind not in (
            "text", "number", "float", "date", "datetime", "bool", "enum", "sobject"
        ):
            sub_td = env.resolve_typedef(member.kind)
            return _entries_to_ventity(sval.entries, member.kind, sub_td, env)
        return _entries_to_ventity(sval.entries, None, None, env)

    if isinstance(sval, list):
        return VList([
            _entries_to_ventity(s.entries, None, None, env)
            if isinstance(s, SObject)
            else Empty
            for s in sval
        ])

    return Empty


def _entries_to_ventity(
    entries: list[SEntry],
    type_name: str | None,
    td: TypeDef | None,
    env: Environment,
) -> VEntity:
    entity = VEntity(typedef=td, type_name=type_name)
    has_keys = any(e.key is not None for e in entries)

    if has_keys:
        for entry in entries:
            if entry.key is not None:
                member = _find_member(td, entry.key) if td else None
                entity.fields[entry.key] = _svalue_to_value(entry.value, member, env)
            else:
                idx = len(entity.fields)
                entity.fields[f"_{idx}"] = _svalue_to_value(entry.value, None, env)
    else:
        # Positional args: map to typedef member names when available,
        # consistent with _node_to_ventity behaviour.
        if td:
            non_reserved = [m for m in td.members if m.name != "__"]
            for idx, entry in enumerate(entries):
                if idx < len(non_reserved):
                    member = non_reserved[idx]
                    entity.fields[member.name] = _svalue_to_value(entry.value, member, env)
                else:
                    entity.fields[f"_{len(entity.fields)}"] = _svalue_to_value(
                        entry.value, None, env
                    )
        else:
            for idx, entry in enumerate(entries):
                entity.fields[f"_{idx}"] = _svalue_to_value(entry.value, None, env)

    return entity


def _coerce_str(raw: str, member: MemberDef, env: Environment) -> Value:
    """Coerce a raw string to the type specified by a MemberDef."""
    from .values import VBool, VEnum, VDate, VNumber, VText
    kind = member.kind

    if kind in ("number", "float"):
        try:
            return VNumber(float(raw))
        except ValueError:
            return VText(raw)

    if kind == "date":
        return VDate(raw)

    if kind == "bool":
        return VBool(raw.lower() in ("true", "1", "yes", "t"))

    if kind == "enum":
        return VEnum(raw, member.choices)

    return atom_to_value(raw)


# ---------------------------------------------------------------------------
# Getter / setter chain evaluation
# ---------------------------------------------------------------------------

def _eval_chain(value: Value, items: list, start: int, env: Environment) -> Value:
    """Walk a getter / setter chain starting at index *start*."""
    i = start
    while i < len(items):
        item = items[i]

        if not isinstance(item, Token):
            break

        # Getter: . ATOM/NUMBER (glued)
        if (
            item.type == TokenType.SIGIL
            and item.value == "."
            and not item.word_head
            and i + 1 < len(items)
        ):
            nxt = items[i + 1]
            # . followed by a glued Node: .(#name) or .(name) or .(N)
            if isinstance(nxt, Node) and not nxt.word_head:
                sym_name = _extract_symbol_name(nxt)
                if sym_name is not None:
                    value = apply_symbol_getter(value, sym_name)
                else:
                    value = apply_node_getter(value, nxt)
                i += 2
                continue
            # . followed by a glued Token: .name or .N
            if isinstance(nxt, Token) and not nxt.word_head:
                value = apply_getter(value, nxt.value)
                i += 2
                continue

        # Query locator: ?(conditions)
        if (
            item.type == TokenType.SIGIL
            and item.value == "?"
            and not item.word_head
            and i + 1 < len(items)
            and isinstance(items[i + 1], Node)
            and not items[i + 1].word_head
        ):
            value = apply_query_locator(value, items[i + 1], env)
            i += 2
            continue

        # Setter: !name(args) or !+(args) or !(#name) or !#(#name)
        if (
            item.type == TokenType.SIGIL
            and item.value == "!"
            and not item.word_head
            and i + 1 < len(items)
        ):
            nxt = items[i + 1]

            # Method call: !=funcname(args) — receiver is first arg
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.SIGIL
                and nxt.value == "="
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Token)
                and items[i + 2].type == TokenType.ATOM
                and not items[i + 2].word_head
                and i + 3 < len(items)
                and isinstance(items[i + 3], Node)
                and not items[i + 3].word_head
            ):
                value = _call_function(unwrap_literal(items[i + 2].value), items[i + 3], value, env)
                i += 4
                continue

            # Batch setter: !+(args)
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.SIGIL
                and nxt.value == "+"
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Node)
                and not items[i + 2].word_head
            ):
                value = apply_batch_setter(value, items[i + 2])
                i += 3
                continue

            # Symbol registration setter: !#(#name)
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.SIGIL
                and nxt.value == "#"
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Node)
                and not items[i + 2].word_head
            ):
                sym_name = _extract_symbol_name(items[i + 2])
                if sym_name is not None:
                    env.set_symbol(sym_name, value)
                i += 3
                continue

            # Unsetter: !-(keys) — remove keys from entity fields/props
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.SIGIL
                and nxt.value == "-"
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Node)
                and not items[i + 2].word_head
            ):
                if isinstance(value, VEntity):
                    for entry in parse_chunk_tokens(items[i + 2].items):
                        if entry.key is None and isinstance(entry.value, str):
                            key = entry.value
                            value.fields.pop(key, None)
                            value.props.pop(key, None)
                i += 3
                continue

            # id shortcut setter: !(#name)
            if isinstance(nxt, Node) and not nxt.word_head:
                sym_name = _extract_symbol_name(nxt)
                if sym_name is not None:
                    value = _apply_id_setter(value, sym_name)
                    i += 2
                    continue

            # Single setter: !name(args)
            if (
                isinstance(nxt, Token)
                and nxt.type == TokenType.ATOM
                and not nxt.word_head
                and i + 2 < len(items)
                and isinstance(items[i + 2], Node)
                and not items[i + 2].word_head
            ):
                value = apply_setter(value, nxt.value, items[i + 2])
                i += 3
                continue

        break

    return value


def _extract_symbol_name(node: Node) -> "str | None":
    """Extract symbol name from a (#name) node. Returns 'name' or None."""
    items = node.items
    if (
        len(items) >= 2
        and isinstance(items[0], Token)
        and items[0].type == TokenType.SIGIL
        and items[0].value == "#"
        and isinstance(items[1], Token)
        and items[1].type == TokenType.ATOM
        and not items[1].word_head
    ):
        return items[1].value
    return None


def _apply_id_setter(value: Value, sym_name: str) -> Value:
    """!(#name) — set __(:id name) on an entity."""
    if not isinstance(value, VEntity):
        return value
    reserved_obj = value.reserved.get("__")
    if reserved_obj is None or not isinstance(reserved_obj, VEntity):
        reserved_obj = VEntity(typedef=None, type_name=None)
        value.reserved["__"] = reserved_obj
    # id is set only once (non-overridable)
    if "id" not in reserved_obj.fields:
        from .values import VText
        reserved_obj.fields["id"] = VText(sym_name)
    return value
