# WIP external review — hold until the §4 pre-checkpoint gate

> **DO NOT READ OR ACT ON THIS REVIEW YET.**
>
> §4 implementation is still in progress. This review is a snapshot taken
> during that work, so later increments may already answer some findings.
> Reconcile it against the completed §4 source only after implementation and
> before the §4 profile, coordinator review, and checkpoint commit. It neither
> interrupts the current implementation nor certifies its present state.

## Scope

Read-only review of savepoint `0a76490f` plus the unstaged §4 work visible on
2026-09-01. No files were changed as part of the review, and no tests or
benchmarks were run.

## Assessment

The §4 work is moving in a better direction, particularly `matched_field`, the
centralized `VALUE_FIELD`, and deriving the existing flat build plan from
product records without adding paid-loop opcodes.

The current evidence nevertheless overstates what has been proved. The earlier
review blockers remain unresolved in this snapshot, and the new §4 work exposes
additional architectural gaps which must be checked against the completed
implementation before the checkpoint.

## Findings

### High — the switch differential does not switch the completion channel

`proto/s4_switch_differential.py::_product_baked` calls the old
`_BAKE(clone, fold)` first, retains `clone.fold` and the fold-derived build
mode, and later calls `pda_model(..., compiled.fold)`. It replaces only
`fields`, `plan`, `fast`, `defaults`, and `needs_ends`.

That usefully proves that product records can reproduce the optimized build
plan. It does not prove that PDA completion executes the product, that the
whole flat program is product-built, or that the fold channel can be deleted.
Those claims require a differential which runs without fold-derived completion
or lifecycle data.

### High — the authored model product cannot yet express model semantics

`compile/pipeline/synthesis.py::model_plan` authors every rule as a `RecordOp`,
including alternations.

- An alternation should pass through its selected child, but it has no capture
  and never uses the existing `PassOp`.
- `RecordOp` alone cannot distinguish sequence, alternation, and value-string
  completion.
- `bake_product_build` refuses any non-`RecordOp`, preventing the direct
  `PassOp` correction in its current shape.
- An unlicensed constructor clears all product-derived build data. The old
  runtime then falls back to `clone.fold`; after fold deletion that construction
  path disappears.

The product must encode alternation pass-through and the unlicensed validated-
construction path before the fold channel is switched or deleted.

### High — `SymbolExpr` is a general callback channel with only documentary restrictions

The prose limits `SymbolExpr` to infrequent compile-time surfaces, but the ABI
does not enforce that boundary: any `RuleProduct` can contain it,
`lower_product` accepts a registry for every product, and the verifier has no
cold-surface or frequency distinction. The lowered operand table contains
arbitrary Python callables.

A registry name prevents `eval`; it does not prevent the opcode from becoming
a callback escape hatch in frequently completed rules. The cold-surface
restriction must be structural rather than documentary.

### High — the JSON numeric semantic boundary remains inconsistent

`grammars/json.py::JSON_EVENTS` still maps the completed `number` rule to the
integer event and the interior `frac` suffix to the fraction event. The suffix
does not contain the complete signed or exponent-bearing value, and `1e3`
contains no `frac` occurrence at all. The numeric sort must be determined from
the completed numeric value rather than this interior rule.

### High — ambiguity replay still cannot represent Python `None`

`earley/kernel/forest/support/ambiguity.py::replayed` returns `None` both when
an alternate fails to build and when the valid target value is Python `None`.
The latter is required by the Python JSON target. Replay needs a generic,
explicit success/failure result shape.

### High — physical verification remains incomplete

`parsing/product/verify.py` verifies that an instruction's operand-row index
exists and that its row contains exact integers. It does not verify those
integers against the tables they index. Invalid constant, constructor, decoder,
route, finisher, check, root-finalizer, meaning-comparator, destination, and
continuation indices can therefore survive the cold gate and fail during
execution.

### High — established parsing paths still carry unapproved work

Every ordinary Earley model fold still allocates and maintains the added
`folded` set. The PDA still carries route state and fork tests even though no
compiled schema can yet emit a route. These changes require the promised clean
baseline comparison and explicit approval if a parsing regression remains,
including when a change is justified as a bug fix.

### High — forbidden type erasure and suppressions remain and are expanding

The implementation still adds `Any`, `object`, and `# type: ignore`; the new
product bake and symbol table add more. This violates the effort's explicit
constraints and identifies unresolved type boundaries rather than harmless
annotation debt.

The carrier, source artefact, meaning memo, construction licence, default
values, and cold symbol transforms need honest named or generic shapes.

### Medium — baseline-result reuse remains underspecified

`TODO.md` and `DESIGN.md` still say that a family's baseline outcome is reused
for lifting. A lift changes a carried child value, so its reducer result cannot
generally be the baseline result. Reusable facts include liveness, structural
work, and evaluations keyed by the complete child-image tuple; a baseline
value cannot stand in for a different lifted input.

## Pre-checkpoint disposition

At the completed §4 pre-checkpoint gate:

1. Re-read each finding against the final source and close any that later work
   demonstrably resolved.
2. Correct every surviving semantic, architectural, typing, and verifier issue.
3. Require a real no-fold PDA/Earley completion differential, not only build-
   plan identity.
4. Run the clean external parsing comparison before accepting the checkpoint;
   no review authorizes a parsing regression.

The product-side bake is worth keeping. It demonstrates that much of the
existing PDA flat build representation can be retained exactly. The checkpoint
question is whether the completed implementation replaces the old completion
channel rather than reproducing only the optimized data hanging from it.
