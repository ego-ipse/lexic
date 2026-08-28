# Prototype 6 — exact source contracts and corrected REVIEW_7 evidence

**Phase:** post-`PROTOTYPE_5` consistency iteration. `src` remains unchanged.
The work is confined to `proto/` and the active planning documents.

**Supersession note (2026-08-29):** `PROTOTYPE_7.md` makes public morphisms
declaration-only, replaces the public map-shape witness with private shape
analysis, strengthens regular-region proof and derivation, rejects §3's
child-local rule, and replaces §4's odd-pair collector row with an even run.
The measurements below remain provenance only.

## 1 — reducer-free selection needs a third overload

`proto/reducer_free_surface.py` pins three non-overlapping forms of the one
`CompiledGrammar.reduce` execution seam:

```python
reduce(text, reducer, *, resolve, cores) -> IrSelf
reduce(text, reducer, *, into=ReductionMorphism[T], resolve, cores) -> T
reduce(text, *, into=GrammarMorphism[T], resolve, cores) -> T
```

The third form is required: `select_raw` has no reducer or semantic signature,
so the two reducer-required overloads in the previous DESIGN could not call it.
The prototype also makes raw capture a typed declaration: default `MODEL`
capture returns `RawSelection[GrammarModel]`; `capture=EXTENT` returns
`RawSelection[CertifiedExtent]`. No boolean execution mode or result union is
needed. Pyright infers all four exercised result types exactly.

`select_raw` is not meaningful over literally every compiled grammar. Its
source is every compiled grammar whose named entry has the compatible recursive
key/value mapping shape derivable from binding data. The demand prototype uses
`MapShape.for_entry` to establish exactly that precondition. Documents and the
future ex10 wording now state the compatible shape rather than overclaiming.

## 2 — regular-region identity now covers the missing dimensions

`proto/regular_region_lowering.py --mode identity` now proves:

- the recursive closure still declines;
- native, GBNF, ABNF, and EBNF JSON formulations capture identical rows;
- 1-, 2-, and 3-field demand produces the corresponding capture arity;
- the complete Qwen vocabulary capture equals the existing expected table and
  ends at the exact following shell boundary;
- `{}` is a valid empty region;
- missing values, trailing separators, and missing key/value separators refuse;
- the original 4,000-entry slice still equals stdlib JSON and generic Lexic
  reduction.

The command prints:

```text
entries 4000
slice_chars 79207
identity native == gbnf == abnf == ebnf == json == engine reduce
edges 1/2/3 captures; empty valid; malformed refused
```

This closes the prototype's two-capture/formulation edge. Production still owes
property-scale invalid-input differential, composed entry/exit certification,
and actual engine integration. The 0.368907 s `ops` row remains an optimistic
microkernel: it omits frames, transactions, the PDA driver, the merge region,
and the rest of the document. It does not prove the complete <1.000 s gate.

## 3 — historical child-local rule, rejected after REVIEW_8

`proto/local_meaning_fold.py` now exercises a native start rule with two
separate accepting items. Different root meanings refuse and equal root
meanings agree, each at four fold-body executions across the two tiny roots.
The existing internal distant-point witness remains 4 child-local folds versus
2,414 root-rooted folds.

The resulting rule was two-part, but its first part is unsound and no longer
belongs to the design:

- internal packed-family ambiguity comparing only differing child meanings is
  rejected by the dropping-parent counterexample;
- separate accepting root items require one complete fold per root, because no
  internal packed point contains that choice.

`resolve=` remains the existing derivation resolver. A predictive ambiguity
must bail before target-state commit; Earley supplies the complete derivation
pair, and only the chosen derivation constructs the final target product.
`PROTOTYPE_7.md` preserves that contract by replaying the dirty
completed-handle ancestor cone to the complete root meaning instead.

## 4 — order correction, later superseded by an even-pair run

`proto/carrier_gc_cost.py` previously ran enabled then disabled in every pair.
The revised probe alternates pair order, forces the requested state before the
clock, restores the prior state afterwards, collects between rows, and reports
the median within-pair delta.

One isolated invocation, eight retained workers, seven pairs:

| collector | process CPU median | wall median |
|---|---:|---:|
| enabled | 0.705460 s | 0.140949 s |
| disabled | 0.704488 s | 0.137130 s |

Median paired enabled-minus-disabled:

| quantity | delta |
|---|---:|
| process CPU | +0.005439 s |
| wall | +0.005182 s |

The prior +0.016948 s / ~11% fixed-order claim is rejected. Because seven pairs
are not order-balanced, this row is not the final toggle measurement.
`PROTOTYPE_7.md` records eight alternating pairs and makes the GC-enabled
carrier row the headline. The production ruling remains: acceptance
measurements run with GC enabled, compare equal GC states, and never manipulate
GC in `src`.

## Verification

Executed serially, with no agent or overlapping benchmark process:

```text
uv run pyright <six relevant prototypes>
0 errors, 0 warnings, 0 informations

uv run python proto/reducer_free_surface.py
surface  three exact overloads  model/extent codomains remain exact

uv run python proto/local_meaning_fold.py
root-siblings  accepting_items=2  different_folds=4  same_folds=4

uv run python proto/regular_region_lowering.py --mode identity
identity  native == gbnf == abnf == ebnf == json == engine reduce
edges  1/2/3 captures; empty valid; malformed refused
```

The order-balanced collector command was the only multithreaded benchmark and
owned the machine for its complete preparation/warm/timing/shutdown lifetime.
