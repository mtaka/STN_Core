# STN_Core 仕様 v0.1（日本語完全版・r3）

生成日時: 2026-02-13 20:25:30

---

# 1. 目的

STN_Core は STN の構造コアを定義する。  
STN_Lexer が出力するAST（一次AST）を、以下の処理を通して再構成する：

1. Leader / Unit の再構成
2. MetaLeader / MetaUnit の再構成
3. 定義（DefinitionBlock）の登録
4. 型定義（TypeDef）の展開
5. 変数への値束縛
6. getter / setter の適用
7. 暗黙チャンクを含む辞書正規化

これらを経て生成される最終構造を Document と呼ぶ。

---

# 2. 用語

## 2.1 Leader

Leader は後続トークンに構造的役割を与える予約記号である。  
Leader は常に独立トークンとして字句化される。

- `#` : グローバル参照
- `@` : ローカル参照（※MetaLeader兼用）
- `.` : getter
- `!` : setter
- `:` : Key（辞書キー）
- `%` : 型呼び出し

## 2.2 Unit

Leader が後続要素（ATOM / NUMBER / LITERAL / BLOCK）と結合した構造単位。

例：
- `#01`
- `#[Some Text]`
- `#(1 2 3)`
- `:x`
- `%Rect(...)`

## 2.3 MetaLeader

文の種類を切り替えるLeader。

- `@` : define

## 2.4 MetaUnit

MetaLeader によって構成される statement 単位。  
v0.1 では DefinitionBlock のみ。

---

# 3. データモデル

## 3.1 PrimitiveKind

Core が扱う最小型：

- Text
- Number
- Date
- Enum(choices)

型は検証しない。  
解釈不能な場合は Text として保持する。

## 3.2 Value

- VText
- VNumber
- VDate
- VEnum
- VList
- VDict
- VRef
- VEntity

## 3.3 TypeDef

- name
- params
- kinds（省略時はText）

例：

@%Rect (x y w h)
@%Reg (:x % :y % :w % :h %)

## 3.4 Entity

- type_name
- fields
- props

fields は TypeDef 由来  
props は setter により追加

---

# 4. 暗黙チャンク

(:x 10 20 :y 30)
→ { x: [10,20], y: 30 }

Key Unit が出現したら次のKeyまでが値。

---

# 5. getter / setter

## getter（`.`）

探索順序：

1. fields
2. props
3. Empty

## setter（`!`）

探索順序：

1. fields があれば更新
2. props にあれば更新
3. なければ props に新規作成

## !+

Block を暗黙チャンク正規化後、複数プロパティ設定。

---

# 6. DefinitionBlock

## 6.1 種類

- GlobalVarDef
- LocalVarDef
- TypeDef

例：

@#A (10 20)
@%Rect (x y w h)

---

# 7. Document と Environment

STN_Core は全体を保持する Document を構築する。

Document は以下を含む：

- Global 定義テーブル
- Local 定義テーブル（スコープ毎）
- TypeDef テーブル
- 評価済み Entity / Value 群

処理フロー：

1. STN_Lexer AST を走査
2. DefinitionBlock を Environment に登録
3. 型定義を参照して Entity を生成
4. 値をグローバル／ローカルへ束縛
5. setter / getter を適用
6. 正規化された構造を Document として保持

## 未定義参照規則

未定義の変数が参照された場合：

→ Empty を返す（例外停止しない）

---

# 8. 使用例

@%Rect (x y w h)
@#R1 %Rect(10 20 100 50)!id(#01)

#R1.x

期待：

- TypeDef 登録
- GlobalVarDef 登録
- Entity 生成
- getter 正常動作

---

# 終わり
