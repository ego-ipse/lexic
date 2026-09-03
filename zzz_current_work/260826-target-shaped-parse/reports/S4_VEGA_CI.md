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
