# Terra prompt — §4 production source

Implement the unchecked production-source bullets of `TODO.md` §4 in
`/home/mika/projects/lexic`, in their TODO order, through the user-directed
hold that follows them. Establish which bullets are open and what the tree
contains from the repository, not from this prompt.

## Orientation

Read the repository instructions and `docs/STYLE.md` completely; they carry
the standing rules and are not repeated here. Then read this effort's
`HANDOVER.md`, `TODO.md` (working protocol and §4 in full), `LEDGER.md` from
the top through "§4 opened: caller inventory and scope rulings", and
`DESIGN.md` §"Target contract", §"Parser consequences", §"Code ownership
after the redesign". Every LEDGER ruling and every parenthesised ruling on a
§4 bullet binds this round.

A Luna pass is finishing the mechanical green-ground fixes; its report is
`reports/S4_LUNA_GREEN.md`. Do not edit any file until that report exists
and you have read it. Then record the initial status: `git status`, `uv run
pyright src tests tools`, and `uv run pytest tests/ -q -n 8`, each unpiped
with its exit code and counts, nothing else running. For each open bullet,
inventory its real consumers with `rg` before designing. Read every module
in full before editing it, every time.

## Authority

Write only `src/`, the `CLAUDE.md` package map (mechanically, for every
module added, moved, or deleted), `proto/s4_*.py` witnesses,
`reports/S4_TERRA.md`, and committed tests for mechanical call-site
adaptation alone — construction and call syntax, assertions byte-preserved,
every adapted file listed; a changed contract is reported for Luna, not
re-pinned. Everything else is read-only, the active plan included.

Beyond the repository rules: no private imports across modules — a helper
that moves takes a public name in its new home; replace, then delete — no
wrapper, adapter, alias, flag, fallback, or retained old route beyond what a
bullet's ruling names; the generated-model paid path is the zero-tax
baseline and gains no state, transaction test, verifier call, interpreter,
opcode, frame slot, allocation, attribute read, or branch; a representation
change on that path lands only after it is measured faster under
`docs/STYLE.md` §7's structural protocol with its numbers in the report;
fallout past one adaptation cycle stops the bullet and reports the blast
radius; before any timing window tell the orchestrator and wait for quiet.
Where the tree proves a bullet's stated contract impossible, report the
proof — do not build a bridge.

## What the bullets must establish

The fold-channel bullets (island/delegate/parallel, `trace.py`, foldkit and
its notation/self-grammar callers, the six-symbol deletion): every island,
delegate, ambiguity-replay, stitch, replica, and trace consumer reads the
bound product — rules, construction tables, the one `ProductExecutor`;
stitch layout derives from `RuleProduct.captures` zipped with
`RecordConstructor.names`, refusing rather than assuming anything else;
model-shaped stitching semantics stay byte-identical; every fold half
authored beside a product goes; every `foldkit` idiom is accounted for by
name; `lift_optional_nullables` keeps an honest home until §8; a search for
the six symbols and `.fold` in `src` is empty at the end.

The completion-range and operations-as-data bullets: every binding lowers
once through `lower_product` and passes `verify_program` cold at bind;
every execution path resolves exactly one verified `CompletionRange` for its
rule with no parallel fields and no paid-path read; the generated-model
program contains zero symbol ops and is not stateful; no target object or
morphism is reachable from the character matcher, item loop, gate selection,
or any frequent completion — recorded with `file:line` evidence; the
`type: ignore` in `compile/product/lower.py` goes at the root.

The `Carry` bullet: every output, holder, and sink path is honestly generic.
The frame list is a heterogeneous mutable positional record; if it admits an
honest typing under the constraints, land it and show the pyright run;
otherwise build the typed alternative as a throwaway A/B, measure it under
the structural protocol over at least three ground-truth grammars including
an attempt-heavy one, and report the numbers — nothing frame-shaped lands
without the ruling.

The value-string bullet: a census first — per ground-truth grammar, the
`value_str` occurrences, those `prove_regular` accepts, those the existing
run-table specializations already serve, and the residual with its per-parse
call count — sent to the orchestrator before the consult is written; a
residual that cannot reach one percent by `docs/STYLE.md` §7's price
arithmetic stops there; otherwise one recognizer consult per eligible
occurrence, the ordinary completion range for capture, declined rules on
their current program, and separate generated-model and token-segmented gate
rows with structural and timed evidence.

The opcode-comparison and zero-tax bullets: against the starting commit
(`git show <commit>:<path>` into `proto/`, never a checkout), every
`FlatClone` field over every ground-truth grammar and the bytecode of the hot
functions in `kernel.py`, `execution.py`, `build.py`, `flatten.py`, and
`product/tree.py`; every added paid-loop instruction explained or removed.

## Execution

One bullet at a time: inventory, design against the ruling, implement,
verify with the relevant existing tests and a `proto/s4_*.py` witness where
the claim is structural, write the report section, message the orchestrator
`lexic-d3` one line — bullet, verdict, section — and continue unless the
orchestrator has replied or the bullet's ruling requires a decision.

## Sequential source review

When every open production-source bullet is implemented and verified, call
fresh, read-only reviewers synchronously and sequentially; no other agent or
measurement may be active. **Do not use Fable.** Use the strongest available
reasoning model at high effort, `subagent_type: general-purpose`,
`run_in_background: false`.

Reviewer 1 — the paid path:

```text
Read the repository instructions, docs/STYLE.md, TODO.md §4, and
reports/S4_TERRA.md. Diff src/ against the starting commit named in the
report. Falsify the zero-tax claim: find any state, transaction test,
verifier call, interpreter, opcode, frame slot, allocation, attribute read,
or branch added to the generated-model character, item, or frame paths; any
retained fold symbol, wrapper, adapter, or fallback; any unverified
completion path; any Any/object/cast/suppression or cross-module private
import in added lines. Read-only; no benchmarks. Return substantive
file:line findings and READY only if none survive. Ignore prose nits.
```

Reviewer 2 — the contracts:

```text
Read the same inputs after the Reviewer 1 fixes. Falsify semantic
preservation: island, delegate, ambiguity replay, stitch, replica, trace,
notation, self-grammar, and templating behaviour against the tree at the
starting commit; the gtext absence-versus-empty-string row; the one-verified-
completion-range claim on every execution path; the value-string census and
gate rows if any landed. Read-only; no benchmarks. Return substantive
file:line findings and READY only if sound. Ignore prose nits.
```

Fix findings within the write allowlist, rerun, and record prompts,
findings, fixes, reruns, and verdicts in `reports/S4_TERRA.md`. If the Agent
tool is unavailable, write the prompts into the report and stop; do not
substitute Fable.

## Report

`reports/S4_TERRA.md`: one section per bullet in TODO order, appended, never
rewritten — the bullet quoted, files changed and inspected, decisions and
defects with `file:line`, the exact verification commands with exit codes
and counts, every measurement with its protocol, control row, GC state, and
raw numbers — and a `## Restart point` at the end, overwritten each time. It
must finally answer: which bullets are done with what evidence; where each
execution path resolves its one verified completion range; what the paid
path costs now against the starting commit, instruction by instruction; what
any representation measurement showed; which tests were adapted and which
contracts await Luna; what remains implementation, measurement, or user
decision; and both reviewers' verdicts.

## Done

Run, unpiped and one at a time: the relevant unit and integration files for
every touched module, the full suite, `uv run pyright src tests tools`,
`uv run python tools/check_generated.py`, every `s3_*` and `s4_*` witness,
and `tools/run_checks.sh` with its exit code and per-file attribution.
Search for forbidden constructs, restore cache or bytecode changes, run
`git diff --check`, write the restart point, and stop. The hold that follows
brings in a different model to review the completed §4 source; the
reconciliation of `reports/WIP_EXTERNAL_REVIEW.md`, external profiling,
commits, and Luna's work belong to that review and to the user's resumption,
not to this round.
