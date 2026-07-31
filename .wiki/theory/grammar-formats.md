---
tags: [theory, reference]
related: [lexic/flavour-system, lexic/architecture]
---

# Grammar Formats Reference

**When to load:** comparing GBNF/ABNF/EBNF syntax; writing or debugging a flavour emitter; checking operator precedence or escape notation for a specific format; understanding what Lexic can and cannot parse.

See also: [[lexic/flavour-system]] for how Lexic implements each format.

---

## GBNF (GGML Backus-Naur Form)

Defined by the llama.cpp project. Used natively as Lexic's primary input format.

### Core concepts

- **Purpose:** constrain LLM output token-by-token at inference time (logit masking). The grammar sampler converts valid grammar states to valid token sets and zeros out all other logit scores.
- **Character-level:** terminals are Unicode code points, not tokeniser tokens. The sampler bridges character-level grammar states to tokeniser-level vocabulary.
- **Start rule:** must be named `root`.

### Syntax reference

| Construct | Syntax | Notes |
|---|---|---|
| Rule definition | `name ::= body` | non-terminal names: dashed lowercase `[a-zA-Z_][a-zA-Z0-9_-]*` |
| Sequence | `a b c` | whitespace-separated; order is significant |
| Alternation | `a \| b \| c` | unordered choice (CFG semantics, not PEG ordered) |
| Grouping | `(body)` | embeds an alternation or applies a quantifier to a sequence |
| String literal | `"text"` | exact match; case-sensitive |
| Character class | `[a-z0-9]` | POSIX bracket expression interior; negation via `[^…]` |
| Optional | `x?` | equivalent to `x{0,1}` |
| Zero-or-more | `x*` | equivalent to `x{0,}` |
| One-or-more | `x+` | equivalent to `x{1,}` |
| Exact count | `x{m}` | exactly m repetitions |
| Bounded range | `x{m,n}` | m ≤ count ≤ n |
| At-least | `x{m,}` | at least m |
| At-most | `x{0,n}` | at most n |
| Comments | `# text` | stripped before parsing |
| Token by ID | `<[token-id]>` | matches specific vocab token (not character-level) |
| Token by string | `<token>` | matches token whose text equals the literal |
| Token negation | `!<[id]>` or `!<token>` | matches any token except the specified one |

**Escape sequences in strings and character classes:**

| Notation | Bits | Example |
|---|---|---|
| `\xXX` | 8-bit | `\x0a` = newline |
| `\uXXXX` | 16-bit | `A` = A |
| `\UXXXXXXXX` | 32-bit | Unicode beyond BMP |

### Performance constraint

`x? x? x?` (N optional copies) creates exponential parse-stack branching; the sampler becomes extremely slow. Use `x{0,N}` instead — this is a **hard constraint on GBNF generation**.

### GBNF vs. Lexic's self-grammar (current gaps)

There is no separate "Lexic meta-grammar" module anymore — `GBNF_GRAMMAR` (`grammars/gbnf.py`), authored directly as `IrAst`, is the grammar the native Earley engine parses GBNF text against (see [[lexic/architecture]]). It accepts the full GBNF surface, including bare exact-count quantifiers (`{m}`, via a dedicated `q-exact` rule) and token-level syntax (`<[id]>`, `<token>`, `!<…>`, mapped to `IrAlphabet` terminals — see [[lexic/tokens]]). One convention difference remains:

- **Implicit start rule** — GBNF requires `root` as start; Lexic supports `@start` directives and otherwise falls back to the first defined rule rather than enforcing the `root` convention.

---

## ABNF (Augmented Backus-Naur Form, RFC 5234)

IETF standard (STD 68, January 2008). Lexic supports it via `grammars/abnf.py`.

### Core syntax

| Construct | Syntax | Notes |
|---|---|---|
| Rule definition | `name = body CRLF` | names case-insensitive; may contain `-` |
| Sequence | `a b c` | whitespace-separated |
| Alternation | `a / b / c` | uses `/` not `\|` |
| Incremental alt. | `name =/ more` | append alternatives to existing rule |
| Grouping | `(body)` | |
| Optional | `[body]` | equivalent to `*1body` |
| Zero-or-more | `*element` | |
| One-or-more | `1*element` | |
| Exact | `3element` | exactly 3 |
| Range | `1*2element` | 1 to 2 |
| Decimal value | `%d13.10` | concatenation of code points; `.` separates |
| Hex value | `%x41` | single code point |
| Hex range | `%x41-5A` | code-point range |
| Binary value | `%b01000001` | binary code point |
| String literal | `"abc"` | **case-insensitive** by default |
| Case-sensitive lit. | `%s"abc"` | RFC 7405 extension |
| Comment | `; text` | to end of line |
| Prose | `<description>` | informal; not parseable by machines |

**Core rules** (Appendix B.1 of RFC 5234) — pre-defined named rules:

| Rule | Value |
|---|---|
| `ALPHA` | `%x41-5A / %x61-7A` (A–Z / a–z) |
| `DIGIT` | `%x30-39` (0–9) |
| `HEXDIG` | `DIGIT / "A" / "B" / "C" / "D" / "E" / "F"` |
| `SP` | `%x20` |
| `HTAB` | `%x09` |
| `CRLF` | `%d13.10` |
| `VCHAR` | `%x21-7E` (visible ASCII) |
| `WSP` | `SP / HTAB` |

### Operator precedence

ABNF has lower coupling between elements than GBNF. Precedence from tightest to loosest:

1. Terminals (`%xNN`, string literals, rule names)
2. Repetition (prefix `n*m`)
3. Grouping `(…)` and optional `[…]`
4. Sequence (juxtaposition)
5. Alternation `/`

### Key differences from GBNF

| Feature | GBNF | ABNF |
|---|---|---|
| Rule separator | `::=` | `=` |
| Alternation | `\|` | `/` |
| String case | case-sensitive | case-insensitive by default |
| Quantifier syntax | suffix `?`, `*`, `+`, `{m,n}` | prefix `n*m`, `*`, `n` |
| Optional shorthand | `x?` | `[x]` |
| Numeric values | `\xNN` escapes in strings/charclass | `%xNN`, `%dNN`, `%bNN` literals |
| Comment char | `#` | `;` |
| Start rule | convention: `root` | no convention |

### ABNF gaps in Lexic

`ABNF_GRAMMAR` (`grammars/abnf.py`) reached full RFC 5234+7405 surface parity in the 2026-07 Lark→Earley cutover (Phase 3 of `PLAN_cutover_parsing_v2.md`) — most of the historical gaps below are closed:

- **`[optional]` bracket syntax** — supported (an `option` rule at the repetition level, bound `(0, 1)`).
- **Incremental alternatives (`=/`)** — supported; arms are merged into the earlier same-named rule during reduction.
- **Decimal and binary terminal values** (`%d`, `%b`) — supported, single value and range (`dmark`/`bmark`, shared hexit machinery).
- **Case-sensitive string literals (`%s"…"`)** — RFC 7405 — supported (raw literal, no case expansion); `%i"…"` and bare `"…"` still expand case-insensitively, matching the pre-cutover behaviour.
- **`%x` concatenation (`.` notation)** — supported (`%x0D.0A` → a single code-point-sequence literal).
- **Prose (`<description>`)** — recognised by the grammar and explicitly rejected with `UnsupportedConstructError` at reduce time (not silently dropped, not a bare parse failure).

> [!warning]
> Remaining gaps, flagged to the user as open (not yet resolved as of the cutover landing):
> - **Value-sequences within `%d`/`%b`** (e.g. `%d13.10`, the decimal/binary analogue of `%x`'s dot-concatenation) — unsupported; fails as an engine parse error, not an explicit `UnsupportedConstructError`.
> - **Uppercase markers** (`%X`, `%D`, `%B`, `%S`, `%I`) — RFC 5234/7405 allow case-insensitive marker letters; Lexic only accepts lowercase. Neither gap appears in any ground-truth corpus or emitter output.
> - **Core rules** (`ALPHA`, `DIGIT`, etc.) — still must be defined manually in any grammar that uses them; `CORE_RULES` in `abnf.py` remains dead data (no consumer).

---

## EBNF (Extended Backus-Naur Form)

A family of notations, not a single standard. ISO/IEC 14977:1996 is the formal standard but is rarely used in practice.

### ISO 14977 key points

- Terminals: `"text"` or `'text'`; case-sensitive (unlike ABNF).
- Concatenation: explicit `,` required between every item — `a , b , c`.
- Alternation: `|` or `/`.
- Repetition: `{ body }` (zero or more); `[ body ]` (optional = zero or one).
- Grouping: `( body )`.
- Exception: `a - b` (a except those matching b).
- Rule end: `;` or `.`.
- Comment: `(* text *)`.
- Special sequence: `? text ?` — implementation-defined extension point.

**ISO 14977 is not used by Lexic and not recommended for new work.** The mandatory commas and absence of Unicode support make it impractical.

### Practical EBNF variants (what you will encounter)

| Variant | Used by | Alternation | Optional | Repetition |
|---|---|---|---|---|
| ISO 14977 | some standards | `\|` | `[…]` | `{…}` |
| W3C EBNF | XML, XPath specs | `\|` | `?` (postfix) | `*`, `+` (postfix) |
| ANTLR 4 `.g4` | ANTLR grammars | `\|` | `?` | `*`, `+` |
| Lark | Lark grammars | `\|` | `?` | `*`, `+` |
| ABNF (RFC 5234) | IETF RFCs | `/` | `[…]` or `*1` | `*`, `1*`, `n*m` (prefix) |
| GBNF | llama.cpp | `\|` | `?` | `*`, `+`, `{m,n}` |

**Lark's grammar format is effectively W3C-style EBNF** — postfix quantifiers `?`, `*`, `+`, alternation `|`, optional `[…]` — extended with terminals, priorities, and tree-shaping directives.

---

## Comparison: GBNF vs ABNF vs EBNF

| Feature | GBNF | ABNF (RFC 5234) | W3C EBNF / Lark |
|---|---|---|---|
| Rule separator | `::=` | `=` | `:` or `=` |
| Alternation | `\|` | `/` | `\|` |
| Sequence | juxtaposition | juxtaposition | juxtaposition |
| Optional | `x?` | `[x]` or `*1x` | `x?` |
| Zero-or-more | `x*` | `*x` | `x*` |
| One-or-more | `x+` | `1*x` | `x+` |
| Exact count | `x{m}` | `mx` | (not standard) |
| Range | `x{m,n}` | `m*nx` | (not standard) |
| String case | case-sensitive | case-insensitive | case-sensitive |
| Numeric escape | `\xNN` | `%xNN` | (depends) |
| Comment | `#` | `;` | `//` or `#` |
| Start rule convention | `root` | none | none |

---

## Key capabilities Lexic does not currently have

> [!note]
> These are gaps relative to the formal specifications of the grammar formats Lexic supports, current as of the 2026-07 Lark→Earley cutover (both GBNF and ABNF self-grammars reached full historical-Lark parity — see the per-format gap sections above for what's newly supported).

### GBNF gaps

- **Token-level nodes** (`<[id]>`, `<token>`, `!<token>`) — no `IrNode` type; `UnsupportedConstructError` (or a bare engine parse failure) at parse time.
- **Enforced `root` start convention** — the engine uses a positional fallback and `@start` directives; it does not enforce or warn when `root` is absent.

### ABNF gaps

- **Value-sequences within `%d`/`%b`** (e.g. `%d13.10`) — unsupported (parity gap, flagged to the user, not yet resolved).
- **Uppercase markers** (`%X`, `%D`, `%B`, `%S`, `%I`) — only lowercase accepted (parity gap, flagged to the user, not yet resolved).
- **Core rule library** — `ALPHA`, `DIGIT`, `WSP`, etc. must be hand-defined in every grammar; `CORE_RULES` in `abnf.py` is dead data.
