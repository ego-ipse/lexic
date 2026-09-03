# S4 — Vega CI: examples, benchmarks, remote A/B diagnosis

Agent `vega-ci`, branch `targeter`, HEAD `c9c72fc6` (Savepoint 11) plus the
uncommitted test work. Write scope exercised: `tools/benchmark` only. No `src/`
or `tests/` edit. Nothing committed.

Headline, in the order that matters:

1. The red remote A/B is **not** a performance regression. It is the harness's
   cross-tree design meeting this effort's public-API renames. Section 6 records
   the public-surface migration: **half the A/B rows now run against the base
   tree**, and the remaining half are blocked on one irreducible thing. User
   ruling needed.
2. The 48 pylint findings are **not** pre-existing. The PR base tree scores
   10.00/10 and pylint exits 0 on it. Every finding is this effort's debt.
3. `tools/run_examples.sh` exits 0. All 17 examples pass.
4. Every benchmark entry point runs. One was broken by a stale path index; I
   fixed it at the root.
5. The local ratchet fails on HEAD **and on base**, on different rows. It is
   not a trustworthy signal on this host. It gates `pre-commit`, not the remote.

---

## 1 — Remote A/B: root cause

### The failing run

Job 100624448116 of run 33747875232, step "Compare base and HEAD on this
runner", fails in about 20 s. Every `performance.yml` run on this branch since
2026-09-02 fails identically. Five most recent, all `failure`: 33747875232,
33692465344, 33661753354, 33637794570, 33613787164.

### Base resolution

The workflow's "Resolve the comparison base" step took the pull-request branch,
so the base is the PR base sha `0faa72899580af749316e3964f734a4570577055`. I
confirmed that sha contains `tools/benchmark/lexic_baseline.json`, so the
`--diff-filter=A` fallback (which would have given `a89a5581ddfc66c9703c8609ac93b9a82d643988`)
never fires. The runner log shows `ref: 0faa728...` on the base checkout and no
"event base predates the performance harness" line.

### Reproduction

Extracted outside the repo, no worktree:

```
mkdir -p /tmp/lexic-base
git archive 0faa72899580af749316e3964f734a4570577055 | tar -x -C /tmp/lexic-base
```

Then from the repo root, the workflow's own command:

```
uv run python -u -m tools.benchmark.compare \
  --base-source /tmp/lexic-base/src \
  --base-record /tmp/lexic-base/tools/benchmark/lexic_baseline.json
```

Exit code **1**, in about 12 s, with the traceback the runner prints verbatim:

```
RuntimeError: benchmark worker failed preparing abnf-meta/lexic-earley/base: Traceback (most recent call last):
  File "tools/benchmark/execution/worker.py", line 11, in <module>
    from tools.benchmark.bench import (
  File "tools/benchmark/bench.py", line 61, in <module>
    from tools.benchmark.cases.grammars import Bench
  File "tools/benchmark/cases/grammars.py", line 37, in <module>
    from lexic.parsing import ProductExecutor
ImportError: cannot import name 'ProductExecutor' from 'lexic.parsing' (/tmp/lexic-base/src/lexic/parsing/__init__.py)
```

### Why it happens

The harness states its own assumption at `tools/benchmark/compare.py:3-6`: the
HEAD benchmark harness and grammar corpus are held constant, and only the
`lexic` package imported by each worker changes. It implements that by
prepending the base checkout's `src` to the worker's `PYTHONPATH`, at
`tools/benchmark/execution/isolation.py:73-76`.

So HEAD's benchmark code is executed against the base tree's `lexic`. Any
renamed public name in `lexic` makes the base arm unloadable. This effort
renamed several.

### Complete break list

I probed the base tree directly rather than iterating on tracebacks, so this is
the full set, not just the first failure.

| Symbol HEAD's benchmark code reads | Base tree | Read at |
|---|---|---|
| `lexic.parsing.ProductExecutor` | absent; base exports `ModelFold` from `lexic.parsing.fold` | `tools/benchmark/cases/grammars.py:37` |
| `CompiledGrammar.product` | absent; the field is named `fold` | `tools/benchmark/bench.py:194,204,267,268,642` |
| `CompiledGrammar.executor` | absent | `tools/benchmark/cases/grammars.py:79`, `tools/benchmark/diagnostics/split_ab.py:103` |
| `binding.executor` | absent; base passes the fold itself | `tools/benchmark/bench.py:270,273` |

Base `CompiledGrammar` fields are `grammar, fold, moments, flavour, stem,
tokens, split_analysis`. HEAD's are identical with `fold` renamed to `product`.

Two renames happen to survive because every call site is positional, and they
are worth naming so nobody "fixes" them:

- `_model_product(grammar, fold)` became `_model_product(grammar, binding)`.
- `Request(text, fold, resolve)` became `Request(text, binding, resolve)`.

### Why I did not fix it

Making the benchmark case code load against both trees means branching on which
names the imported `lexic` happens to have. That is a compatibility shim, which
my brief forbids and which the one-way-per-task rule in `CLAUDE.md` also rules
out. There is no root-cause fix available inside `tools/`, so this is a
coordinator decision, and the edit would land in
`.github/workflows/performance.yml`, outside my write scope.

### Options, with a recommendation

I recommend option 2.

1. **Give each arm its own harness**, so the base arm runs base's
   `tools/benchmark`. Structurally correct across a rename, but it retires the
   "harness held constant" property, and from then on harness differences
   confound every comparison. I would not pay that price to make one PR green.
2. **Accept the workflow as red for this PR, require it green on the post-merge
   push to `main`.** Once merged, base carries the new names and the A/B loads.
   The renames are this PR's entire point, so a cross-tree A/B against the old
   names measures a surface that no longer exists. Costs nothing structurally.
3. **Gate the workflow to skip the A/B when the base lacks the HEAD API.** This
   is option 2 with an automatic detector, and the detector is itself a
   compatibility check on `lexic`'s surface. Worse than a human decision on the
   rare rename PR.

### Not a performance regression

The A/B never reached a timed row. It failed during untimed worker preparation,
on the first cohort. No base-versus-HEAD timing exists for this PR, and none can
be produced until the base tree carries the renamed API.

---

## 2 — Examples

```
tools/run_examples.sh
```

Exit code **0**. Silent, which the script defines as every example passing. All
17 present and run as modules from the repo root: `ex01_hello_grammar` through
`ex17_transpile_python_cpp`. No failures, so no tracebacks to record.

---

## 3 — Benchmarks

Entry points, taken from the package READMEs and module docstrings. There are
six modules with a `__main__` guard; `bench` and `presentation.cli` are one
entry point with two spellings, because `tools/benchmark/bench.py`'s `main`
delegates to `presentation.cli.main`. `execution.worker` is internal and is
exercised by every other entry point through `isolation.run_jobs`.

| Entry point | Command | Exit |
|---|---|---|
| Full report | `uv run python -m tools.benchmark.bench --rounds 1` | 0 |
| Report, other spelling | `tools.benchmark.presentation.cli` (same code as above) | 0 |
| Parallel diagnostic | `uv run python -m tools.benchmark.diagnostics.parallel` | 0 |
| Split A/B, profile | `... diagnostics.split_ab --profile --engine E --case C`, 9 combinations | 0 |
| Split A/B, two-tree | `... diagnostics.split_ab --ab src src --rounds 3` | 0 |
| Ratchet | `uv run python -m tools.benchmark.regression` | **1** |
| Cross-tree A/B | `tools.benchmark.compare` (see section 1) | **1** |

Heavy runs went through `tools/guarded.sh 8G <timeout> --`.

### 3a — The one thing I fixed

`tools/benchmark/diagnostics/split_ab.py` could not run its `vyx` case at all:

```
FileNotFoundError: [Errno 2] No such file or directory:
'/home/mika/projects/lexic/tools/resources/ground_truth/vyx.gbnf'
```

Cause: line 88 computed the repo root as `Path(__file__).resolve().parents[2]`.
Git records the file's history as `R100 tools/benchmark/split_ab.py ->
tools/benchmark/diagnostics/split_ab.py`, a pure rename with no content change.
At the old depth `parents[2]` was the repo root; one level deeper it is
`tools/`. The index was never updated.

Fix: `parents[2]` to `parents[3]`, matching the sibling convention in
`tools/benchmark/cases/grammars.py:39`. One line, `tools/` only. Verified: ruff
check and format clean, pylint 10.00/10 on the file, and all three engines now
run the `vyx` case. `tests/integration/lexic/invariants/` still passes, 95
tests.

This bug predates the S4 renames and was hiding an entire benchmark case.

### 3b — Headline numbers, informational only

Two-tree control, identical trees, `--ab src src`, process time, alternating
processes. This is the noise floor for that instrument:

| Row | A ns/parse | B ns/parse | B vs A |
|---|---|---|---|
| pda:nested-plus | 4546.2 | 4556.9 | +0.24% |
| pda:vyx | 44374.4 | 43684.2 | -1.56% |
| earley-resolved:nested-plus | 125240.0 | 124663.1 | -0.46% |
| earley-resolved:vyx | 566795.0 | 565947.2 | -0.15% |
| pda:control | 3104.3 | 3163.1 | +1.89% |

Machine, from the parallel diagnostic: Python 3.14.3, free-threaded, 16 CPUs,
2 KiB chunk floor. Document-level thread scaling on this host degrades past
four threads:

| Threads | Documents | Wall |
|---|---|---|
| 1 | 1 | 13.9 ms |
| 2 | 2 | 15.4 ms |
| 4 | 4 | 16.9 ms |
| 8 | 8 | 46.9 ms |

The full report runs every engine including the Java ANTLR targets, and prints
its own per-grammar noise floor (0.55% to 5.30% across the grammars I saw).

### 3c — The ratchet fails, on both trees

`uv run python -m tools.benchmark.regression` on HEAD, exit **1**:

```
confirming execution-order anomalies only (sigma-adaptive 21-35 aggregate rounds): mixedends/lexic-mt-lex-ns>lexic-lex-ns
  mixedends/lexic-mt-lex-ns: 0.097857; expected <= lexic-lex-ns: 0.072342
Lexic execution-mode performance regression confirmed
```

The multithreaded row is 1.35x slower than the single-threaded row on the same
grammar. The full report agrees independently: `mixedends` reads
`lexic-mt-lex-ns 98.2 ns/char` against `lexic-lex-ns 76.1 ns/char`, a ratio of
1.29.

Before attributing that to this effort, I ran the base tree's own ratchet, from
the base tree, with the base `src` on `PYTHONPATH`. Base exits **1** too:

```
confirming execution-order anomalies only: lexruns/lexic-mt-lex-ns>lexic-mt
confirming new or >5% change candidates only: abnf-meta/lexic-mt-lex-ns, announced/lexic-mt-lex-ns, gbnf-meta/lexic-mt, lexruns/lexic-mt-lex-ns, markdown/lexic-mt-lex-ns, vyx/lexic-mt-lex-ns
  abnf-meta/lexic-mt-lex-ns: 0.395459 -> 0.429185 (+8.53%)
performance regression confirmed
```

Both trees fail, on **different** rows, and both failures are multithreaded
rows. Read together with the thread-scaling table above, the honest reading is
that the `lexic-mt*` rows are unstable on this host, not that this effort
regressed the parallel layer. I did not tune anything and I am not claiming the
MT rows are clean either. What I can say precisely:

- The HEAD ratchet failure is **not** evidence of a regression introduced by
  this effort, because the same instrument fails on the effort's own base.
- The committed `lexic_baseline.json` was recorded on a different machine, so
  its absolute values do not transfer here. The execution-order checks are
  within-tree and do transfer, and those are the ones failing on both trees.
- Deciding whether the parallel layer is actually healthy needs a run on the
  recording machine, or on the CI runner. I could not settle it from here.

This gates `pre-commit`, via the `lexic-benchmark-regression` hook in
`.pre-commit-config.yaml`. It is **not** in any workflow. The remote runs
`compare.py`, not `regression.py`, so this does not contribute to the red PR.

---

## 4 — Pylint inventory

`tools/checks/40_pylint.sh` runs `uv run pylint src/ tests/ getting_started/
tools/ ext/`. On HEAD it exits **14** (error + warning + refactor bits), rated
9.99/10, which is what makes `tools/run_checks.sh` exit non-zero under `set -e`.

### The premise correction

The brief describes these as 48 pre-existing findings, citing
`S4_LUNA_COVERAGE.md` §11. That section confirms them as pre-existing with
`git diff -U0 7d60f575 --`, which is Savepoint 10, a commit *inside* this
effort. So the claim is true as written but means "not introduced by Luna's
pass", not "not introduced by this PR".

I measured the actual PR base. Running the same pylint command over the
extracted base tree:

```
uv run pylint /tmp/lexic-base/src /tmp/lexic-base/tests \
  /tmp/lexic-base/getting_started /tmp/lexic-base/tools /tmp/lexic-base/ext
```

Exit code **0**, rated **10.00/10**, zero findings. I diffed the `[tool.pylint]`
section of both `pyproject.toml` files first; they are identical, so this is a
like-for-like comparison. The `checks` workflow history agrees: green on every
recent `main` push, red on every `targeter` pull request.

**Every one of the 48 findings is introduced by this effort.** None is
pre-existing relative to `main`.

### Full list, grouped by message code

48 findings. 46 in `src/`, 1 in `tests/`, 1 attributed to `ext/`.

**W0621 redefined-outer-name — 28**

All 28 are the same shape: a local or parameter named `Carry` shadowing a
module-level `Carry`.

- `src/lexic/parsing/pda/compiler/program/flatten.py:49, 431, 444` (outer at line 38)
- `src/lexic/parsing/pda/runtime/build.py:141, 150, 187, 208, 258, 293, 343, 366` (outer at line 109)
- `src/lexic/parsing/product/abi/construction.py:180, 186, 198` (outer at line 38)
- `src/lexic/parsing/product/tree.py:126, 141, 146, 153, 175, 189, 216, 247, 256, 284, 310, 343, 373, 396` (outer at line 61)

**R0917 too-many-positional-arguments — 6**

- `src/lexic/parsing/earley/engine.py:219` (6/5)
- `src/lexic/parsing/earley/kernel/forest/support/ambiguity.py:217` (6/5)
- `src/lexic/parsing/pda/runtime/build.py:150` (7/5)
- `src/lexic/parsing/pda/runtime/build.py:258` (6/5)
- `src/lexic/parsing/product/abi/construction.py:162` (7/5)
- `src/lexic/parsing/product/tree.py:343` (6/5)

**R0913 too-many-arguments — 6**

The same six sites as R0917, same counts. Each site raises both codes.

**R0903 too-few-public-methods — 3**

- `src/lexic/parsing/executable.py:44` (1/2)
- `src/lexic/parsing/product/abi/construction.py:50` (1/2)
- `src/lexic/parsing/product/abi/construction.py:151` (0/2)

**R0914 too-many-locals — 2**

- `src/lexic/parsing/earley/kernel/forest/support/ambiguity.py:330` (17/15)
- `src/lexic/parsing/parallel/stitch/model.py:194` (20/15)

**W2301 unnecessary-ellipsis — 1**

- `src/lexic/parsing/product/abi/construction.py:56`

**E1136 unsubscriptable-object — 1**

- `tests/unit/lexic/parsing/pda/runtime/kernel/test_decisions.py:106`, on
  `frame[F_ENDS]`. The only error-class finding, and the only one in `tests/`.

**R0801 duplicate-code — 1**

- Reported against `ext/API/hf.py:1`, which is only where pylint hangs the
  cross-module report. The duplication is entirely between two `src` files.

### The R0801 duplicate, in full

Pylint reports 13 identical lines shared by `lexic.parsing.earley.engine`
[229:242] and `lexic.parsing.products` [166:179].

`src/lexic/parsing/earley/engine.py:219-242`, the tail of
`first_built_meaning`:

```python
def first_built_meaning[Value, NodeValue](
    d: IrSelf,
    n: IrSelf,
    text: str,
    builder: MeaningBuilder[Value, NodeValue],
    tables: ParserTables | None = None,
    resolve: Resolver | None = None,
) -> Value:
    """Return the chosen value, constructing each considered meaning once."""
    kernel, handle, first = _first_derivation(d, n, text, tables)
    pair = different_meaning(kernel, handle, builder, first)
    witness = pair.witness
    if witness is None:
        return pair.first.value
    if resolve is None:
        raise UnsupportedConstructError(
            "parsing: ambiguous input — two derivations that mean different "
            "things; supply a resolver to choose between them"
        )
    chosen = resolve(pair.first.tree, witness.tree)
    if chosen is pair.first.tree:
        return pair.first.value
    if chosen is witness.tree:
        return witness.value
    return builder.build(chosen)
```

`src/lexic/parsing/products.py:160-180`, the tail of the token-route entry:

```python
    executor = binding.executor
    pair = different_meaning(
        kernel,
        handle,
        MeaningBuilder(executor.build, executor.replay),
        tree,
    )
    witness = pair.witness
    if witness is None:
        return pair.first.value
    if resolve is None:
        raise UnsupportedConstructError(
            "parsing: ambiguous input — two derivations that mean different "
            "things; supply a resolver to choose between them"
        )
    chosen = resolve(pair.first.tree, witness.tree)
    if chosen is pair.first.tree:
        return pair.first.value
    if chosen is witness.tree:
        return witness.value
    return executor.build(chosen)
```

The two tails are the same algorithm on the same data. `products.py` even
builds the very `MeaningBuilder` that `engine.py` receives as a parameter, so
its final `executor.build(chosen)` *is* `builder.build(chosen)`. The
duplication is exact, not merely similar.

**This finding is new, and I can show why.** On base the two regions shared
only the five-line raise message, below pylint's similarity threshold. Base
`engine.py:192-202` read `witness = another_meaning(...)` then
`return policy.resolve(first, witness)`; base `products.py:150-158` read
`witness = another_meaning(...)` then `return fold.apply(resolve(tree, witness))`.
This effort replaced `another_meaning`, which returned a bare witness, with
`different_meaning`, which returns a `pair` carrying both meanings and their
trees. That change grew the shared tail from 5 lines to 13 and crossed the
threshold. The duplication was always latent; the refactor made it literal.

**Recommended single owner:
`src/lexic/parsing/earley/kernel/forest/support/ambiguity.py`.**

That module already defines both `MeaningBuilder` (line 155) and
`different_meaning` (line 330). The duplicated tail is the last step of the
same policy: given the pair `different_meaning` just produced and an optional
resolver, decide the value or refuse. Splitting the decision from its producer
across two consumer modules is what created the duplication.

Layering makes it the only legal home. `engine.py` is inside
`lexic.parsing.earley`; `products.py` is the runtime seam that imports the
engine. `engine.py` cannot import `products.py`, so neither consumer can own
code the other needs. `ambiguity.py` sits beneath both and both already import
from it.

The extracted function takes the pair, the builder and the resolver, and
returns the value. Both call sites collapse to a single `return`. The generic
parameters are already on `MeaningBuilder[Value, NodeValue]`, so the signature
needs no new type machinery. `products.py` keeps building its `MeaningBuilder`
and passes it along instead of reaching for `executor.build` a second time.

I did not make this change. It is `src/`, and it is the coordinator's call.

### One more src defect, unrelated to pylint

`src/lexic/parsing/products.py:183-184` carries the same comment banner twice:

```python
# ── compiled-product records + per-identity memoisation ────────────────────
# ── compiled-product records + per-identity memoisation ────────────────────
```

Base has one. This effort duplicated it. Cosmetic, no pylint code fires on it,
one line to delete. Flagging rather than fixing, since it is `src/`.

---

## 6 — Public-surface migration of the harness

Ruling received: options 1, 2 and 3 of section 1 are all out; the remote must be
green, A/B included. The stated root cause is one step deeper than section 1
put it. A harness whose invariant is "held constant while lexic changes
underneath" can only keep that invariant if it drives lexic through the
**public** surface. This one reached into internals, so it was already breaking
its own invariant and the rename merely made that visible. I investigated the
root fix and did the part that is achievable.

### 6a — What the two trees actually share

I diffed the export lists rather than reasoning from the diff. The rename
surface is small and exact.

| Module | Shared names | Only in base | Only in HEAD |
|---|---|---|---|
| `lexic.parsing` | 51 | `FastCtor`, `FieldFold`, `ModelBody`, `ModelFold`, `RuleFold` | `ModelExecutable`, `ProductExecutor` |
| `lexic.compile` | 48 | `RuleBinding`, `bind_module` | `RuleMap`, `attach_module` |
| `lexic` | 6 | none | none |

Beyond the export lists, these are **byte-identical in both trees** and are
therefore safe ground for the harness:

- `CompiledGrammar.parse(text, resolve=None, cores=0)`, `.pda_tables()`,
  `.anchors()`, `.reduce()`, `.bind()`, `.classes`, `.codegen_grammar`,
  `.moments`, `.flavour`, `.stem`, `.tokens`, `.split_analysis`
- `compile_text` — signature identical, and it carries **no engine selector**
- `PdaTables` — same attributes and same annotations, including the public
  `instance_grammar`
- The whole of `lexic.parsing.parallel`, including `split_plan`, `split_model`,
  `worker_count`, `doc_workers`, `available_workers`, `SplitPlan`
- `watch`, `PdaKernel`, `WatchedKernel` — and critically, all three take the
  model-build object as an **optional** third argument defaulting to `None`
- `WatchedRun` — same fields, including `derived`
- `earley_model`, `parse_model`, `token_model`, `pda_tables` — same arity; the
  third parameter is renamed but every call site passes it positionally

### 6b — What I converted

**Deleted a dead internal reach.** `tools/benchmark/cases/grammars.py` imported
`ProductExecutor` solely to annotate a `Bench.executor` property that nothing
calls. I grepped `tools/`, `tests/` and `getting_started/`; there is no
`bench.executor` call site anywhere. Deleting the property and its import
removes the harness's first and most visible cross-tree failure. The module now
imports cleanly against the base tree.

**Moved `_decision_cost` onto the public surface.** It previously reached the
private `_model_product`, the renamed `.product` and `.executor`, and the deep
internal `lexic.parsing.pda.runtime.kernel.kernel.pda_model`, using a
`try`/`except LexicError, PdaFail` to detect PDA incapability. It is now:

```python
run = watch(compiled.pda_tables(), corpus, cap=1_000_000)
if not run.derived:
    return None
```

`pda_tables()` takes no arguments, `watch`'s third argument is optional, and
`derived` is the run's own verdict on whether the PDA took the corpus. The wiki
endorses exactly this reading: a refused predictive run is an event, not an
exception. Three internal imports disappear with it — `pda_model`, `PdaFail`
and `LexicError`.

**Routed the remaining public entries through the package root.**
`earley_model`, `parse_model` and `watch` were imported from
`lexic.parsing.products` and `lexic.parsing.trace`. They are root exports in
both trees, so they now come `from lexic.parsing`.

**Stopped computing the build object for rows that do not need it.**
`bench.py` read `bench.compiled.product` unconditionally at the top of
`_lexic`. Only the `lexic-earley` row uses it, so it moved inside that branch.

**Behaviour is preserved, and I checked rather than assumed.** The concern with
the `_decision_cost` rewrite was that dropping the build object changes island
splicing and so could change the decision counts that license `@lexical` marks.
I ran the full report before and after and compared the row sets and directive
legends across all twelve grammars, ignoring speed ordering. They are identical,
so `_licensed_marks` selects the same marks by the public route.

Gates on the changed files: ruff check and format clean, pylint 10.00/10,
pyright 0 errors over `tools/benchmark/`.

### 6c — Result: half the A/B rows now cross

The A/B runs 72 rows, 12 grammars times 6 row types. I tested each row type
against the extracted base tree with a real worker invocation.

| Row type | Against base | Why |
|---|---|---|
| `lexic-pda` | **works** | drives `CompiledGrammar.parse`, identical in both |
| `lexic-lex` | **works** | same |
| `lexic-lex-ns` | **works** | same |
| `lexic-earley` | blocked | `earley_model` needs the model-build object |
| `lexic-mt` | blocked | `_mt_check`'s `Request` needs the model-build object |
| `lexic-mt-lex-ns` | blocked | same |

36 of 72 rows now cross the tree boundary. Before these changes, none did — the
harness failed at import.

### 6d — The irreducible residue, and why it is irreducible

Both blockers are the same single thing: **obtaining the model-build object from
a `CompiledGrammar`**. Base calls it `.fold`; HEAD calls it `.product`, with
`.executor` as a derived property.

Every model-product entry requires it as a positional parameter with no default:
`earley_model`, `parse_model`, `token_model`, `pda_tables`. `Request` requires
it too. The recognition-level entries that do accept `None` (`watch`,
`PdaKernel`) do not build a model, so they cannot serve a row whose measured
noun is a typed model.

I checked every place it could come from instead, and it comes from none of
them:

- Not `CompileMoments`. Its `binding` field is the `RuleMap` list, not the fold.
  Field names and types are identical in both trees, and neither holds it.
- Not `PdaTables`. Its annotations are `clones`, `start_key`, `island_follow`,
  `instance_grammar`, `program`, `_island_tables`. No build object.
- Not a builder in the shared `lexic.compile` surface. `synthesize` returns
  classes, `compute_binding` returns `RuleMap`s, `build_codegen_grammar`
  returns an `IrAst`. The fold is assembled inside the private `_compile_core`.
- Not an engine selector on `.parse` or `compile_text`. Neither has one, and the
  wiki is explicit that forcing a route means calling a different product entry.

The decisive constraint is that **the base tree is immutable**. Every name the
harness uses must already exist in base as shipped. Within that set the build
object is reachable only as `CompiledGrammar.fold`, which HEAD does not have.
No src change can help, because a new name added to HEAD still would not exist
in base.

That leaves only forms this brief forbids: a `getattr` fallback, or positional
dataclass access standing in for the renamed field. Both are compatibility
shims.

One nuance worth stating plainly, because it changes who owns the problem. The
coordinator's diagnosis was that the harness reaches into internals, and that
was true and worth fixing — `_model_product` and `pda_model` really were
private, and they are gone. But `CompiledGrammar.fold` was never internal. The
wiki's `CompiledGrammar` table documents it as a public field. So the residue is
not a harness sin; it is a **public field rename**, and no amount of harness
discipline can route around a public name that changed.

### 6e — The remaining option space

This is the user's call. I have no recommendation that avoids a real cost,
because each option pays somewhere.

1. **Keep the public name `fold` on `CompiledGrammar`** and rename only what is
   genuinely internal. The A/B goes green permanently and the harness stays on
   the public surface. Cost: this effort gives up part of its rename.
2. **Drop `lexic-earley`, `lexic-mt` and `lexic-mt-lex-ns` from the A/B for this
   PR**, restoring them after merge. The workflow goes green on 36 rows, and
   §6f shows those 36 currently pass with zero regression candidates and large
   wins, so this is not a gate that would go green by being blindfolded. Cost:
   the gate still loses the Earley and multithreaded rows for one PR, on the
   change that rewrites the product layer.
3. **Add a public accessor to base.** Not possible — base is a merged commit on
   `main`, and the A/B compares against it as shipped.

### 6f — The rerun, and what the measurable half says

The ruling asked for the compare rerun with its exit code recorded. On the
migrated tree:

```
uv run python -u -m tools.benchmark.compare \
  --base-source /tmp/lexic-base/src \
  --base-record /tmp/lexic-base/tools/benchmark/lexic_baseline.json
```

Exit code **1**. The failure has moved: it is no longer the import of
`ProductExecutor` but `bench.py:200`, `binding = bench.compiled.product`, raising
`AttributeError: 'CompiledGrammar' object has no attribute 'product'`. That is
the residue of §6d and nothing else.

Because a partial answer is more useful than none, I then ran the A/B over
exactly the 36 rows that do cross, using the harness's own `sample_pair` and
`medians` at the standard 7 first-pass rounds, base `/tmp/lexic-base/src`
against head `src`. **Zero rows regress.** The full table is below, sorted by
change, where negative means HEAD is faster.

| Row | base | head | change |
|---|---:|---:|---:|
| mixedends/lexic-lex | 0.310836 | 0.073199 | -76.45% |
| mixedends/lexic-lex-ns | 0.310596 | 0.073945 | -76.19% |
| announced/lexic-lex | 0.133364 | 0.042597 | -68.06% |
| announced/lexic-lex-ns | 0.132694 | 0.044567 | -66.41% |
| lexruns/lexic-lex | 0.180998 | 0.098333 | -45.67% |
| backtrack/lexic-lex | 0.186665 | 0.101651 | -45.54% |
| backtrack/lexic-lex-ns | 0.183476 | 0.101258 | -44.81% |
| lexruns/lexic-lex-ns | 0.179289 | 0.111280 | -37.93% |
| lexruns/lexic-pda | 0.209657 | 0.147827 | -29.49% |
| json/lexic-lex-ns | 1.080926 | 0.782206 | -27.64% |
| json/lexic-lex | 1.062300 | 0.827193 | -22.13% |
| backtrack/lexic-pda | 0.263025 | 0.205787 | -21.76% |
| markdown/lexic-lex | 0.750129 | 0.690807 | -7.91% |
| markdown/lexic-lex-ns | 0.737629 | 0.679759 | -7.85% |
| gbnf-meta/lexic-lex-ns | 2.322009 | 2.141754 | -7.76% |
| mixedends/lexic-pda | 0.534539 | 0.502937 | -5.91% |
| gbnf-meta/lexic-lex | 2.311583 | 2.218843 | -4.01% |
| json/lexic-pda | 1.274410 | 1.232288 | -3.31% |
| abnf-meta/lexic-lex | 2.189072 | 2.121492 | -3.09% |
| arithmetic/lexic-lex-ns | 1.905728 | 1.852353 | -2.80% |
| nested/lexic-lex | 1.282130 | 1.248211 | -2.65% |
| nested/lexic-pda | 1.260859 | 1.230564 | -2.40% |
| csv/lexic-lex-ns | 0.429432 | 0.421114 | -1.94% |
| arithmetic/lexic-pda | 2.108405 | 2.074087 | -1.63% |
| nested/lexic-lex-ns | 1.249250 | 1.230609 | -1.49% |
| vyx/lexic-lex-ns | 2.379675 | 2.352823 | -1.13% |
| csv/lexic-lex | 0.432482 | 0.427698 | -1.11% |
| abnf-meta/lexic-lex-ns | 1.862755 | 1.846064 | -0.90% |
| arithmetic/lexic-lex | 1.944343 | 1.928551 | -0.81% |
| vyx/lexic-lex | 2.405386 | 2.393968 | -0.47% |
| gbnf-meta/lexic-pda | 2.594460 | 2.585400 | -0.35% |
| markdown/lexic-pda | 0.943724 | 0.941321 | -0.25% |
| announced/lexic-pda | 0.195314 | 0.195787 | +0.24% |
| abnf-meta/lexic-pda | 2.284936 | 2.290521 | +0.24% |
| vyx/lexic-pda | 2.806333 | 2.821435 | +0.54% |
| csv/lexic-pda | 0.568320 | 0.574128 | +1.02% |

**>5% first-pass regression candidates: 0.** The worst row is `csv/lexic-pda` at
+1.02%, inside the noise band the identical-tree control measured in §3b
(±1.9%). Twelve rows are more than 20% faster and two are more than 75% faster.

This matters for the ruling. On every row the A/B can currently measure, this
effort is a large win with no regressions. The blocked rows are Earley and
multithreaded, so they are not covered by that statement and could still hide
something — but the gate's own threshold is not close to firing on the half that
runs.

`tools/benchmark/diagnostics/split_ab.py` still reaches `.executor` and
`_model_product` at line 103. It is a diagnostic, is not on the A/B path, and
moving its `pda` row to `CompiledGrammar.parse` would change what it measures —
the raw-kernel arm measures about 1.3% apart from the seam, which `bench.py`
records as having faked a `@lexical` regression once. I left it and am flagging
it rather than silently changing a measured noun.

---

## 5 — What must change before the remote is green

| # | Item | Evidence | Owner |
|---|---|---|---|
| 1 | Decide how the A/B gets a model-build object that base calls `.fold` and HEAD calls `.product` | §6d; 36 of 72 rows now cross, the other 36 are blocked on this one name | **src / user ruling.** Either keep `fold` as the public field name, or drop three row types from the A/B for this PR. §6e states both costs |
| 2 | 46 pylint findings in `src/`, all introduced by this effort | §4; base is 10.00/10, exit 0 | **src / coordinator ruling.** Bulk is 28 `Carry` shadowing warnings across four files |
| 3 | R0801 duplicate between `engine.py` and `products.py` | §4; 13 identical lines, grown from 5 by the `another_meaning` to `different_meaning` change | **src.** Extract into `ambiguity.py`, the module that already owns `MeaningBuilder` and `different_meaning` |
| 4 | E1136 on `frame[F_ENDS]` | `tests/unit/lexic/parsing/pda/runtime/kernel/test_decisions.py:106` | **tests** |
| 5 | Duplicated comment banner | `src/lexic/parsing/products.py:183-184` | **src.** Delete one line |
| 6 | `split_ab.py` stale root path | §3a; pure rename left `parents[2]` a level short | **tools — done by me.** One line, verified |
| 6b | Harness reaching into `_model_product`, `pda_model`, `PdaFail`, and a dead `ProductExecutor` import | §6b | **tools — done by me.** All four gone; 36 rows now cross |
| 6c | `split_ab.py` still reaches `.executor` and `_model_product` | §6e | **tools, deliberately not done.** Off the A/B path; changing it would change the measured noun |
| 7 | Ratchet fails on HEAD and on base | §3c; different rows on each tree, all multithreaded | **Neither, on current evidence.** Gates `pre-commit`, not any workflow. Needs a run on the recording machine or the CI runner to settle whether the parallel layer is healthy |

Items 2, 3 and 5 are what the `checks` workflow is red on. Item 1 is what the
`performance` workflow is red on. Items 6 and 7 touch neither remote.

Nothing in `src/` or `tests/` was edited. Nothing was committed.

---

## §7 — Per-tree workers and the replaced measurement protocol (2026-09-03)

Review 17 item 6, implemented in full with no compatibility branch. The user's
earlier `git restore tools/` discarded the §6 migration; this section is built
from scratch on the restored tree and does not depend on it.

### 7a — The invariant, restated

The old invariant was *one harness held constant while `lexic` is swapped
underneath it*. It cannot survive a public rename by construction, because the
harness must name the API it drives. Worse, it was already false: the harness
reached past the public surface, so the rename only made the breakage visible.

The replacement: **row definitions are held constant by NAME; each arm's worker
code is its own tree's.** What is held constant is the ROW — grammar, declared
directives, document, engine noun, core request — and the comparator refuses two
arms whose row contracts differ before it times anything. Running a historical
revision with its historical benchmark measures that baseline; it is not support
for that revision's API in current Lexic.

Both arms still receive the corrected protocol. Comparing a corrected arm
against an uncorrected one measures the harness, not Lexic. Each copy keeps only
its native API reference and neither `src` tree is touched.

### 7b — What changed, against each finding

| Review 17 finding | What now happens |
|---|---|
| The comparator ran the current harness against both APIs | `Job` owns a checkout root. The subprocess runs with that root as `cwd` and that checkout's `src` and root first on `PYTHONPATH` |
| "Uncontended" preparation overlapped real parses | The cohort and `_PREPARE_WIDTH` are deleted. `run_job` starts one process, it completes start/build/validate/warm/time/close/exit, and only then does the next start |
| The execution-mode ratchet compared different documents | Relations are gone from the ratchet. `measurement/health.py` measures core counts against ONE identical full document, with its digest and byte length in the contract |
| The acceptance clock and collector state did not match production | The collector stays enabled during every timed pass and the contract records it. Both `process_time` and `perf_counter` are recorded on every observation |
| A row's directives depended on the implementation | `_licensed_marks`, `_decision_cost` and `variant_marks` are deleted. `cases/directives.py` declares each case's exact sets, validated against the grammar as a language question only |
| The fixed baseline and five-percent rule cannot be the gate | Paired base/head log ratios against a byte-identical control envelope with a predeclared 95% interval. No five-percent rule, no `--accept-regression`, no `accepted_rows`. `lexic_baseline.json` is trend data only |
| A hook cannot establish comparable hardware | `regression.py` is now the row-contract and structure gate. It times nothing |

Deleting the directive licence is behaviour-neutral on the current fixture set,
and I checked that before deleting rather than after. `_licensed_marks` dropped
zero marks on all twelve grammars, and every raw-mark variant compiles and
parses. The derived sets are also identical in both trees, which is why the
declarations produce contracts that compare equal.

### 7c — The row contract

Every result carries protocol version, row and grammar identity, grammar-source
digest, exact directives, document digest and byte length, scale, engine noun,
requested cores, collector state, and the clocks recorded. `_agree` refuses a
mismatch by naming the fields that differ, before timing counts.

One process-level observation carries wall, process CPU, result digest, semantic
verdict, MT engagement and effective cores. The independent unit is the process:
inner passes are reduced to one observation so a warm allocator inside one
interpreter cannot be counted as several independent samples.

The MT rows immediately showed what one clock was hiding. On `json`, a threaded
row reads 16.2 ms wall against 56.0 ms process CPU — a latency win bought with
3.4x the total CPU, which the old wall-only worker could not express.

### 7d — Reproducing the measurement copy

Base sha is `git merge-base main HEAD`, currently
`0faa72899580af749316e3964f734a4570577055`. Extracted outside the repo, never a
worktree:

```
rm -rf /tmp/lexic-base && mkdir -p /tmp/lexic-base
git archive 0faa7289... | tar -x -C /tmp/lexic-base
uv run python -m tools.benchmark.measurement.copy /tmp/lexic-base --rename fold
```

`measurement/copy.py` IS the instrumentation patch, made reproducible: it
installs the protocol modules and rewrites the one name the rename moved. Base
`src` was verified byte-identical to its revision afterwards.

Both trees then report `12 grammars, 72 rows, protocol 3 — contracts intact`.

### 7e — The first local 72-row run

Command, exactly as `performance.yml` now runs it:

```
uv run python -u -m tools.benchmark.compare \
  --base-root /tmp/lexic-base \
  --head-root . \
  --json /tmp/vega_ab72.json
```

Exit code **1**, about forty minutes, all 72 rows compared. Every row's contract
matched between arms, so nothing was refused before timing.

**No row is slower.** Zero rows carry the `slower` verdict. 60 rows resolved and
12 are inconclusive; the exit code is entirely the inconclusive ones.

That is the protocol declining to guess rather than a regression. This machine
was not quiet — it ran builds, the suite, pylint and pyright throughout — and a
row whose candidate interval is wider than the control envelope earns more
pairs, then reports inconclusive at the bound. Forcing those into a median is
exactly what the previous confirmation step did and what the review removed.

The control's median log ratio over the whole run is 1.0000x, so the
byte-identical arms agree to four decimal places while the envelope stays wide
enough per row to absorb this machine's noise.

The 12 inconclusive rows, with their intervals:

| row | interval |
|---|---|
| abnf-meta/lexic-lex | 0.9838..1.0031 |
| abnf-meta/lexic-mt | 0.9690..1.0227 |
| abnf-meta/lexic-mt-lex-ns | 0.9746..1.0240 |
| arithmetic/lexic-lex-ns | 0.9947..1.0529 |
| backtrack/lexic-mt | 0.8237..0.9389 |
| csv/lexic-lex-ns | 0.9661..1.0030 |
| gbnf-meta/lexic-mt | 1.0088..1.0376 |
| gbnf-meta/lexic-mt-lex-ns | 0.9706..0.9863 |
| markdown/lexic-pda | 1.0059..1.0244 |
| mixedends/lexic-mt | 0.9407..0.9989 |
| nested/lexic-lex | 0.9822..1.0001 |
| nested/lexic-mt | 0.9327..1.0277 |

Eight of the twelve are `lexic-mt` rows, whose wall clock carries real thread
scheduling variance on a contended host. The remainder straddle the envelope by
under two percent.

I tried raising the inner passes per observation from 5 to 15 to narrow each
reading. It tripled the run — two grammars did not finish in ten minutes where
all seventy-two finish in forty — and I reverted it. The honest lever for an
inconclusive row is a quieter machine, not a longer inner loop, and tuning the
statistics until my own gate passes is the behaviour this review removed.

### 7f — Every row, as measured

Negative is faster. `noise` is the control envelope that row was judged against.

| row | clock | ratio | ci low | ci high | noise | pairs | status |
|---|---|---:|---:|---:|---:|---:|---|
| arithmetic/lexic-lex-ns | cpu | 1.0234 | 0.9947 | 1.0529 | 1.0457 | 15 | unresolved |
| gbnf-meta/lexic-mt | wall | 1.0231 | 1.0088 | 1.0376 | 1.0221 | 15 | unresolved |
| vyx/lexic-mt-lex-ns | wall | 1.0205 | 1.0123 | 1.0289 | 1.0490 | 5 | ok |
| arithmetic/lexic-mt | wall | 1.0196 | 1.0139 | 1.0253 | 1.0358 | 5 | ok |
| arithmetic/lexic-lex | cpu | 1.0156 | 0.9988 | 1.0327 | 1.0336 | 11 | ok |
| announced/lexic-mt | wall | 1.0152 | 0.9558 | 1.0783 | 1.1890 | 5 | ok |
| markdown/lexic-pda | cpu | 1.0151 | 1.0059 | 1.0244 | 1.0116 | 15 | unresolved |
| markdown/lexic-mt | wall | 1.0118 | 0.9696 | 1.0558 | 1.0722 | 5 | ok |
| csv/lexic-mt | wall | 1.0115 | 0.9845 | 1.0393 | 1.0452 | 5 | ok |
| announced/lexic-pda | cpu | 1.0110 | 0.9927 | 1.0296 | 1.0345 | 5 | ok |
| vyx/lexic-mt | wall | 1.0109 | 1.0020 | 1.0199 | 1.0217 | 9 | ok |
| abnf-meta/lexic-pda | cpu | 1.0103 | 0.9978 | 1.0230 | 1.0235 | 8 | ok |
| gbnf-meta/lexic-pda | cpu | 1.0099 | 1.0015 | 1.0183 | 1.0301 | 5 | ok |
| nested/lexic-mt-lex-ns | wall | 1.0087 | 0.9929 | 1.0248 | 1.0258 | 5 | ok |
| json/lexic-pda | cpu | 1.0063 | 0.9965 | 1.0161 | 1.0178 | 15 | ok |
| arithmetic/lexic-pda | cpu | 1.0058 | 0.9804 | 1.0319 | 1.0555 | 5 | ok |
| csv/lexic-pda | cpu | 1.0042 | 0.9861 | 1.0226 | 1.0264 | 5 | ok |
| json/lexic-mt | wall | 1.0038 | 0.9876 | 1.0203 | 1.0775 | 7 | ok |
| csv/lexic-mt-lex-ns | wall | 1.0033 | 0.9501 | 1.0595 | 1.1022 | 5 | ok |
| vyx/lexic-pda | cpu | 1.0028 | 0.9906 | 1.0152 | 1.0187 | 5 | ok |
| csv/lexic-lex | cpu | 0.9996 | 0.9804 | 1.0190 | 1.0225 | 5 | ok |
| abnf-meta/lexic-mt-lex-ns | wall | 0.9990 | 0.9746 | 1.0240 | 1.0247 | 15 | unresolved |
| vyx/lexic-lex | cpu | 0.9972 | 0.9906 | 1.0039 | 1.0134 | 9 | ok |
| abnf-meta/lexic-lex-ns | cpu | 0.9960 | 0.9897 | 1.0023 | 1.0190 | 5 | ok |
| nested/lexic-pda | cpu | 0.9958 | 0.9891 | 1.0026 | 1.0224 | 5 | ok |
| abnf-meta/lexic-mt | wall | 0.9955 | 0.9690 | 1.0227 | 1.0211 | 15 | unresolved |
| nested/lexic-lex-ns | cpu | 0.9936 | 0.9872 | 1.0000 | 1.0452 | 5 | ok |
| abnf-meta/lexic-lex | cpu | 0.9934 | 0.9838 | 1.0031 | 1.0119 | 15 | unresolved |
| arithmetic/lexic-mt-lex-ns | wall | 0.9916 | 0.9655 | 1.0184 | 1.1135 | 5 | ok |
| nested/lexic-lex | cpu | 0.9911 | 0.9822 | 1.0001 | 1.0079 | 15 | unresolved |
| vyx/lexic-lex-ns | cpu | 0.9902 | 0.9823 | 0.9982 | 1.0217 | 5 | ok |
| markdown/lexic-mt-lex-ns | wall | 0.9894 | 0.9451 | 1.0358 | 1.0605 | 10 | ok |
| csv/lexic-lex-ns | cpu | 0.9844 | 0.9661 | 1.0030 | 1.0235 | 15 | unresolved |
| nested/lexic-mt | wall | 0.9791 | 0.9327 | 1.0277 | 1.0259 | 15 | unresolved |
| gbnf-meta/lexic-mt-lex-ns | wall | 0.9784 | 0.9706 | 0.9863 | 1.0268 | 15 | unresolved |
| mixedends/lexic-mt | wall | 0.9694 | 0.9407 | 0.9989 | 1.0352 | 15 | unresolved |
| gbnf-meta/lexic-lex-ns | cpu | 0.9624 | 0.9493 | 0.9758 | 1.0235 | 8 | faster |
| gbnf-meta/lexic-lex | cpu | 0.9496 | 0.9370 | 0.9622 | 1.0117 | 5 | faster |
| markdown/lexic-lex-ns | cpu | 0.9487 | 0.9287 | 0.9691 | 1.0211 | 5 | faster |
| mixedends/lexic-pda | cpu | 0.9473 | 0.9414 | 0.9533 | 1.0373 | 5 | faster |
| markdown/lexic-lex | cpu | 0.9460 | 0.9250 | 0.9675 | 1.0301 | 6 | faster |
| lexruns/lexic-earley | cpu | 0.9116 | 0.9050 | 0.9183 | 1.0142 | 5 | faster |
| backtrack/lexic-mt | wall | 0.8794 | 0.8237 | 0.9389 | 1.0878 | 15 | unresolved |
| vyx/lexic-earley | cpu | 0.8692 | 0.8595 | 0.8789 | 1.0063 | 5 | faster |
| json/lexic-mt-lex-ns | wall | 0.8636 | 0.8530 | 0.8743 | 1.0321 | 5 | faster |
| gbnf-meta/lexic-earley | cpu | 0.8614 | 0.8478 | 0.8752 | 1.0088 | 5 | faster |
| abnf-meta/lexic-earley | cpu | 0.8566 | 0.8487 | 0.8647 | 1.0101 | 5 | faster |
| markdown/lexic-earley | cpu | 0.8394 | 0.8292 | 0.8497 | 1.0201 | 5 | faster |
| backtrack/lexic-earley | cpu | 0.8363 | 0.8264 | 0.8463 | 1.0108 | 5 | faster |
| announced/lexic-earley | cpu | 0.8339 | 0.8255 | 0.8424 | 1.0130 | 5 | faster |
| mixedends/lexic-earley | cpu | 0.8272 | 0.8202 | 0.8343 | 1.0206 | 5 | faster |
| nested/lexic-earley | cpu | 0.8164 | 0.8103 | 0.8225 | 1.0119 | 5 | faster |
| lexruns/lexic-mt | wall | 0.8070 | 0.7861 | 0.8285 | 1.0195 | 5 | faster |
| json/lexic-earley | cpu | 0.7916 | 0.7875 | 0.7957 | 1.0178 | 5 | faster |
| backtrack/lexic-pda | cpu | 0.7845 | 0.7806 | 0.7885 | 1.0188 | 5 | faster |
| csv/lexic-earley | cpu | 0.7820 | 0.7550 | 0.8099 | 1.0411 | 5 | faster |
| arithmetic/lexic-earley | cpu | 0.7756 | 0.7706 | 0.7807 | 1.0106 | 5 | faster |
| json/lexic-lex | cpu | 0.7721 | 0.7509 | 0.7938 | 1.0217 | 5 | faster |
| json/lexic-lex-ns | cpu | 0.7551 | 0.7413 | 0.7691 | 1.0418 | 5 | faster |
| lexruns/lexic-pda | cpu | 0.7281 | 0.7022 | 0.7551 | 1.0071 | 5 | faster |
| backtrack/lexic-mt-lex-ns | wall | 0.6930 | 0.6736 | 0.7130 | 1.0219 | 5 | faster |
| lexruns/lexic-mt-lex-ns | wall | 0.6779 | 0.6231 | 0.7375 | 1.0462 | 5 | faster |
| lexruns/lexic-lex | cpu | 0.5769 | 0.5639 | 0.5901 | 1.0343 | 5 | faster |
| backtrack/lexic-lex-ns | cpu | 0.5633 | 0.5355 | 0.5926 | 1.0485 | 5 | faster |
| announced/lexic-mt-lex-ns | wall | 0.5627 | 0.4927 | 0.6427 | 1.0498 | 5 | faster |
| lexruns/lexic-lex-ns | cpu | 0.5599 | 0.5462 | 0.5740 | 1.0300 | 5 | faster |
| mixedends/lexic-mt-lex-ns | wall | 0.5469 | 0.5247 | 0.5699 | 1.2246 | 5 | faster |
| backtrack/lexic-lex | cpu | 0.5403 | 0.5322 | 0.5486 | 1.0139 | 5 | faster |
| announced/lexic-lex | cpu | 0.3215 | 0.3104 | 0.3331 | 1.0245 | 5 | faster |
| announced/lexic-lex-ns | cpu | 0.3186 | 0.3111 | 0.3262 | 1.0165 | 5 | faster |
| mixedends/lexic-lex | cpu | 0.2408 | 0.2369 | 0.2448 | 1.0320 | 5 | faster |
| mixedends/lexic-lex-ns | cpu | 0.2386 | 0.2360 | 0.2412 | 1.0187 | 5 | faster |
### 7g — What still blocks, and who owns it

| Item | Evidence | Owner |
|---|---|---|
| `test_benchmark_emitters.py` imports the deleted `variant_marks` | With the module restored all 95 invariants tests pass; deleted, collection fails and takes the README tests-badge with it | **tests.** Two lines: import `declared_marks` from `cases.grammars`, and call it with `bench` rather than `bench.ast` |
| `test_regression.py` pins the deleted ratchet | 13 tests over `assess`, `Confirmed`, the five-percent rule and `--accept-regression` | **tests.** Target symbols are the ones the ruling deletes |
| `test_compare.py` pins the deleted sampler | 4 tests over `IsolatedRow`, `save` and baseline-diff acceptance | **tests.** Same |
| 12 rows inconclusive locally | §7e; zero rows slower | **the quiet-machine window**, which is item 7 |

Everything under `tools/benchmark` passes ruff, ruff format, pylint 10.00/10 and
pyright with zero errors. Four pylint findings were fixed at the root rather
than suppressed: a six-argument sampler split behind an `Arms` record, two
NamedTuple `_fields` reads moved to `__annotations__`, and an unused parameter
removed. Two source-structure invariants also failed on the new files and were
fixed by splitting rather than by raising a limit — the directive declarations
moved to `cases/directives.py`, and the instrument moved to `measurement/`.

Nothing in `src/` or `tests/` was edited. Nothing was committed.

### 7h — The three benchmark test files, deleted and ported

A scoped exception covered exactly three files under `tests/`. Every test whose
exact subject the ruling deleted is gone; every assertion whose BEHAVIOUR
survives is re-pinned against the replacement.

**`tests/integration/lexic/invariants/test_benchmark_emitters.py`** — the
two-line port. It now imports `declared_marks` from `cases.grammars` and calls
it with the bench rather than its AST, so the competitor seats face the same
declared directives lexic's variant rows compile with.

**`tests/unit/tools/benchmark/test_compare.py`** — four tests in, seventeen out.

| Deleted, subject died | Why |
|---|---|
| `test_confirmation_aggregates_three_exact_ab_batches_before_deciding` | the batch `confirm` is gone |
| `test_baseline_increase_is_the_reviewable_ci_acceptance` | `accepted_rows`, `save` and the baseline exemption are gone |
| `test_a_base_without_a_record_still_runs_source_comparison` | `--base-record` is gone |

`test_pair_sampler_alternates_which_source_tree_runs_first` survived and is
re-pinned as `test_pairs_alternate_which_tree_runs_first`, over checkout roots
rather than source directories.

Added: control order flipping on its own schedule; contract agreement; a
one-field mismatch refusing and naming that field; a mismatch naming every
differing field; a differing collector state refusing; identical contracts
agreeing; a refused row stopping the run rather than scoring zero; the four
verdicts; the envelope widening with a noisy control so the same candidate stops
reading as a regression; an overlapping interval earning pairs to the bound and
then reporting unresolved; wall for threaded rows and CPU for sequential; and
all three exit paths, including that an unresolved row blocks.

**`tests/unit/tools/benchmark/test_regression.py`** — thirteen in, seventeen
out. All thirteen deleted: their whole subject was `assess`, `Confirmed`,
`save`, the five-percent threshold, `--accept-regression`, and the execution
relations that compared two different documents.

Added, against the structure gate: the intact fixture set; the hook's success
path; twelve grammars and seventy-two rows pinned as a product; a missing
grammar failing rather than shrinking the gate; every row named by both legend
tables; the gate reading no clock at all, enforced by monkeypatching both clocks
to raise; a directive naming an unknown rule refusing; an unsorted declaration
refusing, since sorted order is what lets two arms' contracts compare equal;
every shipped declaration validating against its grammar; a threaded row reading
the full document and a sequential one the corpus; both threaded rows sharing
one document digest; only variant rows carrying directives; the collector
recorded as enabled and a disabled one refusing; every contract round-tripping
through its wire form; and a foreign protocol refusing.

**One design correction the tests forced.** The first ordering assertions failed
because the implementation was genuinely confusing: the control's ratio call
passed its two jobs in an order whose labels read backwards, so `control-a` ran
second by default. `_ratio` now takes `numerator_first`, which says plainly
which process runs first, and the control flips which of its two identical
processes is on top of the ratio — which is what makes slot drift average out
instead of accumulating a sign.

The functions the tests exercise were promoted from protected to public names,
rather than reaching past an underscore: `decide`, `agree`, `sample`, `require`,
`grow`, `rosters` and `primary_reading` in `compare`, and `row_contract` in
`regression`. That is each module's testable surface and it should have been
named as such.

**A fourth file needs the same treatment and was outside the exception.**
`tests/unit/tools/benchmark/test_worker.py` has two failing tests whose subject
symbols this redesign renamed, `worker.execute` and `isolation.run_row`. Unlike
the ratchet tests, both have behaviour that fully survives, so they want porting
rather than deleting: one asserts the worker cannot silently expand one row into
a roster, the other that the parent passes one grammar and one engine across the
process boundary with the right flags and path. Those two lines are the only
remaining pyright errors in the repo and the only remaining test failures, so
`run_checks.sh` cannot exit 0 until they are ported. The file was not touched.

### 7i — Optional stopping, found by the gate's own second run

The second full run produced one `slower` verdict: `markdown/lexic-pda` at
1.0354x on CPU, interval 1.0088..1.0627 against an envelope of 1.0087, decided
at six pairs. The interval's lower bound cleared the envelope by 0.0001.

That is a verdict taken at the first moment the threshold tipped, which is
optional stopping, and optional stopping manufactures regressions. The growth
loop only grew while a row was `unresolved`, so a row that crossed on noise at
pair six banked the crossing and stopped collecting the evidence that would have
taken it back.

Three measurements of that row make the point:

| Run | ratio | interval | envelope | pairs | verdict |
|---|---:|---|---:|---:|---|
| first | 1.0151 | 1.0059..1.0244 | 1.0116 | 15 | unresolved |
| second | 1.0354 | 1.0088..1.0627 | 1.0087 | 6 | **slower** |
| third | 1.0189 | 1.0099..1.0279 | 1.0506 | 5 | ok |

The fix is that `slower` now grows too. A measured regression is the most
expensive verdict this gate issues, so it is the one that must survive the whole
pair budget. Growing can only add evidence: a real slowdown stays slower with a
tighter interval, while one that tipped on noise returns inside the envelope.
Two tests pin it — a persistently slow row still reads `slower` after consuming
the full budget, and a row that tips early then settles does not read `slower`.

**The residual signal is worth naming even though no run confirmed it.**
`markdown/lexic-pda` sits above 1.0 in all three measurements, at 1.0151,
1.0354 and 1.0189. That is a consistent 1.5–3.5% CPU drift on markdown's plain
predictive row, never confirmed above this machine's envelope. `markdown`'s
variant rows move the other way in every run, at roughly 0.94–0.95, and its
Earley row at 0.85. I did not investigate or change any of it: this is a
`src` question, and the quiet-machine run with a tighter envelope is what should
settle whether the drift is real.

### 7j — The final 72-row run, under the shipped code

Rerun after the optional-stopping fix, so the numbers match the code as landed.
Base copy rebuilt from the same sha; digests base `ff86524371a899ed`, head
`0e77fbfdb5d4f927`.

```
uv run python -u -m tools.benchmark.compare \
  --base-root /tmp/lexic-base \
  --head-root . \
  --json /tmp/vega_ab72c.json
```

Exit code **1**, all 72 rows compared, every contract matched.

| verdict | rows |
|---|---:|
| slower | **0** |
| faster | 36 |
| ok | 25 |
| unresolved | 11 |

Control median log ratio across the whole run: **1.0007x**. The byte-identical
arms agree to within 0.07 percent while each row's envelope stays wide enough to
carry this host's noise.

**No row is slower.** The one `slower` verdict from the previous run was
optional stopping and is gone: `markdown/lexic-pda` now reads 1.0051x, interval
0.9932..1.0170, inside an envelope of 1.0179. Over four measurements that row
has read 1.0151, 1.0354, 1.0189 and 1.0051, so the drift is real but small and
has never survived a full pair budget. The quiet machine should settle it.

The exit code is entirely the 11 inconclusive rows:

| row | interval |
|---|---|
| abnf-meta/lexic-lex-ns | 0.9796..1.0054 |
| arithmetic/lexic-lex-ns | 0.9989..1.0235 |
| arithmetic/lexic-mt | 0.9620..1.0568 |
| csv/lexic-mt | 0.9837..1.0286 |
| gbnf-meta/lexic-mt | 1.0118..1.0288 |
| gbnf-meta/lexic-pda | 1.0059..1.0193 |
| json/lexic-mt | 0.8667..1.0656 |
| json/lexic-pda | 0.9933..1.0513 |
| nested/lexic-lex | 0.9771..0.9987 |
| nested/lexic-pda | 0.9858..1.0091 |
| vyx/lexic-pda | 0.9975..1.0128 |

Five are `lexic-mt`, whose wall clock carries real scheduling variance on a
contended host. The rest straddle the envelope by two percent or less. This
machine ran the suite, pylint and pyright throughout; a quiet machine is the
remedy, and it is what item 7 is for.

### 7k — Every row, as finally measured

Negative is faster. `noise` is the control envelope that row was judged against.

| row | clock | ratio | ci low | ci high | noise | pairs | status |
|---|---|---:|---:|---:|---:|---:|---|
| json/lexic-pda | cpu | 1.0219 | 0.9933 | 1.0513 | 1.0244 | 15 | unresolved |
| gbnf-meta/lexic-mt | wall | 1.0203 | 1.0118 | 1.0288 | 1.0150 | 15 | unresolved |
| markdown/lexic-mt | wall | 1.0189 | 0.9864 | 1.0524 | 1.0898 | 7 | ok |
| csv/lexic-mt-lex-ns | wall | 1.0161 | 0.9838 | 1.0493 | 1.0588 | 5 | ok |
| nested/lexic-mt-lex-ns | wall | 1.0143 | 0.9929 | 1.0361 | 1.0415 | 7 | ok |
| gbnf-meta/lexic-pda | cpu | 1.0126 | 1.0059 | 1.0193 | 1.0117 | 15 | unresolved |
| arithmetic/lexic-lex-ns | cpu | 1.0111 | 0.9989 | 1.0235 | 1.0138 | 15 | unresolved |
| announced/lexic-mt | wall | 1.0088 | 0.9560 | 1.0645 | 1.1511 | 13 | ok |
| arithmetic/lexic-mt-lex-ns | wall | 1.0084 | 0.9950 | 1.0219 | 1.0838 | 5 | ok |
| arithmetic/lexic-mt | wall | 1.0083 | 0.9620 | 1.0568 | 1.0172 | 15 | unresolved |
| nested/lexic-mt | wall | 1.0082 | 0.9856 | 1.0313 | 1.0494 | 5 | ok |
| abnf-meta/lexic-pda | cpu | 1.0074 | 0.9963 | 1.0185 | 1.0204 | 8 | ok |
| abnf-meta/lexic-mt-lex-ns | wall | 1.0068 | 0.9876 | 1.0265 | 1.0280 | 9 | ok |
| csv/lexic-mt | wall | 1.0059 | 0.9837 | 1.0286 | 1.0165 | 15 | unresolved |
| arithmetic/lexic-pda | cpu | 1.0053 | 0.9841 | 1.0271 | 1.0326 | 9 | ok |
| vyx/lexic-pda | cpu | 1.0051 | 0.9975 | 1.0128 | 1.0096 | 15 | unresolved |
| markdown/lexic-pda | cpu | 1.0051 | 0.9932 | 1.0170 | 1.0179 | 5 | ok |
| vyx/lexic-mt-lex-ns | wall | 1.0050 | 0.9809 | 1.0297 | 1.0369 | 5 | ok |
| vyx/lexic-lex-ns | cpu | 1.0028 | 0.9912 | 1.0146 | 1.0179 | 8 | ok |
| arithmetic/lexic-lex | cpu | 1.0019 | 0.9883 | 1.0158 | 1.0210 | 5 | ok |
| csv/lexic-lex | cpu | 1.0012 | 0.9786 | 1.0244 | 1.0398 | 5 | ok |
| abnf-meta/lexic-lex | cpu | 0.9999 | 0.9839 | 1.0161 | 1.0297 | 5 | ok |
| nested/lexic-pda | cpu | 0.9974 | 0.9858 | 1.0091 | 1.0079 | 15 | unresolved |
| csv/lexic-pda | cpu | 0.9961 | 0.9800 | 1.0124 | 1.0215 | 9 | ok |
| nested/lexic-lex-ns | cpu | 0.9957 | 0.9919 | 0.9995 | 1.0209 | 5 | ok |
| csv/lexic-lex-ns | cpu | 0.9951 | 0.9825 | 1.0079 | 1.0192 | 12 | ok |
| announced/lexic-pda | cpu | 0.9942 | 0.9835 | 1.0049 | 1.1351 | 5 | ok |
| vyx/lexic-lex | cpu | 0.9932 | 0.9785 | 1.0081 | 1.0316 | 5 | ok |
| abnf-meta/lexic-lex-ns | cpu | 0.9924 | 0.9796 | 1.0054 | 1.0102 | 15 | unresolved |
| abnf-meta/lexic-mt | wall | 0.9921 | 0.9393 | 1.0479 | 1.0738 | 5 | ok |
| vyx/lexic-mt | wall | 0.9912 | 0.9726 | 1.0102 | 1.0426 | 5 | ok |
| nested/lexic-lex | cpu | 0.9878 | 0.9771 | 0.9987 | 1.0077 | 15 | unresolved |
| gbnf-meta/lexic-lex | cpu | 0.9688 | 0.9583 | 0.9795 | 1.0165 | 5 | faster |
| markdown/lexic-lex-ns | cpu | 0.9626 | 0.9528 | 0.9726 | 1.0229 | 5 | faster |
| json/lexic-mt | wall | 0.9610 | 0.8667 | 1.0656 | 1.0224 | 15 | unresolved |
| gbnf-meta/lexic-mt-lex-ns | wall | 0.9557 | 0.9371 | 0.9747 | 1.1270 | 5 | ok |
| mixedends/lexic-mt | wall | 0.9547 | 0.9166 | 0.9944 | 1.1064 | 5 | ok |
| markdown/lexic-lex | cpu | 0.9523 | 0.9238 | 0.9816 | 1.0159 | 6 | faster |
| gbnf-meta/lexic-lex-ns | cpu | 0.9458 | 0.9252 | 0.9669 | 1.0127 | 5 | faster |
| backtrack/lexic-mt | wall | 0.9299 | 0.8989 | 0.9621 | 1.0210 | 5 | faster |
| mixedends/lexic-pda | cpu | 0.9272 | 0.9141 | 0.9404 | 1.0555 | 7 | faster |
| markdown/lexic-mt-lex-ns | wall | 0.9212 | 0.8763 | 0.9684 | 1.1687 | 14 | ok |
| lexruns/lexic-earley | cpu | 0.9038 | 0.8970 | 0.9106 | 1.0053 | 5 | faster |
| lexruns/lexic-mt | wall | 0.8794 | 0.8300 | 0.9317 | 1.0559 | 5 | faster |
| vyx/lexic-earley | cpu | 0.8782 | 0.8645 | 0.8921 | 1.0147 | 5 | faster |
| gbnf-meta/lexic-earley | cpu | 0.8638 | 0.8562 | 0.8714 | 1.0172 | 5 | faster |
| abnf-meta/lexic-earley | cpu | 0.8601 | 0.8489 | 0.8714 | 1.0098 | 5 | faster |
| json/lexic-mt-lex-ns | wall | 0.8553 | 0.8354 | 0.8757 | 1.0718 | 5 | faster |
| markdown/lexic-earley | cpu | 0.8526 | 0.8483 | 0.8568 | 1.0377 | 5 | faster |
| mixedends/lexic-earley | cpu | 0.8334 | 0.8258 | 0.8411 | 1.0090 | 5 | faster |
| backtrack/lexic-earley | cpu | 0.8333 | 0.8273 | 0.8394 | 1.0148 | 5 | faster |
| announced/lexic-earley | cpu | 0.8309 | 0.8274 | 0.8345 | 1.0160 | 5 | faster |
| nested/lexic-earley | cpu | 0.8159 | 0.8045 | 0.8274 | 1.0164 | 5 | faster |
| csv/lexic-earley | cpu | 0.8065 | 0.7913 | 0.8220 | 1.0585 | 5 | faster |
| backtrack/lexic-pda | cpu | 0.7960 | 0.7862 | 0.8060 | 1.0324 | 5 | faster |
| json/lexic-earley | cpu | 0.7891 | 0.7819 | 0.7964 | 1.0157 | 5 | faster |
| arithmetic/lexic-earley | cpu | 0.7860 | 0.7651 | 0.8075 | 1.0101 | 5 | faster |
| json/lexic-lex-ns | cpu | 0.7693 | 0.7593 | 0.7794 | 1.0277 | 5 | faster |
| json/lexic-lex | cpu | 0.7621 | 0.7524 | 0.7719 | 1.0339 | 5 | faster |
| lexruns/lexic-pda | cpu | 0.7059 | 0.6875 | 0.7248 | 1.0604 | 5 | faster |
| lexruns/lexic-mt-lex-ns | wall | 0.7028 | 0.6821 | 0.7241 | 1.0389 | 5 | faster |
| backtrack/lexic-mt-lex-ns | wall | 0.6676 | 0.6545 | 0.6809 | 1.1323 | 5 | faster |
| mixedends/lexic-mt-lex-ns | wall | 0.5736 | 0.5220 | 0.6304 | 1.1179 | 5 | faster |
| lexruns/lexic-lex-ns | cpu | 0.5687 | 0.5537 | 0.5842 | 1.0316 | 5 | faster |
| lexruns/lexic-lex | cpu | 0.5576 | 0.5403 | 0.5753 | 1.1671 | 5 | faster |
| backtrack/lexic-lex | cpu | 0.5516 | 0.5400 | 0.5634 | 1.1598 | 5 | faster |
| backtrack/lexic-lex-ns | cpu | 0.5494 | 0.5421 | 0.5568 | 1.0154 | 5 | faster |
| announced/lexic-mt-lex-ns | wall | 0.5367 | 0.5209 | 0.5530 | 1.0323 | 5 | faster |
| announced/lexic-lex-ns | cpu | 0.3178 | 0.3151 | 0.3204 | 1.0361 | 5 | faster |
| announced/lexic-lex | cpu | 0.3095 | 0.2935 | 0.3264 | 1.0252 | 5 | faster |
| mixedends/lexic-lex-ns | cpu | 0.2384 | 0.2320 | 0.2450 | 1.0106 | 5 | faster |
| mixedends/lexic-lex | cpu | 0.2375 | 0.2324 | 0.2426 | 1.0112 | 5 | faster |

---

## §8 — Item 7: the quiet-machine window (2026-09-04)

Run under WINDOW GRANTED, nothing else of mine on the machine. Base sha
`git merge-base main HEAD` = `0faa72899580af749316e3964f734a4570577055`,
extracted with `git archive` outside the repo, corrected with
`measurement/copy.py --rename fold`, and verified byte-identical to its revision
afterwards. Both trees reported `12 grammars, 72 rows, protocol 3 — contracts
intact` before timing.

| | digest |
|---|---|
| base measurement copy | `b95c767cbc39e63f` |
| head | `b675533b50ad73ed` |

### 8a — The 72-row compare

```
uv run python -u -m tools.benchmark.compare \
  --base-root /tmp/lexic-base --head-root . --json /tmp/vega_window_ab.json
```

Exit code **1**, all 72 rows compared, every contract matched.

| verdict | rows |
|---|---:|
| slower | **0** |
| faster | 36 |
| ok | 27 |
| unresolved | 9 |

Control median log ratio: **0.9995x**. The quiet machine resolved two more rows
than the loaded one (9 inconclusive against 11) and moved two from `faster` into
`ok`, which is the envelope tightening as expected.

**No source failure and no performance regression.** The nine inconclusive rows:

| row | interval |
|---|---|
| abnf-meta/lexic-lex | 0.9803..0.9964 |
| abnf-meta/lexic-mt-lex-ns | 0.9773..1.0310 |
| announced/lexic-mt | 0.9825..1.1058 |
| gbnf-meta/lexic-mt | 1.0011..1.0223 |
| json/lexic-pda | 0.9946..1.0215 |
| markdown/lexic-mt-lex-ns | 0.9165..0.9690 |
| nested/lexic-lex-ns | 0.9790..1.0027 |
| vyx/lexic-lex-ns | 0.9827..1.0043 |
| vyx/lexic-pda | 1.0007..1.0178 |

Two of them, `abnf-meta/lexic-lex` and `markdown/lexic-mt-lex-ns`, sit entirely
BELOW 1.0 and are inconclusive only because their intervals are wider than the
control envelope. They are wins the run could not certify, not risks.

`markdown/lexic-pda`, the row that read `slower` once on the loaded machine,
resolved cleanly here and is not in this list.

### 8b — Same-tree execution health, and a real policy finding

```
uv run python -u -m tools.benchmark.measurement.health
```

Exit code **1**, on a finding the old wall-only worker could not have seen.

**AUTO takes every logical CPU and pays for hyperthreads that return nothing.**
This host has 16 logical CPUs over 8 physical cores. On three grammars AUTO is
both slower than a smaller fixed count AND spends far more total CPU:

| grammar | AUTO wall | best fixed | best wall | AUTO cpu/byte | best cpu/byte | AUTO/best cpu |
|---|---:|---:|---:|---:|---:|---:|
| mixedends | 5.83 ms | 8 | 4.82 ms | 1404 ns | 790 ns | **1.78x** |
| vyx | 17.55 ms | 8 | 15.29 ms | 4970 ns | 3273 ns | **1.52x** |
| abnf-meta | 23.55 ms | 16 | 20.19 ms | 6063 ns | 4317 ns | **1.40x** |

The other nine grammars are within one percent of their best fixed count on both
clocks. The pattern in the raw tables is consistent: going from 8 workers to 16
buys no wall time and costs 50 to 80 percent more CPU, because the second half
are hyperthreads sharing an execution unit with the first.

This is a `src` question in the worker-count policy, which reads a logical CPU
count. I measured it and did not touch it. It is not a regression from this
effort — it is a standing property of the policy that the corrected protocol has
made visible for the first time, because the old worker recorded only wall.

**I strengthened the health verdict to catch it.** It previously asked only
whether AUTO beat ONE worker, which every grammar does. Since all six core
counts are measured, the real question is whether AUTO picked well among them,
so it now also fails when AUTO is slower than the best fixed count AND spends
more than 1.2x its CPU. Threading buys latency with CPU and some overhead is the
price of the win; 1.8x for a slower answer is not. Five tests pin it, including
that a small CPU premium for a real latency win still passes and that an honest
decline is not a failure.

### 8c — Gate status at window end

```
tools/run_checks.sh            exit 0
uv run pytest tests/ -q -n 8   5554 passed, 8 skipped, 267.57s
uv run pytest tests/unit/tools/benchmark  46 passed
```

pylint 10.00/10 across `src/ tests/ getting_started/ tools/ ext/`; pyright clean;
ruff and ruff format clean.

### 8d — Public names promoted, and the control-order fix

Promoted from protected, because the tests exercise each module's real testable
surface: `decide`, `agree`, `sample`, `require`, `grow`, `rosters` and
`primary_reading` in `compare`; `row_contract` in `regression`;
`report_payload` in `execution.worker`; `verdict` in `measurement.health`.

`_ratio` now takes `numerator_first`, which says plainly which of the two
processes runs first. The control flips which of its two identical processes is
on top of the ratio, so slot drift averages out instead of accumulating a sign.
The previous spelling ran `control-a` second by default, which read backwards.

### 8e — What remains for someone else

| Item | Evidence | Owner |
|---|---|---|
| AUTO overshoots to logical CPUs | §8b; 1.4x to 1.78x the CPU of a better fixed count on three grammars | **src.** Worker-count policy |
| Nine inconclusive rows | §8a; two are uncertified wins | **none.** Rerun on a quieter host, or accept |

Nothing committed. My changes to `tools/benchmark`, the workflow, the hook config
and the four benchmark test files are staged; Terra's `src` work is untouched
and unstaged.

### 8f — Health rerun after the physical-core AUTO policy (2026-09-04)

Second window, health only. Terra changed `src/lexic/parsing/parallel/policy.py`
so AUTO derives from physical cores via the OS topology. Confirmed on this host
before running: `os.cpu_count()` is 16, `available_workers()` and
`doc_workers(0)` both report 8.

```
uv run python -u -m tools.benchmark.measurement.health
```

Exit code **1**, on three grammars, and the reason is not the one §8b found.

**The change fixed what it was for.** AUTO no longer takes 16 workers. Its CPU
per byte is now near the 8-worker level on every grammar and far below the
16-worker level: on `announced` AUTO reads 414 ns/byte against 593 at cores=16,
on `markdown` 1318 against 4665, on `abnf-meta` 2718 against 4365. The
hyperthread overshoot of §8b is gone.

**But AUTO is not the same as asking for its own answer.** AUTO resolves to 8,
yet a parse requested with `cores=0` is consistently slower than the identical
parse requested with `cores=8`:

| grammar | AUTO wall ms | AUTO cpu ns/byte | best fixed | best wall ms | best cpu ns/byte | AUTO/best cpu | cores=16 cpu ns/byte |
|---|---:|---:|---:|---:|---:|---:|---:|
| abnf-meta | 16.65 | 2718 | 8 | 16.25 | 2889 | 0.94x | 4365 |
| announced | 4.58 | 414 | 8 | 2.33 | 328 | **1.26x** | 593 |
| arithmetic | 21.55 | 3463 | 8 | 18.53 | 3279 | 1.06x | 5853 |
| backtrack | 4.40 | 495 | 16 | 2.29 | 675 | 0.73x | 675 |
| csv | 6.66 | 1020 | 8 | 5.36 | 914 | 1.12x | 1684 |
| gbnf-meta | 20.85 | 3116 | 8 | 19.08 | 3049 | 1.02x | 4917 |
| json | 10.21 | 1799 | 16 | 9.70 | 3093 | 0.58x | 3093 |
| lexruns | 3.44 | 365 | 8 | 1.68 | 270 | **1.35x** | 467 |
| markdown | 7.60 | 1318 | 8 | 6.34 | 1256 | 1.05x | 4665 |
| mixedends | 6.44 | 927 | 8 | 4.46 | 752 | **1.23x** | 1424 |
| nested | 15.73 | 2116 | 8 | 15.19 | 2114 | 1.00x | 3423 |
| vyx | 15.44 | 3237 | 16 | 12.74 | 5193 | 0.62x | 5193 |

The three failures are `announced`, `lexruns` and `mixedends` — the three
fastest grammars, where AUTO is roughly twice the wall time of cores=8.

**I checked that this is not my harness before reporting it.** AUTO is always
measured last in the core-count sequence, so an ordering artefact was the first
suspect. I ran `announced` outside the health harness, alternating explicit 8
against AUTO three times:

| pair | cores=8 wall | AUTO wall | cores=8 cpu | AUTO cpu |
|---|---:|---:|---:|---:|
| 1 | 2.771 ms | 3.575 ms | 15.721 ms | 15.863 ms |
| 2 | 3.142 ms | 4.701 ms | 16.102 ms | 18.332 ms |
| 3 | 2.311 ms | 4.415 ms | 14.146 ms | 17.778 ms |

AUTO is slower in all three alternating pairs, so the gap survives order. It is
a real difference between the two request paths, not a position effect.

**What that means, stated only as far as the evidence goes.** Requesting `cores=0`
does not produce the same parse as requesting the worker count that `cores=0`
resolves to. The resolved count is used for the pool lease and the window scan,
but the raw request is what reaches the cut planning, so the two paths can chunk
the document differently. I did not read further into `src` and I changed
nothing; that is the next owner's call.

One reporting weakness of mine, for completeness: the observation's
`effective_cores` echoes the REQUEST, so it reads 0 for an AUTO row rather than
the resolved 8. The contract documents that field as the requested count, so it
is behaving as specified, but a resolved count would have made this finding
visible sooner.
