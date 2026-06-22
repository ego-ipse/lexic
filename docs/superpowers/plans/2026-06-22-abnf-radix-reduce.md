# ABNF Radix Reduce — Pure Numeric Reductions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three procedural `IrLambda` reductions in `ABNF_REDUCTIONS` (`_num_val`, `_repeat`, `_repetition`) — and their `ABNF_FLAVOUR.parse_charclass`/`parse_quantifier` calls — with pure `IrSelf` algebra driven by the already-built `IrUnradix` decoder, restructuring `ABNF_GRAMMAR`'s numeric rules so each digit run and optional bound is its own named rule.

**Architecture:** The reduce direction becomes 100% pure `IrSelf`. `ABNF_GRAMMAR` splits `num-val` → `num-single`/`num-range` and `repeat` → `repeat-exact`/`repeat-range`, wraps each digit run in `hexits`/`decits` (so it reduces to one joined string) and each optional bound in a named `lo-bound`/`hi-bound`/`repeat-opt` rule (so the slot always materialises). The reduce table decodes each clean digit string with `IrUnradix(base, out)` and builds the typed node with `IrBuild`. Correctness is gated by the existing ABNF self-hosting fixpoint, which holds because decoded `IrInt`/`IrChr` leaves compare equal to authored plain-int/`IrChr` endpoints via the type-aware `IrBounds.__eq__`/`IrScalar.__eq__`.

**Tech Stack:** Python 3.13, pytest, pyright, pylint, `uv`. The shapes and reduce table are lifted from the validated prototype `_validate_radix.py` (see `docs/superpowers/specs/2026-06-20-radix-decode-design.md` §Reduce table).

---

## Scope & context (read first)

This is **step 1** of the radix follow-on (`docs/superpowers/specs/2026-06-20-radix-decode-design.md` items 5 & 6 / `2026-06-18-flavour-2-reduce-handover.md` item B), sequenced inside the wider `parsing` → `parsing_2` cutover (`plans/flavour-2-lark-cutover/flavour_2-handover.md`, Phase 1 numeric algebra + the numeric slice of Phase 3).

- **In scope:** `src/lexic/grammars/abnf_2.py` (the `ABNF_GRAMMAR` numeric rules + the `ABNF_REDUCTIONS` table + deleting `_num_val`/`_repeat`/`_repetition`) and its mirror test `tests/unit/lexic/grammars/test_abnf_2.py`.
- **Out of scope (separate follow-on):** the emit-side `IrRadix` + `_abnf_charclass` removal (step 2); the `flavour_2` container and table-shape decision (cutover Phase 2); `gbnf_2.py` (cutover Phase 3).
- **Coupling:** grammar and reductions change together — `ABNF_GRAMMAR` and `ABNF_REDUCTIONS` are a matched pair under the self-hosting fixpoint. There is no partial green state, so this is **one task**, TDD'd against hand-built and parse-based tests with the fixpoint as the final gate.

**Commit policy:** This project's commits belong entirely to the user. The task ends with a **Stage** step (`git add`) — do **not** run `git commit`, and never add a `Co-Authored-By` line.

**Verification is repo-wide** (per the user): the task is done only when `bash tools/run_checks.sh` and `uv run pytest tests/ -q` are both fully green.

---

## Why the restructure (the mechanism)

The procedural reductions exist because the old grammar scattered digits and folded optionality into a single rule, so a pure body had nowhere to read a clean value from. The restructure removes both obstacles:

- **`hexits = 1*HEXDIG` / `decits = 1*DIGIT`** — wrapping the digit run in its own rule means its reduction (`IrJoin(IrArgs())`) collapses the scattered single-char args into **one** `IrStr` per slot, so a sibling rule reads it positionally with `IrArg(n)`.
- **`num-val = num-single / num-range`, `repeat = repeat-exact / repeat-range`** — splitting the arms kills the `5` vs `5*` vs `*5` and `%x41` vs `%x41-5A` discriminator-by-presence-of-`*`/`-`; the reducer dispatches on the **rule name** instead. Single-link (unambiguous) parsing is preserved — for any complete input exactly one arm yields a full parse (validated in the prototype).
- **`lo-bound = [decits]`, `hi-bound = [decits]`, `repeat-opt = [repeat]`** — each optional bound becomes a **named** rule, so it always appears as a child of its parent and always reduces, even when it matched empty. An empty match leaves the rule's `nc` empty; `IrCond(test=IrArgs(), …)` reads that as falsy and supplies the default (`IrInt(0)` for `lo`, `IrNone` for `hi`, a built `IrQuantifier()` for `repeat-opt`). This is what lets `repetition` be a purely positional `IrBuild(IrItem, (atom, quant))` instead of the type-selecting `_repetition`.

The fixpoint holds across the count/codepoint divide because decoded leaves are `IrInt`/`IrChr` while authored endpoints are plain `int`/`IrChr`, and `IrScalar.__eq__` makes `IrInt(5) == 5` while `IrBounds.__eq__` keeps a count range and a code-point range unequal.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/lexic/grammars/abnf_2.py` | ABNF-as-IR grammar + reduce table | **Restructure** numeric rules; **rewrite** `ABNF_REDUCTIONS`; **delete** `_num_val`/`_repeat`/`_repetition`; fix imports |
| `tests/unit/lexic/grammars/test_abnf_2.py` | mirror of `abnf_2.py` | **Port** the two `num-val` unit tests to the new rule shape; **add** repeat/bound parse-based tests; keep the fixpoint tests |

---

## Task 1: Pure numeric reductions + grammar restructure

**Files:**
- Modify: `src/lexic/grammars/abnf_2.py`
- Test: `tests/unit/lexic/grammars/test_abnf_2.py`

- [ ] **Step 1: Port the two `num-val` unit tests and add the new parse-based tests (failing)**

In `tests/unit/lexic/grammars/test_abnf_2.py`, ensure the imports include `IrInt` from `lexic.ir.base` (alongside the existing `IrSeq`) — change the line `from lexic.ir.base import IrSeq` to:

```python
from lexic.ir.base import IrInt, IrSeq
```

**Port** `test_num_val_hex_range_yields_ircharclass_range` and `test_num_val_single_hex_yields_ircharclass_str` (current lines 155-184). The numeric work now lives in `num-single`/`num-range` reducing over a `hexits` sub-tree, and the `%`/`x`/`-` literals are dropped by `literal=DROP`, so they must use `ABNF_REDUCER` (not the default-policy `Reducer`). Replace both functions with:

```python
def test_num_single_yields_ircharclass_chr():
    """num-single over a hexits subtree yields IrCharClass(IrChr('A'))."""
    hexits = ParseTree(IrRuleRef("hexits"), IrSeq(IrLiteral("4"), IrLiteral("1")))
    tree = ParseTree(
        IrRuleRef("num-single"),
        IrSeq(IrLiteral("%"), IrLiteral("x"), hexits),
    )
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrChr("A"))


def test_num_range_yields_ircharclass_range():
    """num-range over two hexits subtrees yields IrCharClass(IrRange('A','Z'))."""
    lo = ParseTree(IrRuleRef("hexits"), IrSeq(IrLiteral("4"), IrLiteral("1")))
    hi = ParseTree(IrRuleRef("hexits"), IrSeq(IrLiteral("5"), IrLiteral("A")))
    tree = ParseTree(
        IrRuleRef("num-range"),
        IrSeq(IrLiteral("%"), IrLiteral("x"), lo, IrLiteral("-"), hi),
    )
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrRange(IrChr("A"), IrChr("Z")))
```

**Add** these parse-based tests (exercising the real empty-optional mechanism end to end). Put them just after `test_parse_reduce_charclass_rule` (current line 230):

```python
def _quant_of(text: str) -> IrQuantifier:
    """Parse a one-rule ABNF snippet and return its single item's quantifier."""
    g = _normalize(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, text))
    assert isinstance(result, IrAst)
    return list(list(result.rules)[0].body)[0][0].quantifier


def test_repeat_exact_quantifier():
    """'5\"a\"' → IrQuantifier(5, 5)."""
    assert _quant_of('x = 5"a"\n') == IrQuantifier(5, 5)


def test_repeat_range_quantifier():
    """'1*5\"a\"' → IrQuantifier(1, 5)."""
    assert _quant_of('x = 1*5"a"\n') == IrQuantifier(1, 5)


def test_repeat_open_upper_quantifier():
    """'5*\"a\"' → IrQuantifier(5, IrNone) — empty hi-bound is unbounded."""
    assert _quant_of('x = 5*"a"\n') == IrQuantifier(5, IrNone)


def test_repeat_open_lower_quantifier():
    """'*5\"a\"' → IrQuantifier(0, 5) — empty lo-bound is zero."""
    assert _quant_of('x = *5"a"\n') == IrQuantifier(0, 5)


def test_repeat_star_quantifier():
    """'*\"a\"' → IrQuantifier(0, IrNone) — both bounds empty."""
    assert _quant_of('x = *"a"\n') == IrQuantifier(0, IrNone)


def test_repeat_absent_defaults_to_one_one():
    """No repeat prefix → repeat-opt defaults to IrQuantifier(1, 1)."""
    assert _quant_of('x = "a"\n') == IrQuantifier(1, 1)


def test_num_single_parse_reduce():
    """'x = %x41' reduces to IrCharClass(IrChr('A'))."""
    g = _normalize(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, "x = %x41\n"))
    assert isinstance(result, IrAst)
    item = list(list(result.rules)[0].body)[0][0]
    assert item.atom == IrCharClass(IrChr("A"))
```

`IrNone` is already imported in the test file via `from lexic.ir.nodes import (...)`? It is not — add it. Ensure the `from lexic.ir.nodes import (...)` block includes `IrNone`. If `IrNone` lives in `lexic.ir.base`, import it from there instead; confirm with `uv run python -c "from lexic.ir.nodes import IrNone"` — if that errors, use `from lexic.ir.base import IrInt, IrNone, IrSeq`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/lexic/grammars/test_abnf_2.py -q`
Expected: FAILures — the ported `num-single`/`num-range` tests error (grammar/reductions still on the old shape) and the new repeat tests fail (no `repeat-exact`/`repeat-range`/`repeat-opt` rules yet; quantifiers come back wrong). The fixpoint tests still pass at this point (old grammar + old reductions are internally consistent).

- [ ] **Step 3: Restructure the numeric rules in `ABNF_GRAMMAR`**

In `src/lexic/grammars/abnf_2.py`, **replace** the `repetition` rule (current lines 156-164), the `repeat` rule (current lines 165-175), the `num-val` rule (current lines 218-228), and the `rangerest` rule (current lines 229-237) with the following rules. (Leave every other rule — `rulelist`, `rule`, `rulename`, `namechar`, `alternation`, `altrest`, `concatenation`, `catrest`, `element`, `group`, `char-val`, `vchar-nq`, `c-nl`, `wsp`, `ALPHA`, `DIGIT`, `HEXDIG`, `CR`, `LF`, `SP`, `HTAB`, `DQUOTE` — exactly as they are.)

```python
        IrRule(
            "repetition",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("repeat-opt")),
                    IrItem(IrRuleRef("element")),
                )
            ),
        ),
        IrRule(
            "repeat-opt",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("repeat"), IrQuantifier(0, 1)))
            ),
        ),
        IrRule(
            "repeat",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("repeat-exact"))),
                IrSequence(IrItem(IrRuleRef("repeat-range"))),
            ),
        ),
        IrRule(
            "repeat-exact",
            IrAlternation(IrSequence(IrItem(IrRuleRef("decits")))),
        ),
        IrRule(
            "repeat-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("lo-bound")),
                    IrItem(IrLiteral("*")),
                    IrItem(IrRuleRef("hi-bound")),
                )
            ),
        ),
        IrRule(
            "lo-bound",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))
            ),
        ),
        IrRule(
            "hi-bound",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("decits"), IrQuantifier(0, 1)))
            ),
        ),
        IrRule(
            "decits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("DIGIT"), IrQuantifier(1, IrNone)))
            ),
        ),
```

And, for the `num-val` family, insert:

```python
        IrRule(
            "num-val",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("num-single"))),
                IrSequence(IrItem(IrRuleRef("num-range"))),
            ),
        ),
        IrRule(
            "num-single",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrLiteral("x")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "num-range",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("%")),
                    IrItem(IrLiteral("x")),
                    IrItem(IrRuleRef("hexits")),
                    IrItem(IrLiteral("-")),
                    IrItem(IrRuleRef("hexits")),
                )
            ),
        ),
        IrRule(
            "hexits",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("HEXDIG"), IrQuantifier(1, IrNone)))
            ),
        ),
```

Order within `IrSeq(...)` does not matter for correctness (rule lookup is by name), but keep `repetition` where it was and group the new `repeat*`/bound rules and the new `num*`/`hexits`/`decits` rules near it for readability.

- [ ] **Step 4: Rewrite `ABNF_REDUCTIONS`, delete the procedural functions, fix imports**

4a. **Fix the imports.** Replace the three import lines (current lines 56-61) so that `Sequence` and `ABNF_FLAVOUR` (only used by the deleted functions) are gone, `IrLambda`/`IrAtom` (only used by the deleted functions) are gone, and the new algebra nodes (`IrArgs`, `IrCond`, `IrJoin`, `IrUnradix`) plus `IrInt` are added:

```python
from lexic.ir.action import (
    IrArg,
    IrArgs,
    IrBuild,
    IrCond,
    IrField,
    IrJoin,
    IrPipe,
    IrUnradix,
)
from lexic.ir.base import IrInt, IrNone, IrSelf, IrSeq, IrTuple
from lexic.ir.mapping import IR_DEFAULT, IrMap
```

(`from __future__ import annotations` stays; delete the now-orphaned `from typing import Sequence` line and the `from lexic.grammars.abnf import ABNF_FLAVOUR` line.)

4b. **Delete** the three procedural functions `_num_val`, `_repeat`, `_repetition` (current lines 304-331) and their `# ── Procedural reductions … ──` banner comment.

4c. **Add the decode helpers and rewrite the table.** Replace the entire `ABNF_REDUCTIONS = IrMap(...)` block (current lines 336-361) with:

```python
# ── Decode helpers: hex code points off args; joined decimal count ────────

_cp0 = IrPipe(IrArg(0), IrUnradix(16, IrChr))
"""First hex digit-run arg → an ``IrChr`` code point."""
_cp1 = IrPipe(IrArg(1), IrUnradix(16, IrChr))
"""Second hex digit-run arg → an ``IrChr`` code point."""
_dec = IrPipe(IrJoin(IrArgs()), IrUnradix(10, IrInt))
"""Joined decimal digit-run args → an ``IrInt`` count."""


# ── Reductions: structural rules build from clean nc, text rules yield ─────

# Dyads in an annotated tuple so each value widens to ``IrSelf`` (the invariant
# ``IrTuple`` would otherwise reject the heterogeneous bodies under ``IrMap``).
ABNF_REDUCTIONS: IrMap[IrRuleRef, IrSelf] = IrMap(
    IrTuple(
        IrRuleRef("rulelist"),
        IrBuild(IrAst, IrTuple(IrBuild(IrSeq), IrPipe(IrArg(0), IrField("name")))),
    ),
    IrTuple(IrRuleRef("rule"), IrBuild(IrRule)),
    IrTuple(IrRuleRef("alternation"), IrBuild(IrAlternation)),
    IrTuple(IrRuleRef("altrest"), IrArg(0)),
    IrTuple(IrRuleRef("concatenation"), IrBuild(IrSequence)),
    IrTuple(IrRuleRef("catrest"), IrArg(0)),
    # repetition: repeat-opt is child 0, element is child 1 → IrItem(atom, quant).
    IrTuple(IrRuleRef("repetition"), IrBuild(IrItem, IrTuple(IrArg(1), IrArg(0)))),
    # repeat-opt: present → forward the quantifier; empty → a built default (1,1).
    IrTuple(
        IrRuleRef("repeat-opt"),
        IrCond(
            test=IrArgs(),
            then_op=IrArg(0),
            else_op=IrBuild(IrQuantifier, IrTuple()),
        ),
    ),
    IrTuple(IrRuleRef("repeat"), IrArg(0)),
    IrTuple(
        IrRuleRef("repeat-exact"),
        IrBuild(
            IrQuantifier,
            IrTuple(
                IrPipe(IrArg(0), IrUnradix(10, IrInt)),
                IrPipe(IrArg(0), IrUnradix(10, IrInt)),
            ),
        ),
    ),
    IrTuple(
        IrRuleRef("repeat-range"),
        IrBuild(IrQuantifier, IrTuple(IrArg(0), IrArg(1))),
    ),
    # bounds own their own emptiness: IrArgs() is falsy when the rule matched empty.
    IrTuple(
        IrRuleRef("lo-bound"),
        IrCond(test=IrArgs(), then_op=_dec, else_op=IrInt(0)),
    ),
    IrTuple(
        IrRuleRef("hi-bound"),
        IrCond(test=IrArgs(), then_op=_dec, else_op=IrNone),
    ),
    # digit-run rules: join the scattered single-char args into one string.
    IrTuple(IrRuleRef("decits"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("hexits"), IrJoin(IrArgs())),
    IrTuple(IrRuleRef("element"), IrArg(0)),
    IrTuple(IrRuleRef("group"), IrArg(0)),
    # Text rules — wrap the subtree text as the leaf type (quotes skipped).
    IrTuple(IrRuleRef("rulename"), IrBuild(IrRuleRef, IrTuple(YIELD))),
    IrTuple(IrRuleRef("char-val"), IrBuild(IrLiteral, IrTuple(YIELD))),
    # num-val → IrCharClass over code points (IrChr endpoints).
    IrTuple(IrRuleRef("num-val"), IrArg(0)),
    IrTuple(IrRuleRef("num-single"), IrBuild(IrCharClass, IrTuple(_cp0))),
    IrTuple(
        IrRuleRef("num-range"),
        IrBuild(IrCharClass, IrTuple(IrBuild(IrRange, IrTuple(_cp0, _cp1)))),
    ),
    IrTuple(IR_DEFAULT, YIELD),
)
"""Per-rule reductions: parse tree → IR. Numeric rules decode their clean digit
runs with :class:`~lexic.ir.action.IrUnradix`; structural rules build from clean
``nc``; every char/terminal rule falls through ``IR_DEFAULT`` to :data:`YIELD`.
Paired with :data:`ABNF_NOISE`."""
```

4d. **Update the module docstring.** The final paragraph ("**Why some reductions stay procedural.**", current lines 42-51) is now false — the numeric reductions are pure. Replace that paragraph with:

```
**Every reduction is pure ``IrSelf``.** Text rules (the character/terminal rules)
reduce with the shared :data:`YIELD`. Structural rules build typed nodes from
clean ``nc`` with :class:`~lexic.ir.action.IrBuild`. The numeric rules decode
their digit runs with :class:`~lexic.ir.action.IrUnradix` (the inverse of the
emit-side radix spelling) and build over code points — no ``parse_charclass`` /
``parse_quantifier`` call remains on the reduce side.
```

- [ ] **Step 5: Run the abnf_2 tests (unit + parse-based + fixpoint)**

Run: `uv run pytest tests/unit/lexic/grammars/test_abnf_2.py -q`
Expected: PASS — all tests in the file, including the ported `num-single`/`num-range` unit tests, the new repeat/bound parse-based tests, and **the self-hosting fixpoint** (`test_self_hosting_fixpoint`, `_idempotent`, `_crlf_reduces_to_abnf_grammar`). If the fixpoint fails, a red localizes the offending rule — compare the reduced `IrAst` against `ABNF_GRAMMAR` rule by rule; the usual culprit is a bound rule's empty-match path or a digit-run not joining.

- [ ] **Step 6: Per-file quality gate**

Run: `uv run pyright src/lexic/grammars/abnf_2.py && uv run pylint src/lexic/grammars/abnf_2.py`
Expected: pyright `0 errors`; pylint `10.00/10`. If pylint flags an unused import, it is one of the removed names — confirm it is truly unused with `grep` before deleting (do not add a suppression). If formatting drifts, run `tools/auto_fix.sh` first.

- [ ] **Step 7: Repo-wide verification**

Run: `bash tools/run_checks.sh && uv run pytest tests/ -q`
Expected: all four checks green (sanity, ruff lint+format, pyright, pylint) and the full suite passes. `IrUnradix` is no longer dead code — it now has a live consumer. No out-of-scope module should regress (this change is confined to `abnf_2.py`).

- [ ] **Step 8: Stage (do not commit)**

```bash
git add src/lexic/grammars/abnf_2.py tests/unit/lexic/grammars/test_abnf_2.py
```
Suggested commit message (user runs): `refactor(abnf): pure radix reductions, drop parse_charclass/parse_quantifier`

---

## Final verification (repo-wide)

- [ ] **Confirm the reduce side is `IrLambda`-free for numerics and `IrUnradix` is wired**

Run: `grep -n "IrLambda\|parse_charclass\|parse_quantifier\|_num_val\|_repeat\|_repetition" src/lexic/grammars/abnf_2.py`
Expected: no matches (the procedural numeric reductions and their callers are gone).

Run: `grep -rn "IrUnradix" src/lexic/grammars/abnf_2.py`
Expected: matches in the decode helpers and `repeat-exact` (the node is now consumed).

- [ ] **Full gate**

Run: `bash tools/run_checks.sh && uv run pytest tests/ -q`
Expected: all green.

> **Next (separate plan, out of scope here):** the emit-side `IrRadix` + `_abnf_charclass` removal (step 2), then the `flavour_2` container + table-shape decision (cutover Phase 2) before authoring `gbnf_2.py`.
