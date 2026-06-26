# What was implemented (2026-06-26) — since reverted

This is a factual record of the code changes that were applied and then reverted.
It states only what was changed. It does not draw conclusions.

## Change 1 — `src/lexic/parsing_2/normalize.py`, `Expand.eval`

The `*` and `+` unbounded arms were changed from right-recursive to
left-recursive by swapping the operand order in the second arm:

```python
# before
if lo == 0:    # *
    body = IrAlternation(IrSequence(), IrSequence(unit, ref))
elif lo == 1:  # +
    body = IrAlternation(IrSequence(unit), IrSequence(unit, ref))

# after
if lo == 0:    # *
    body = IrAlternation(IrSequence(), IrSequence(ref, unit))
elif lo == 1:  # +
    body = IrAlternation(IrSequence(unit), IrSequence(ref, unit))
```

The `?`, bounded-count, `m*` (lo>1), and `OptChain` branches were not changed.
Three docstrings/comments that said "right-recursive" were changed to say
"left-recursive". `reduce.py` was not changed.

## Change 2 — `src/lexic/parsing_2/ops.py`, `Predict.eval`

One line changed: `for item in cast(Sequence[IrSelf], arm)` → `for item in arm`.

## Test edits

- `tests/unit/lexic/parsing_2/test_normalize.py`: two tests
  (`test_desugar_star_second_arm_has_atom_and_self_ref`,
  `test_desugar_plus_second_arm_has_atom_and_self_ref`) had their arm-order
  assertions and docstrings changed to expect the swapped (left-recursive) order.
- `tests/performance/test_lazy_forest_perf.py` and `tests/performance/conftest.py`:
  comment/docstring wording changed from "right-recursive, O(n²)".

## Measurements taken (raw, no interpretation)

Full test suite wall-clock, 3 runs each, `-p no:randomly`:

- without the changes: 11.00 s, 10.93 s, 10.96 s (2 tests failing — the two
  unmodified assertions above)
- with the changes: 11.81 s, 11.03 s, 11.06 s (1126 passing)

ABNF self-parse fixpoint (`Earley fixpoint == ABNF_GRAMMAR`) printed `True` both
with and without the changes.

## Status

All of the above was reverted by the user. Current tree does not contain these
changes.
