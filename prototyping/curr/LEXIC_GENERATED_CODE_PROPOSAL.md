# Lexic — Proposal for Generated Code End-Shape

Status: design proposal.
Supersedes the code shape described in `OPUS_REVIEW_V3.md` §3 and §6.
Does not supersede the IR concerns raised there — integrates with them (see
[§8](#8-integration-with-opus_review_v3)).

The target: the generated Pydantic module should look like hand-written
Pydantic code, the grammar should be fully recoverable from the module, and
the two paths (grammar → module, user-written module → grammar) should
converge on the same file.

---

## 1. What's wrong with the current generated code

Read `generated/chess.py`, `generated/c.py`, `generated/json_ws.py`. Six
concrete problems:

1. **Every class carries a 10-line `RuleSpec(...)` blob** ahead of the field
   definitions. The fields — the part that matters to users — are buried.
2. **Field names are pattern-derived, not semantic.** `a_h_x: str`,
   `cc_1_8: str`, `nbkqr: str`, `val_0_92: str`, `ee_0_9_1_9_0: str`.
3. **Synthetic helper classes leak.** `StatementArm1` … `StatementArm7`,
   `ExpressionItem`, `Statementarm7Item`, `ArglistItem` are grammar-shape
   artifacts, not domain concepts.
4. **List-tail idioms are exposed raw.** `[1,2,3]` parses to
   `Array(array_item=ArrayItem(value=1, arrayitem_item=[ArrayitemItem(value=2), ArrayitemItem(value=3)]))`.
5. **Structured rules collapse to opaque strings.** `Nonpawn` has six
   semantic components; generated class has `value: str`.
6. **Unions have no discriminator.** `Move.value: Union[Pawn, Nonpawn, Castle]`
   can't be constructed from a dict at all.

Root cause, single sentence: **the generated code is a transcription of the
grammar AST, not a model of the domain.**

---

## 2. Core principle

> **The class declaration is the single source of truth. Every downstream
> artifact — `RuleSpec`, Lark grammar, GBNF text, generator strategy — is
> derived from it.**

The decorator reads field types + a rule string + module-level type aliases
and synthesises `__grammar__`. Users never write `RuleSpec`. Codegen
produces the same file a user would have written by hand. One file, one
authority.

---

## 3. What the user sees

Minimal example (arithmetic grammar):

```python
from __future__ import annotations
from typing import Annotated, List, Literal

from pydantic import Discriminator, StringConstraints
from lexic import GrammarModel, grammar_rule


# ── Character-class types ───────────────────────────────────────────────
Digits    = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]
LowerChar = Annotated[str, StringConstraints(pattern=r"^[a-z]$")]
IdentTail = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]*$")]

# ── Literal-alternation types ───────────────────────────────────────────
ArithOp = Literal["-", "+", "*", "/"]


# ── Concrete rules ──────────────────────────────────────────────────────
@grammar_rule('head tail ws')
class Ident(GrammarModel):
    head: LowerChar
    tail: IdentTail = ""


@grammar_rule('digits ws')
class Num(GrammarModel):
    digits: Digits


@grammar_rule('"(" ws expr ")" ws')
class Parens(GrammarModel):
    expr: Expr


Term = Annotated[Ident | Num | Parens, Discriminator(_discriminate_term)]


@grammar_rule('op term')
class BinaryOp(GrammarModel):
    op: ArithOp
    term: Term


@grammar_rule('head tail*')
class Expr(GrammarModel):
    head: Term
    tail: List[BinaryOp] = []


@grammar_rule('expr "=" ws result "\\n"')
class Assignment(GrammarModel):
    expr: Expr
    result: Term


@grammar_rule('assignments+')
class Root(GrammarModel):
    assignments: List[Assignment]
```

No `RuleSpec` blobs. No `ABC`. No helper classes named after grammar
artifacts. No pattern-sniffed field names. Alternations are discriminated
unions, not base classes. Every field's type carries enough information for
Pydantic to validate, for the Pydantic → GBNF path to emit a grammar, and
for the LLM constraint engine to mask tokens.

---

## 4. The rule-string DSL

Claim-to-be-refuted: "the rule string is just GBNF right-hand-side." That
was sloppy. GBNF can express grouping and nested alternation that Pydantic
fields can't hold directly.

**The rule string is a strict subset of GBNF.** Its grammar:

```
rule       := item*
item       := literal | field_ref
field_ref  := name quantifier?
quantifier := "?" | "+" | "*" | ("+" | "*") separator
separator  := "[" sep_item+ "]"
sep_item   := literal | bare_rule_ref    # no fields allowed inside
literal    := '"' chars '"'
name       := identifier                 # must match a field on the class
```

Everything else a grammar can express goes **into the type system or into
helper classes**, never into the rule string.

### 4.1 What goes where

| GBNF construct | Maps to | Example |
|---|---|---|
| `A B C` | Rule-string sequence | `'expr "=" ws term "\\n"'` |
| `A?` (single field) | Optional field | `else_block?` with `else_block: ElseBlock \| None` |
| `A+` / `A*` (single field) | `List[A]` field | `assignments+` with `List[Assignment]` |
| `"a" \| "b" \| "c"` | `Literal["a","b","c"]` field type | `op: Literal["-","+","*","/"]` |
| `rule_a \| rule_b \| rule_c` | Discriminated union alias | `Term = Annotated[...]` at module level |
| `[a-z]` / `[a-z]+` / `[0-9]{0,15}` | `Annotated[str, StringConstraints(pattern=...)]` | See §5 |
| `(X Y)+` with rule refs | Helper class + `List[Helper]` | `BinaryOp` helper, `tail*` in parent |
| `(X Y)+` pure pattern | Single constrained-string field | `capture: Annotated[str, ...]` |
| `X (sep X)*` pure separator | `List[X]` + separator annotation | `values*[", " ws]` |
| `X (Y X)*` semantic separator | Helper class for the `Y X` pair | See §7.1 |

### 4.2 Three deterministic decisions

Every GBNF rule reduces to the table above via three mechanical checks:

**Decision 1: groups with rule refs → helper class. Groups without → field.**

`(pawn | nonpawn | castle) [+#]?` splits:
- Outer group contains rule refs → `piece: Pawn | Nonpawn | Castle`
  discriminated union.
- `[+#]?` is pure pattern → `annotation: Annotated[str, StringConstraints(pattern=r"^[+#]?$")] = ""`.

`([a-h] "x")?` is pure pattern → one constrained-string field:
`capture: Annotated[str, StringConstraints(pattern=r"^([a-h]x)?$")] = ""`.

**Decision 2: separator annotation vs helper class.**

- Separator contains only literals + `ws` → flatten with `[", " ws]` syntax.
- Separator contains semantic structure (a literal alternation or a
  meaningful pattern) → helper class.

`array ::= "[" ws (value ("," ws value)*)? "]" ws`
→ `values*[", " ws]` (pure separator, flattens).

`expr ::= term ([-+*/] term)*`
→ Helper class `BinaryOp` with `op: ArithOp` and `term: Term`, because
`[-+*/]` carries semantics worth typing.

**Decision 3: literal alternation typing.**

- Pure-literal alternation → `Literal[...]` on a field.
- Pure-rule-ref alternation → `Union[...]` / discriminated union alias.
- Mixed (some literal, some rule ref) → helper classes, one per arm.

### 4.3 What the decorator does

```python
def grammar_rule(template: str):
    def decorate(cls: type[GrammarModel]) -> type[GrammarModel]:
        tokens   = _parse_rule_template(template)
        _validate_field_refs(tokens, cls.model_fields)
        atoms    = _build_atoms(tokens, cls.model_fields, _module_aliases(cls))
        cls.__grammar__ = RuleSpec(
            rule_name         = _snake(cls.__name__),
            class_name        = cls.__name__,
            parent_class_name = "GrammarModel",    # flat
            kind              = "sequence",        # always, see §6
            items             = atoms,
            field_map         = _derive_field_map(atoms, cls.model_fields),
        )
        _resolve_forward_refs(cls)
        return cls
    return decorate
```

Class-time validation: every `name` in the template must exist in
`cls.model_fields`, every field must appear exactly once in the template
(except those explicitly marked `_raw_ws` — see §9). Inconsistencies raise
at class-creation time with a specific error pointing at the template.

---

## 5. Field type system — Literal vs Pattern (corrected)

**Character classes are patterns. Literal alternations are enums. Do not
conflate them.**

### 5.1 Why `Literal` for char ranges is wrong

`Literal["a","b","c","d","e","f","g","h"]` fails at scale:
- `[a-z]` → 26 literals. Noisy but tolerable.
- `[\u3040-\u309f]` (hiragana) → 96 literals.
- `[a-z]+` → infinite literals. Can't be a `Literal` at all.
- `[a-h][1-8]` → 64 literals. Quantifying this compounds catastrophically.
- `[a-z]{0,15}` → more than `7e21` literals.

`Literal` also doesn't compose with quantifiers. A field whose value is any
string of lowercase letters cannot be expressed as a `Literal` set.

### 5.2 The correct mapping

| GBNF source | Type |
|---|---|
| `"int" \| "float" \| "char"` | `Literal["int", "float", "char"]` |
| `"<=" \| "<" \| "==" \| "!=" \| ">=" \| ">"` | `Literal["<=", "<", "==", "!=", ">=", ">"]` |
| `"+" \| "-" \| "*" \| "/"` | `Literal["+", "-", "*", "/"]` |
| `[abc]` | `Annotated[str, StringConstraints(pattern=r"^[abc]$")]` |
| `[a-h]` | `Annotated[str, StringConstraints(pattern=r"^[a-h]$")]` |
| `[a-z]+` | `Annotated[str, StringConstraints(pattern=r"^[a-z]+$")]` |
| `[0-9]{0,15}` | `Annotated[str, StringConstraints(pattern=r"^[0-9]{0,15}$")]` |
| `[\u3040-\u309f]+` | `Annotated[str, StringConstraints(pattern=r"^[\u3040-\u309f]+$")]` |
| `[^\n]*` | `Annotated[str, StringConstraints(pattern=r"^[^\n]*$")]` |
| `"\"" ([^"\\] \| "\\" .)* "\""` | `body: Annotated[str, StringConstraints(pattern=...)]` |

Rule: **`Literal` iff the GBNF source is a literal-string alternation with
min=max=1**. Char classes are never `Literal`.

### 5.3 Opting into Literal for small char classes

A user may want enum semantics for a small char class (e.g. chess pieces
`[NBKQR]`). The type system doesn't force this, but the sidecar (§6.3) or a
module-level alias supplied by the user does:

```python
# Optional opt-in, only for genuinely-enum-like small sets:
Piece = Literal["N", "B", "K", "Q", "R"]

@grammar_rule('piece disambig_file? disambig_rank? capture? file rank')
class Nonpawn(GrammarModel):
    piece: Piece      # opt-in: user wants enum semantics
    ...
```

Codegen's default for `[NBKQR]` is `Annotated[str, StringConstraints(pattern=r"^[NBKQR]$")]`.
User upgrades via sidecar or by defining the alias and naming it in the
sidecar. Library never infers "this char class is small enough to be an
enum" — that decision is semantic, not syntactic.

### 5.4 Multi-character patterns

Quantifiers compose with the regex, not with the `Literal`:

- `[a-z]+` → `pattern=r"^[a-z]+$"` — any nonempty lowercase string.
- `[a-z]{3}` → `pattern=r"^[a-z]{3}$"` — exactly three.
- `[0-9]{0,15}` → `pattern=r"^[0-9]{0,15}$"`.
- `([^*]|\*[^/])*` (C multi-line comment body) → single `str` field with
  the full composed pattern.

One `Annotated[str, StringConstraints]` field per atom, regardless of
quantifier. The pattern carries everything.

### 5.5 IR implication

`CharClassAtom`, `QuantifiedLiteralAtom`, and `InlineRegexAtom` all collapse
to a single `PatternAtom`:

```python
@dataclass
class PatternAtom:
    pattern: str          # a regex (Lark-compatible, matches a single atom occurrence)
    gbnf: str             # shadow form for to_gbnf() emission
    min: int
    max: int | None
```

Seven atom types → five. V3 §2 (classifier complexity) shrinks because
three of its five classifications fold into "sequence rule with
pattern-constrained fields."

---

## 6. Naming without GBNF comments

Ordinal `_0`, `_1` was a bad answer. The real answer is a four-tier cascade.

### 6.1 Tier 1 — type-alias names

When a field's type is bound to a module-level name, **the alias name is
the default field name**. Snake-cased, never pluralized automatically (the
user's choice):

```python
Digits    = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]
LowerChar = Annotated[str, StringConstraints(pattern=r"^[a-z]$")]

# Codegen produces:
class Num(GrammarModel):
    digits: Digits            # field name from alias

class Ident(GrammarModel):
    lower_char: LowerChar     # auto; user almost certainly overrides
    ident_tail: IdentTail
```

Collision handling: two fields with the same alias → `digits`, `digits_2`.
Collision is a signal the user has semantic distinctions the types don't
capture; library shouldn't invent names, just disambiguate honestly.

### 6.2 Tier 2 — built-in pattern library

A small table of well-known patterns → conventional field names. Ships with
Lexic:

```python
BUILTIN_PATTERNS = {
    r"^[0-9]$":         "digit",
    r"^[0-9]+$":        "digits",
    r"^[a-z]$":         "lower",
    r"^[A-Z]$":         "upper",
    r"^[a-zA-Z]$":      "letter",
    r"^[a-zA-Z_]$":     "letter",
    r"^[a-zA-Z_0-9]$":  "alnum",
    r"^[a-zA-Z_0-9]*$": "alnum_tail",
    r"^[ \t]+$":        "spaces",
    r"^[ \t\n]+$":      "ws",
}
```

~10 entries. Not a heuristic name generator. If the pattern isn't in the
table, tier 2 does nothing. Extensible via `lexic.register_pattern(...)`
or a `[tool.lexic.patterns]` section in `pyproject.toml`. Users do not
fork Lexic to add a pattern.

### 6.3 Tier 3 — structural positional

If tiers 1 and 2 didn't apply, use names that describe the field's
structural role, not its pattern content:

- First pattern-typed field → `head`, subsequent → `part_2`, `part_3`.
- First rule-ref field → `body`, subsequent → `body_2`.
- First literal-alternation field → `kind`, subsequent → `kind_2`.
- Where the grammar is literally `X X*`, detect it syntactically → `head`,
  `tail`.

These names are **honest about structure** rather than **lying about
semantics**. `part_3: str` tells you this is the third positional
component. `val_0_92: str` lies about what `val_0_92` means.

Tier 3 is fugly on purpose. It exists so every rule has a valid generated
shape, and so the sidecar has something to rename.

### 6.4 Tier 4 — sidecar YAML

For grammars the user doesn't own (llama.cpp corpus, partner schemas),
editing `.gbnf` to add `# @field=` isn't an option. The sidecar lives next
to the generated module and is re-applied every time codegen runs:

```yaml
# arithmetic.lexic.yaml
classes:
  Ident:
    fields:
      lower_char: head       # rename tier-1 name → semantic name
      ident_tail: tail
  Number:
    class_name: DecimalNumber       # rename the class itself
    fields:
      sign: sign
      integer_part: whole
      fractional_part: decimal
      exponent: power
  RootItem:
    class_name: Assignment          # rename an auto-generated helper class
  Nonpawn:
    fields:
      piece:
        type: Literal["N","B","K","Q","R"]   # opt into enum semantics
        name: piece
```

Precedence: **sidecar > tier 1 alias > tier 2 library > tier 3 positional**.

For the Pydantic-first flow, the sidecar doesn't apply — the user wrote the
field names.

---

## 7. Hard cases, worked

### 7.1 C statement arms

`statement` has nine arms, most of them inline sequences that deserve their
own domain name:

```python
# Tier 3 fallback would produce StatementArm1..StatementArm7 + named rules
# Sidecar specifies real names:
```

```yaml
# c.lexic.yaml
classes:
  StatementArm1: { class_name: Declaration }
  StatementArm2: { class_name: Assignment }
  StatementArm3: { class_name: ExpressionStatement }
  StatementArm4: { class_name: Return }
  StatementArm5: { class_name: While }
  StatementArm6: { class_name: For }
  StatementArm7: { class_name: If }
  Statementarm7Item: { class_name: ElseBlock }
```

Generated output after sidecar:

```python
@grammar_rule('"while" "(" condition ")" "{" body* "}"')
class While(GrammarModel):
    condition: Condition
    body: List[Statement] = []


@grammar_rule('"if" "(" condition ")" "{" then_body* "}" else_block?')
class If(GrammarModel):
    condition: Condition
    then_body: List[Statement] = []
    else_block: ElseBlock | None = None


@grammar_rule('"else" "{" body* "}"')
class ElseBlock(GrammarModel):
    body: List[Statement] = []
```

Where the first literal in a statement arm is a recognizable keyword
(`"while"`, `"return"`, `"if"`), codegen can also try a **heuristic** for
tier 3: "first literal in sequence, capitalized, is the class name." That
eliminates most sidecar entries for arms-that-start-with-a-keyword. Arms
that start with a rule ref (`statement-arm1` starts with `dataType
identifier`) still need the sidecar.

### 7.2 Chess overlapping arms

`[a-h]` and `[1-8]` appear multiple times in `pawn` and `nonpawn`. Using
tier-2 names produces collisions (`lower`, `lower_2`). Sidecar fixes it
once:

```yaml
classes:
  Pawn:
    fields:
      part_1: capture_file_and_x   # pure-pattern group ([a-h] "x")?
      part_2: dest_file
      part_3: dest_rank
      part_4: promotion             # ("=" [NBKQR])?
  Nonpawn:
    class_name: Nonpawn
    fields:
      part_1: piece
      part_2: disambig_file
      part_3: disambig_rank
      part_4: capture               # "x"?
      part_5: dest_file
      part_6: dest_rank
```

The resulting `Pawn`:

```python
CaptureFileAndX = Annotated[str, StringConstraints(pattern=r"^([a-h]x)?$")]
DestFile        = Annotated[str, StringConstraints(pattern=r"^[a-h]$")]
DestRank        = Annotated[str, StringConstraints(pattern=r"^[1-8]$")]
Promotion       = Annotated[str, StringConstraints(pattern=r"^(=[NBKQR])?$")]

@grammar_rule('capture_file_and_x dest_file dest_rank promotion')
class Pawn(GrammarModel):
    capture_file_and_x: CaptureFileAndX = ""
    dest_file:          DestFile
    dest_rank:          DestRank
    promotion:          Promotion       = ""
```

No `Literal["a",..."h"]`. No `a_h_x`. All fields validated by pattern.

### 7.3 json_ws number

Nested quantified groups collapse into per-field patterns:

```python
Sign           = Annotated[str, StringConstraints(pattern=r"^-?$")]
IntegerPart    = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]{0,15})$")]
FractionalPart = Annotated[str, StringConstraints(pattern=r"^\.[0-9]+$")]
Exponent       = Annotated[str, StringConstraints(pattern=r"^[eE][-+]?[0-9][1-9]{0,15}$")]

@grammar_rule('sign integer_part fractional_part? exponent? ws')
class Number(Value):
    sign:            Sign           = ""
    integer_part:    IntegerPart
    fractional_part: FractionalPart | None = None
    exponent:        Exponent       | None = None
```

The `{0,15}` quantifier lives **inside** the pattern. Pydantic validates
it at construction; the generator samples it; `to_gbnf()` emits it from
the `PatternAtom.gbnf` shadow. Single source of structural truth.

### 7.4 json_ws string body

A 64-character pattern:

```python
JsonStringBody = Annotated[
    str,
    StringConstraints(
        pattern=r'^([^"\\\x7F\x00-\x1F]|\\(["\\bfnrt]|u[0-9a-fA-F]{4}))*$'
    ),
]

@grammar_rule('"\"" body "\"" ws')
class String(Value):
    body: JsonStringBody
```

The same pattern used by Lark at parse time is used by Pydantic to
validate, by `generate()` to sample, and by `to_gbnf()` (via the shadow
`gbnf` field on the atom) to emit. One regex authority.

### 7.5 json_ws ws

`ws ::= | " " | "\n" [ \t]{0,20}` — a three-arm alternation with one
empty arm:

```python
WsPattern = Annotated[str, StringConstraints(pattern=r"^( |\n[ \t]{0,20}|)$")]

@grammar_rule('value')
class Ws(GrammarModel):
    value: WsPattern
```

The three arms fold into one disjunctive pattern. Pydantic validates the
disjunction; users rarely touch `Ws` directly.

### 7.6 Discriminator synthesis for overlapping unions

`Factor = Identifier | Number | UnaryTerm | FuncCall | ParenExpression`.
`Identifier` and `FuncCall` both start with an identifier. The
discriminator needs lookahead:

```python
def _discriminate_factor(v):
    # When v is a concrete arm instance, its class is the tag.
    if isinstance(v, GrammarModel):
        return type(v).__name__
    # When v is a dict (constructed from JSON or model_dump), pick by
    # required-field uniqueness.
    if isinstance(v, dict):
        if "expression" in v: return "ParenExpression"
        if "args" in v:       return "FuncCall"
        if "factor" in v:     return "UnaryTerm"
        if "digits" in v:     return "Number"
        if "value" in v:      return "Identifier"
    raise TypeError(f"Cannot discriminate Factor: {v!r}")
```

Generated by codegen from analysis of each arm's required field set.
Every pair of arms in a union must differ by at least one required field
name — if they don't, the grammar itself is structurally ambiguous and
codegen raises with the ambiguous arm pair named.

Generated discriminators live alongside the module, not in a separate
file — users can read what dispatch rule governs their union.

---

## 8. Integration with OPUS_REVIEW_V3

| V3 concern | Resolution in this proposal |
|---|---|
| **§1 `_build_instance` imperative bridge** | Pattern-constrained fields are single Lark tokens. Transformer hands Pydantic a dict; Pydantic validates. Coalescing and `atom.max != 1` sniffing disappear. Remaining dispatch fits a ~40-LoC table. |
| **§2 `_classify` cascade** | `value_str`, `pure_literal_alt`, and `named_alt` all fold into "sequence class + union alias." Two branches: alternation → alias, sequence → class. |
| **§3 Semantic naming** | Four-tier cascade (§6). Ordinal names are an honest tier-3 fallback; sidecar overrides without editing `.gbnf`. Annotations in grammar comments become optional, not mandatory. |
| **§4 `value_str` Lark leak** | Resolved. No `value_str` path — structured rules become sequences with pattern-constrained fields. |
| **§5 `generate.py` structural dup** | Patterns delegate to `re` / `exrex`. One regex authority, consumed by Lark, Pydantic, generator, and emitter. |
| **§6 Union discrimination** | Mandatory and generated (§7.6). Every union emits an `Annotated[..., Discriminator(fn)]` alias and a synthesised discriminator function. |
| **§7 R005 absent** | Cleaner surface, still unimplemented. Constraint engine tracks "current field" and masks by the field's type. `grammar_state.py` builds against RuleSpec as before. |
| **§8 parse regenerates** | Unchanged — still needs `CompiledGrammar`. |
| **§9 `to_gbnf()` back-edge** | Concrete justification to make atoms polymorphic (`PatternAtom.to_gbnf()` etc). STRUCTURE.md's non-goal "don't rush polymorphism" should be revisited. |
| **§10 Helper collision** | List-tail flattening + separator syntax eliminates most helpers. Those remaining fit a single global name registry. |
| **§A Generator bias** | Type-driven generator reads patterns directly; `Optional` honestly samples presence/absence. |
| **§B Parallel bracket parsers** | Gone. Both paths defer to `re`. |
| **§C Transformer cycle** | Independent; `to_lark_name` moves to `lexic.utils.names`. |

Eight of thirteen resolve cleanly. Two (§7, §8) are independent of this
proposal. Two (§3, §9) require design decisions this proposal makes
explicit. One (§C) is a separate small cleanup.

---

## 9. Round-trip fidelity

Two instance-level distinctions matter:

- **Parsed instances** carry a hidden `_raw: dict[str, str]` attribute
  populated by the transformer. It records original whitespace, separator
  text, and any other non-semantic input fragments that can't be recovered
  from typed fields alone.
- **Constructed instances** have `_raw = None`. `to_text()` emits canonical
  form using literals from `__grammar__` and default whitespace.

Contract:

- `parse(text).to_text() == text` — exact round-trip for parsed input.
- `Constructed(...).to_text() == canonical_form` — canonical emission for
  user-built instances.
- `parse(Constructed(...).to_text())` — always succeeds; the canonical
  form is always valid.

`_raw` is excluded from `model_dump()` by default, from `__eq__`, and from
`semantic_dump()`. Users who don't care about whitespace fidelity will
never see it.

This replaces the current `ws: Ws`, `ws2: Ws` visible fields. Whitespace
rules still produce `Ws` classes; they're just not top-level-visible on
their consumers — consumers hold `_raw["ws_1"]`, `_raw["ws_2"]` strings.

---

## 10. Tensions and open questions

### 10.1 Three sources of truth must stay consistent

The decorator has three inputs: the rule-string template, the class's
field types, and module-level type aliases. Inconsistencies (a field in
the template that doesn't exist on the class, or vice versa) raise at
class-creation time. This is cheap — one validation per class, zero
runtime overhead — but it is a real contract the user has to respect.

### 10.2 Discriminator synthesis is real codegen work

Unlike the rest of this proposal (which is mostly rearrangement of existing
information), discriminator functions have to be **generated as Python
source code**, not derived at runtime. This is the single implementation
commitment that's bigger than a refactor. Analysis rule: the set of
required field names must be unique across arms; otherwise raise with a
specific message naming the ambiguous arms.

### 10.3 Sidecar workflow needs editor support

A YAML sidecar is a second file the user has to maintain. For the common
case (a grammar with five well-named rules) the sidecar is either absent
or tiny. For grammars with many synthetic helpers (C, complex JSON
dialects), the sidecar gets substantial. Mitigation: codegen emits a
default sidecar on first run, user edits it, subsequent runs merge
user edits with regenerated defaults. The merge is structural, not textual
(YAML keys, not lines).

### 10.4 Pattern size

Some patterns get long (`json_ws.StringBody` at ~50 chars, C
`MultiLineComment.text` at ~20 chars, the worst real-world cases are at
~200 chars). This is fine — patterns are meant to be authored once and
read rarely. Lexic can render patterns as named type aliases
(`JsonStringBody = Annotated[...]`) so they don't pollute the class body.

### 10.5 Literal → Pattern opt-out

In §5.3 the user opts *into* `Literal` via sidecar. The reverse is also
available: if codegen produces a pattern and the user wants a literal
alternation instead, sidecar specifies `type: Literal[...]`. The library
never second-guesses the user.

### 10.6 Helpers that can't be named

The `statementarm7-item` case (`("else" "{" statement* "}")?`) gets
named `ElseBlock` via sidecar. What about truly anonymous groups like
`("a" "b" "c")*`? Tier 3 produces `Group1`, `Group2`. Ugly but honest.
Users who don't rename them via sidecar get what they asked for by not
naming them.

---

## 11. Non-goals

- **Parsing GBNF in the decorator.** The decorator consumes the bounded
  DSL of §4.1, not full GBNF. Anyone writing GBNF-as-rule-string gets a
  parse error with the production that failed named.
- **Inferring class names semantically from grammar structure.** The
  `statement → Declaration, Assignment, Return` mapping is done by
  sidecar, not by NLP-on-the-first-literal. Heuristics compete with
  user intent.
- **Name policy beyond the four tiers.** No "suggest names from
  neighbouring rules," no "infer from rule docstring." Keep the surface
  finite.
- **Replacing Pydantic.** `GrammarModel` is a `pydantic.BaseModel`
  subclass. We use Pydantic's validator, discriminator, and
  `StringConstraints` facilities directly. No parallel stack.
- **Shipping R006 against pattern-derived names.** R006 translates via
  discriminated unions, user-named fields (tier 1/2/4), or
  semantic_dump structural matching — never via tier-3 positional names.
  If a source grammar has only tier-3 names, R006 raises.

---

## 12. Implementation order

Independent, lands incrementally:

1. **Merge char-class atom types into `PatternAtom`.** Mechanical refactor
   of `lexic.ir.atoms`.
2. **Write `grammar_rule` decorator.** Parses the bounded DSL, synthesizes
   `RuleSpec`, attaches `__grammar__`. ~200 LoC.
3. **Type-driven field generation in `ModelEmitter`.** Emit
   `Annotated[str, StringConstraints(...)]` for every `PatternAtom`;
   emit `Literal[...]` for pure-literal alternation atoms.
4. **Four-tier naming cascade in codegen.** Tier 3 is today's behaviour
   minus pattern-sanitization; tiers 1, 2, 4 are additive.
5. **Discriminator synthesis.** Analyse union arm field-sets, emit
   `_discriminate_*` functions alongside each union alias.
6. **Sidecar parser.** YAML, loaded post-codegen, applies renames
   structurally. First-run generates a default sidecar.
7. **`_raw` wiring in transformer.** Replace visible `ws`, `ws2` fields
   with `_raw` dict entries.

Each step is independently mergeable. Each preserves existing test
behaviour until the one it depends on lands. None require changes to
`parser.py` or `ast.py`.
