# Prototype 7 — root-equivalent ambiguity and authoritative regular regions

**Phase:** REVIEW_8 correction loop. `src` remains unchanged. This pass rejects
the child-local ambiguity ruling, strengthens the regular proof, derives region
inputs from semantic roles, and corrects the remaining toggleable measurements.

## 1 — root value is preserved without a second whole-document fold

`proto/local_meaning_fold.py` remains the counterexample: its dropping-parent
row is cheap locally but refuses two derivations whose complete products are
equal. Child-local meaning is therefore rejected as the ambiguity relation.

`proto/root_meaning_incremental.py` instead folds the default derivation once,
indexes completed-handle dependencies, and evaluates an alternate by replaying
only the dirty completed handles from its packed family to the root. Every
unchanged sibling meaning comes from the read-only baseline memo; each
alternate writes a sparse overlay and never copies that document-sized table.
Meaning programs are indexed by completed code, not rule name, so future
occurrence clones select their own completion range directly.

The real Earley-kernel witnesses print:

```text
kept-difference  differs=True   baseline_folds=3     alternate_folds=3
dropping-parent  differs=False  baseline_folds=3     alternate_folds=3
same-meaning     differs=False  baseline_folds=3     alternate_folds=3
distant-point    differs=True   baseline_folds=1207  alternate_folds=3
```

This preserves the existing root-value language, including the dropping-parent
case, while alternate **fold-body execution** follows the ambiguity's ancestor
cone rather than document size. That count does not by itself price flattening
or equality for an eager target container.

`proto/persistent_meaning.py` closes that representation gap for sequence-like
products without a probabilistic digest. It retains an immutable balanced
contribution tree, path-copies one changed leaf, skips identity-shared branches
during exact iterative equality, and materializes the selected eager result
once. Over 65,536 leaves it visits 18 nodes for a changed value, 33 for an equal
path-copied value, and one for a parent-dropped singleton; only the chosen value
is flattened. This is the production shape for built-in accumulators. A target
which cannot provide an exact shareable meaning may pay a full cold ambiguity
comparison, but may not put witness state on the unambiguous hot path or use a
collision-prone digest as equality.

Separate accepting root items still require one complete meaning construction
per root because they have no common internal packed point. Production owes the
same dependency index over its flat completion ranges and the existing resolver
still receives complete derivations only after a different root meaning exists.

## 2 — the authoritative regular proof is stronger than scanner admission

`proto/regular_region_proof.py` adds the missing sufficient conditions for
reusing atomic/possessive pattern sources as an authoritative interior:

- the reachable closure is simple and acyclic;
- authored arms have disjoint first-character sets and at most one nullable
  arm;
- a variable repetition cannot consume a character owned by its continuation;
- repeated atoms are non-nullable; and
- entry and separator-entry concatenations are boundary-deterministic against
  both the next separator and the terminator.

The surrounding parser owns the opener and terminator. The delegated fast path
starts after the opener and stops before the terminator; it does not promote the
scanner's fail-soft shell recognition into an authoritative answer.

The existing recursive witness declines. A new acyclic/simple witness,
`lead ::= "a"*` followed by `tail ::= "a"`, passes `build_recognizer` but
declines the stronger proof because possessive `lead` would steal `tail`'s
character. The JSON vocabulary continues to pass and remains differential with
the generic engine.

## 3 — region discovery is signature × demand composition

`regular_region_lowering.py` no longer constructs the vocabulary `RegionSpec`
directly. A reducer-authored `RegionSignature` maps semantic field roles onto
lower entry positions; a target `RegionDemand` names roles; `_derive_region`
composes them into the grammar-specific program. Rule names remain on the
signature's lower side and never enter the target declaration or runtime paid
loop.

The identity witness now includes a non-JSON catalog language with different
rules and delimiters:

```text
entries   4000
identity  native == gbnf == abnf == ebnf == json == engine reduce
edges     1/2/3 captures; empty valid; malformed refused; ambiguous declined
derived   JSON vocab + non-JSON catalog
```

This is an executable derivation mechanism, not a production proof over every
grammar. Production ownership belongs in `compile/product/compose.py`, with the
authoritative regular proof in `parsing/product/regular.py`; an unproved region
stays on the same interpreted product rather than guessing a boundary.

## 4 — the toggleable interpreted/capture ratio is now in-process

`regular_region_lowering.py --mode compare --rounds 8` alternates `capture` and
`ops` in one process, takes minima, and carries two labels executing the same
capture body as the unreachable control.

| row | process CPU minimum | wall minimum |
|---|---:|---:|
| whole-entry capture | 0.246319 s | 0.246350 s |
| one recognizer consult per rule + int ops | 0.351784 s | 0.351812 s |
| control left | 0.251292 s | 0.251314 s |
| control right | 0.250163 s | 0.250197 s |

The process-CPU ratio is **1.428162x** and the control CPU floor is 0.001129 s
(about 0.46% of capture), so the interpreted/capture difference is material.
The interpreted row still assumes one exact compiled-recognizer consult per
eligible value-string rule occurrence. It is evidence only if that generic
specialization is an explicit implementation task; it is not the shipped
per-character PDA loop and is not a complete `<1.000 s` result.

## 5 — public declarations stay inert; routing does not consume `resolve=`

`proto/reducer_free_surface.py` keeps the three exact overloads but removes
`run` from both public morphism classes. They are immutable declaration tuples;
only a private `_BoundProduct[Result]` contains an executor. The executable
witness binds Python and extent declarations privately while Pyright retains
the exact public result types.

`proto/route_continuation.py` now exercises decoded and raw keys. Both write a
finite route lane and select an already-compiled PDA clone or Earley successor;
they add **zero grammar arms**. Raw `"model"` and `"m\\u006fdel"` remain
distinct. The caller's `resolve=` channel is consequently untouched and reaches
only genuine ambiguity in the authored document grammar. The overlapping-arm
resolver in `demand_selection.py` is retained only as the rejected prototype
stand-in that motivated this route mechanism.

## 6 — shared synthetic folds and order-balanced collector rows

`shared_forest_refold.py` now mirrors the production fact that transparent
synthetic folds do not write a result. Its `__rep_1` witness executes twice
under the current result-membership guard and once under a distinct finished
set. The earlier 2/2/1 counts were a lower bound, not the complete defect shape.

`carrier_gc_cost.py` now requires an even round count. One isolated invocation
with eight retained workers and eight alternating pairs produced:

| collector | process CPU median | wall median |
|---|---:|---:|
| enabled | 0.700274 s | 0.130779 s |
| disabled | 0.689180 s | 0.132670 s |

Median paired enabled-minus-disabled was +0.004562 s process CPU and
-0.002075 s wall. The wall sign is noise, not a claim that collection helps.
The carrier headline is now the explicitly GC-enabled row; the old 0.138739 s
GC-disabled component decomposition remains provenance only and is not a
budget.

## Verification

All changed/new prototypes pass Ruff format/check and Pyright with zero
findings. The executable non-benchmark witnesses pass serially. The collector
probe was the only multithreaded benchmark and owned its complete timing window;
the capture/ops comparison was sequential and ran in a separate window.
