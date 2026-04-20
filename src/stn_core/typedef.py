"""TypeDef and MemberDef for STN Core."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemberDef:
    name: str
    kind: str  # "text"|"number"|"float"|"date"|"datetime"|"bool"|"enum"|"sobject"|typename
    choices: list[str] = field(default_factory=list)  # for enum
    multi: bool = False  # * means multiple values


@dataclass
class TypeDef:
    name: str  # "" if anonymous
    members: list[MemberDef]
    parent: "TypeDef | None" = None
    props: dict[str, "object"] = field(default_factory=dict)  # class-level properties
    reserved: dict[str, object] = field(default_factory=dict)
