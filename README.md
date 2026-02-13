# STN Core

Structural evaluation engine for STN AST.

STN Core takes the AST produced by [STN Lexer](../STN_lexer) and reconstructs it into a typed, evaluated **Document** — resolving type definitions, variable bindings, entity creation, and getter/setter operations.

## Installation

```
pip install -e .
```

Requires `stn-lexer` as a dependency (resolved via path dependency in `pyproject.toml`).

## Example

Input (STN):

```
@%Person (:name :age % :sex %s(F M))
@@taro %Person(:name 山田太郎 :age 36 :sex M)
@taro.name
```

Code:

```python
from stn import parse
from stn_core import evaluate

doc = evaluate(parse(text).ast)

doc.typedefs["Person"]      # TypeDef(name="Person", params=["name","age","sex"], ...)
doc.locals_["taro"]         # VEntity(Person { name: "山田太郎", age: 36.0, sex: "M" })
doc.results                 # [VText("山田太郎")]
```

Result:

```
TypeDef Person:
  params: [name, age, sex]
  kinds:  [Text, Number, Enum(F, M)]

@taro = Entity(Person)
  name: VText("山田太郎")
  age:  VNumber(36.0)
  sex:  VEnum("M", choices=["F", "M"])

@taro.name → VText("山田太郎")
```

## Features

| Feature | Syntax | Description |
|---------|--------|-------------|
| Type definition | `@%Rect (x y w h)` | Define a named type with parameters |
| Global variable | `@#R1 %Rect(10 20 100 50)` | Bind a typed entity to a global name |
| Local variable | `@@taro %Person(...)` | Bind a value to a local name |
| Getter | `#R1.x` | Access fields, then props, then Empty |
| Setter | `#R1!color([red])` | Set field/prop on an entity |
| Batch setter | `#R1!+(:x 10 :y 20)` | Set multiple properties at once |
| Type with kinds | `(:name :age % :sex %s(F M))` | `%` = Number, `%s(...)` = Enum |
| Implicit dict | `(:key1 val1 :key2 val2)` | Key-value dict from `:` markers |
| Undefined ref | `#NOPE` | Returns `Empty` (no exception) |

## Data Model

| Type | Description |
|------|-------------|
| `VText` | Text string |
| `VNumber` | Numeric value |
| `VDate` | Date string (ISO-8601) |
| `VEnum` | Enumerated value with choices |
| `VList` | List of values |
| `VDict` | Key-value dictionary |
| `VRef` | Unresolved reference |
| `VEntity` | Typed entity with fields and props |
| `Empty` | Singleton for undefined references |

## Architecture

```
STN text → [STN Lexer] → AST (Node) → [STN Core] → Document
                                            │
                                  ┌─────────┼─────────┐
                                  │         │         │
                              TypeDefs   Globals   Locals
                                        (Values)  (Values)
```

**Two-pass evaluation:**

1. **Pass 1** — Scan for `@` definitions, register TypeDefs
2. **Pass 2** — Evaluate all statements, resolve references, create entities, apply getters/setters

## Testing

```
uv run pytest tests/ -v
```

See [stn_core_spec_v01_ja_r3.md](stn_core_spec_v01_ja_r3.md) for the full specification.
