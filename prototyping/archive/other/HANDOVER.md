# Handover — 2026-06-14

Working tree is **clean** (HEAD `85e0687 moree`). Everything below about the
codepoint work was prototyped and **git-restored** by the user — none of it is
on disk. Read it as a design record, not as code to find.

## Committed this session (in `b7483d6` / `85e0687`)

1. **ABNF emission declarativized.** `_abnf_encode_literal`, `_abnf_item`,
   `_abnf_ast` → declarative action bodies matching GBNF. The prefix quantifier
   is now `ABNF_PREFIX_QUANTIFIER`, an **`IrMap` with an `IR_MAP_DEFAULT`
   fallback** (two exact specials `(1,1)→""`, `(0,∞)→"*"` shared with
   `GBNF_QUANTIFIERS`; everything else falls through to a nested `IrCond`).
   Only remaining ABNF `IrCallable` is `_abnf_charclass` (hex).
2. **`IR_MAP_DEFAULT`** (`ir/mapping.py`): a catch-all sentinel **key** for
   `IrMap`/`IrTypeMap`. Registered ⇒ `resolve` falls back on a miss; absent ⇒
   still raises. `__getitem__`/`__contains__` stay explicit-key. `IrMap.__new__`
   got an overload pair so a heterogeneous sentinel dyad type-checks without
   `IrMap[IrSelf, IrSelf]` (which the user forbade).
3. **Metaclass consolidation** (`ir/meta.py`): `IrMeta` moved there from
   `base.py`; new `IrSingleton(Singleton, IrMeta)`. `IrNoneType` and
   `_IrMapDefault` now use `metaclass=IrSingleton` — hand-rolled singleton
   `__new__` gone. Full coverage in `tests/unit/lexic/ir/test_meta.py`.

All committed work was green: pytest, pyright, pylint, ruff.

## The live design thread: codepoint char-ranges (NOT implemented)

Goal: make `_abnf_charclass` declarative and unify char-ranges with quantifier
bounds. The agreed model (verified, sound):

- **A char-range endpoint is a codepoint.** Store `IrRange(IrInt, IrInt)` — the
  decoded codepoint, not the source spelling. `a`, `\x61`, `%x61` all → `97`.
- **Parse decodes** (escape handling is a parsing concern); **flavour encodes**
  on emit. ABNF range → `%x` + base-16 of the codepoint (no `ord`, "just a base
  change"). GBNF range → `chr`/escape of the codepoint.
- **`IrRange` is FIXED ARITY** — an `IrNamedTuple[IrInt, IrInt | IrNoneType]`,
  NOT a variadic `IrSeq`/vector. (User rejected the vector hard.) `lo`/`hi`
  become dispatchable children (drop the `IrLeaf` mixin and `_child_attrs = ()`).
  Coercing `__new__`: single-char `str` → `ord`, plain `int` → as-is.
- **`IrQuantifier(IrRange)`** stays int bounds (counts, not codepoints), no-arg
  default `(1,1)`. After the flip `IrQuantifier(1,1) != IrRange(1,1)` (IrInt vs
  IrStr historically) — that disjointness is *wanted*.

### Verified facts that unblock it
- **No test asserts grammar-source byte-exact round-trip.** The North Star /
  property round-trip is **instance-level** (`parse(text,g).to_text()==text`),
  which is codepoint-level and indifferent to charclass spelling. So storing
  codepoints (canonical-form re-emit) is allowed; my earlier "byte-exact blocks
  it" objection was about an untested non-requirement.
- Today's storage (baseline): GBNF keeps the **verbatim source unit** as a str
  (`IrRange('\\x00','\\x1F')`, 4-char strings); ABNF keeps a **decoded char**
  (`%x61`→`'a'`). Inconsistent across flavours — symptom of escape handling
  leaking into the IR.
- `str(IrInt(4))` returns `"IrInt(4)"`, NOT `"4"` (int has no `__str__`, so
  `str` falls through to the codegen `__repr__`). The codepoint flip needs
  `IrInt.__str__` returning `int.__repr__(self)`. This is a real latent bug.
- `charclass_pattern` (`utils/charclass.py`) is the single flat-view chokepoint
  feeding `lark_builder`, `generate`, `derive`. If it re-encodes codepoints to
  the same canonical text, those consumers don't change.

### The blocker that ended the session: the encoder placement
ABNF hex is a base change, but you still need a **codepoint → surface** encoder
for GBNF (`chr`/escape) and the flat view. Hard constraints the user enforced:

- **NO cross-module utility imports** (a flavour importing `utils.charclass` =
  "ugly ass imports", instant restore). Encoding must live on something the
  flavour already holds. See memory `feedback_no_cross_module_util_imports`.
- **The old `EscapeCodec` is rejected** as the home — user: "the old escape
  codec is shit. We need a new `IrEscape`." Do NOT extend `EscapeCodec`.
- The user wants a **new `IrEscape`** (the action leaf) that owns escaping —
  almost certainly carrying its escape mapping as *payload* (an `IrMap`?) rather
  than pulling `d.escapes`, operating on a codepoint `IrInt` and returning
  `IrStr`. **The exact skeleton was never specified** — that is the open
  question. Get it from the user before writing anything.

## Rejected approaches (do not retry)
- `IrVector[T](IrSeq[...])` variadic base for ranges — ranges are fixed arity.
- `IrScalar.__str__` override — recursion (`__format__("")` re-enters `__str__`).
  Fix is `IrInt.__str__` only.
- `IrDefaultMap` subclass — user wanted `IR_MAP_DEFAULT` sentinel on plain
  `IrMap`/`IrTypeMap` instead (this one shipped).
- A flavour importing an `encode_codepoint` helper from `utils`.

## Other open items (pre-existing, from prior handover)
- `_abnf_charclass` hex callable (the whole point of the codepoint thread).
- Parse-side flavour methods (`parse_quantifier`/`parse_charclass`/
  `normalize_literal`) — die with the IR-native parser (blocked step 4, needs a
  design session). `parse_quantifier` cannot be removed yet (load-bearing).
- CLAUDE.md / `.wiki/` stale.

## Workflow notes for the next agent
The user iterates on **mechanism** fast and restores aggressively when the
structure is wrong or ugly. **Do not implement large multi-file changes on a
guess** — pin the exact node/class shape with them first, then build. Tests go
to Sonnet subagents (ask first). Never commit autonomously.
