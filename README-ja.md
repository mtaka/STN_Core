# STN Core

STN AST の構造評価エンジンです。

STN Core は [STN Lexer](../STN_lexer) が生成する AST を受け取り、型定義・変数束縛・Entity 生成・getter/setter 適用を経て、評価済みの **Document** を構築します。

## インストール

```
pip install -e .
```

`stn-lexer` が依存パッケージとして必要です（`pyproject.toml` のパス依存で解決されます）。

## 使用例

入力（STN）：

```
@%Person (:name :age % :sex %s(F M))
@@taro %Person(:name 山田太郎 :age 36 :sex M)
@taro.name
```

コード：

```python
from stn import parse
from stn_core import evaluate

doc = evaluate(parse(text).ast)

doc.typedefs["Person"]      # TypeDef(name="Person", params=["name","age","sex"], ...)
doc.locals_["taro"]         # VEntity(Person { name: "山田太郎", age: 36.0, sex: "M" })
doc.results                 # [VText("山田太郎")]
```

結果：

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

## 機能一覧

| 機能 | 構文 | 説明 |
|------|------|------|
| 型定義 | `@%Rect (x y w h)` | 名前付き型をパラメータ付きで定義 |
| グローバル変数 | `@#R1 %Rect(10 20 100 50)` | 型付き Entity をグローバル名に束縛 |
| ローカル変数 | `@@taro %Person(...)` | 値をローカル名に束縛 |
| getter | `#R1.x` | fields → props → Empty の順に探索 |
| setter | `#R1!color([red])` | Entity のフィールド/プロパティを設定 |
| バッチ setter | `#R1!+(:x 10 :y 20)` | 複数プロパティを一括設定 |
| 型の種類指定 | `(:name :age % :sex %s(F M))` | `%` = Number、`%s(...)` = Enum |
| 暗黙辞書 | `(:key1 val1 :key2 val2)` | `:` マーカーによるキーバリュー辞書 |
| 未定義参照 | `#NOPE` | `Empty` を返す（例外停止しない） |

## データモデル

| 型 | 説明 |
|----|------|
| `VText` | テキスト文字列 |
| `VNumber` | 数値 |
| `VDate` | 日付文字列（ISO-8601） |
| `VEnum` | 選択肢付き列挙値 |
| `VList` | 値のリスト |
| `VDict` | キーバリュー辞書 |
| `VRef` | 未解決の参照 |
| `VEntity` | fields と props を持つ型付きエンティティ |
| `Empty` | 未定義参照時のシングルトン |

## アーキテクチャ

```
STN テキスト → [STN Lexer] → AST (Node) → [STN Core] → Document
                                                │
                                      ┌─────────┼─────────┐
                                      │         │         │
                                  TypeDefs   Globals   Locals
                                            (Values)  (Values)
```

**2パス評価：**

1. **パス1** — `@` 定義を走査し、TypeDef を登録
2. **パス2** — 全文を評価し、参照解決・Entity 生成・getter/setter 適用

## テスト

```
uv run pytest tests/ -v
```

詳細な仕様は [stn_core_spec_v01_ja_r3.md](stn_core_spec_v01_ja_r3.md) を参照してください。
