# CLAUDE.md — Lexic

Lexic is the grammar engine layer of Vyx (an agent-to-agent protocol). It
compiles grammar files (GBNF, ABNF, EBNF) into model classes synthesized at
runtime on the `IrNamedTuple` record spine; instances parse text and round-trip
back to grammar.

**Grammar is the ground truth — classes are its Python representation, not the
other way around.** Almost every design question resolves by asking which
direction that arrow points.

## Where the knowledge lives

**[.wiki/index.md](.wiki/index.md)** is the knowledge base. Each page opens with
a *"When to load"* line — read the one that matches your task rather than
loading everything:

| Page | Load when |
|---|---|
| `architecture.md` | checking import legality, adding a module, pipeline flow |
| `ir-shapes.md` | working with IR nodes, action bodies, `kind` semantics |
| `public-api.md` | choosing an entry point, `CompiledGrammar`/`GrammarModel` surface |
| `decisions.md` | asking *why* something is shaped this way — read before reversing one |
| `flavour-system.md` | adding or extending a flavour |
| `field-naming.md` | `bind_fields`, field-name collisions |
| `error-vocabulary.md` | choosing which exception to raise |
| `generated-modules.md` | twin modules, `export_module`, the notation half |
| `invariants.md` / `testing.md` | safety of a change; test placement |

**Update the wiki whenever you add knowledge that would otherwise need
re-deriving from code** — new API surfaces, design decisions, invariants. Add a
`log.md` entry for every significant wiki change.

Code standards are **[docs/STYLE.md](docs/STYLE.md)**. Read it before editing;
it applies to every change.

Active work plans live at `zzz_current_work/<yymmdd>-<name>/`, one directory
per effort, each carrying its own spec, checklist and progress ledger (file
names vary by effort). Check the newest when orienting. `zzz_current_work/` is
gitignored — never cite it from committed docs.

## Commands

Always prefix with `uv run`. Never run `pytest` or `ruff` bare.

```bash
uv run pytest tests/ -q                  # full suite
uv run pytest tests/ -q -n auto          # ... in parallel (~3x); same result, xdist is a dev dep
tools/guarded.sh 8G 600 -- uv run pytest tests/ -q   # memory-capped (use for property tests)
tools/auto_fix.sh                        # ruff format + isort + ruff --fix — run before hand-fixing lint
tools/run_checks.sh                      # THE done-gate; work is done when this exits 0
tools/run_examples.sh                    # every getting_started/ex*.py must exit 0
uv run python tools/check_generated.py   # generated-twin tool-clean gate
```

`guarded.sh <mem> <timeout_s> -- <cmd>` runs under a hard `MemoryMax` so a
runaway allocation is OOM-killed (exit 137) instead of taking the host down. The
property suite drives hypothesis, whose harness retains memory proportional to
examples explored — run it, and any raised-`max_examples` exploration, through
`guarded.sh`. Never raise a committed test's `max_examples`.

## Layering — arrows go one way

Violating this is review-blocking, and
`tests/integration/test_layering_invariants.py` enforces it by static grep.

```
lexic.ir        ← lexic.grammars, lexic.parsing, lexic.compile, lexic (runtime)
lexic.parsing   ✗ lexic.grammars, lexic.compile      (the engine is a leaf w.r.t. both)
lexic (runtime) ↗ lexic.compile, lexic.parsing       (runtime never imports the engine directly)
```

Two deliberate exceptions, both explicit and eager:

1. `model.py` imports `get_flavour` from `lexic.grammars` to drive `to_grammar()`.
2. The `lexic.compile` package is the single runtime seam onto the engine. Only
   `compile/__init__.py` is importable from outside the package.

No `TYPE_CHECKING` dodges, no lazy intra-function imports of `lexic.parsing`
from runtime modules. If a runtime module needs something in the engine, move
the thing.

## The IR spine — the one thing to internalise

**A node IS its payload.** `IrStr` subclasses `str`; `IrTuple`/`IrSeq` subclass
`tuple`; `IrNamedTuple` records ARE their field tuple, read by name or by index.
There are no `.value` / `.items` / `.arms` accessors. So `leaf == "x"` works,
`seq[0]` works, and a reduced document is read with plain Python.

**Absence is `IrNone`**, the singleton value of `IrNoneType(IrSelf)` — never
Python `None`. It fits every dispatch slot, which is what keeps signatures
union-free. Compare `x is IrNone`.

**Consumers dispatch on open `IrDispatch`/`IrTypeMap` tables with a raising
`UnsupportedConstructError` default** — never a closed `isinstance` ladder,
never a silent fallback. A new atom type must not require editing a cascade.

Detail — the three tiers, the action algebra, `IrBottomUp`, `_bound` derivation
— is in `ir-shapes.md`.

## Package map

Orientation only; module docstrings carry the detail.

| Package | What it owns |
|---|---|
| `ir/` | the IR spine, action algebra, dispatch, layout, encodings, canonicalisation. **The strict tier** |
| `parsing/` | the native Earley engine + predictive PDA. A leaf: imports only `lexic.ir` |
| `compile/` | grammar → classes; the sole runtime seam onto the engine; notation, twin modules, templating |
| `grammars/` | GBNF / ABNF / EBNF flavours + the JSON grammar, each carrying its own grammar, reducer and emit actions |
| `model.py` | `GrammarModel` on `IrNamedTuple` — models ARE `IrSelf` |

Two conventions worth knowing before you go looking:

- A flavour is **data, not methods**: `IrFlavour` is an `IrEmitter` carrying its
  own self-grammar and reducer as ClassVars. It defines zero parsing methods.
- `parsing/` and `compile/` hot paths **deliberately** use plain `None`, bare
  tuple aliases and mutable cursors. Strictness is `ir/`'s contract, not
  theirs — don't "clean up" the engine into records.

## Project layout

Exhaustive and drift-checked — `tests/integration/test_doc_drift.py` asserts
both directions (CLAUDE.md once described a deleted shape for a month before
anyone noticed). Annotations are one line; module docstrings carry the detail.

```
src/lexic/
  __init__.py                      Lexic — Grammar engine
  exceptions.py                    LexicError hierarchy — UnsupportedConstructError, FieldValidationError
  generate.py                      random string generator — walks a canonical grammar's rules directly
  model.py                         GrammarModel on IrNamedTuple — models ARE IrSelf; to_text/to_grammar/dump
  api/
    __init__.py                    Readers for third-party formats — applications of lexic, shipped with it
    json_tokenizer.py              tokenizer.json → IrTokenizer; the json formulation is a parameter
    pretokens.py                   that format's own split specs — vendor vocabulary, declared out of ir/
  compile/
    __init__.py                    parse_grammar / canonical_grammar / compile_text — grammar entry points
    artifact.py                    CompiledGrammar — the parse-ready artefact compile_* produces
    foldkit.py                     Shared authored-fold vocabulary — the build-path unification seed
    templating.py                  Generic templating — extract selected paths of any COMPILED grammar via spans
    module/
      __init__.py                  The twin-module surface — export (emit half) + selfgrammar (parse-back half)
      export.py                    export_source / export_module — the importable .py twin
      selfgrammar.py               The generated-module self-grammar — lexic parses its own exports
    notation/
      __init__.py                  The IR-constructor notation surface — parse + emit halves, manifest loader
      emit.py                      The IR-constructor notation's emit half — IR → formatted notation text
      loader.py                    Flavour manifests — one notation expression → a live `IrFlavour`
      parse.py                     The IR-constructor notation — text → real lexic.ir objects
    pipeline/
      __init__.py                  The compile pipeline — grammar → classes (passes, binding, synthesis)
      binding.py                   Binding view — the codegen grammar's per-rule class/kind/parent/field map
      passes.py                    Grammar→grammar codegen passes — hoist groups, hoist arms, relax noise
      synthesis.py                 Runtime class synthesis — codegen grammar + binding view → model classes
  grammars/
    __init__.py                    Grammar-flavour layer — public endpoint
    abnf.py                        ABNF flavour — RFC 5234+7405 surface, core-rules prelude
    ebnf.py                        EBNF flavour — ISO-family surface; refuses negation declaratively
    gbnf.py                        GBNF flavour — incl. the token terminals <t>/<[id]>/!<…>/.
    json.py                        JSON grammar as native IR — the canonical, flavour-neutral representation
  ir/
    __init__.py                    Public IR surface — import everything from here
    action.py                      Action-algebra IrNodes — primitive-node model
    base.py                        IR spine — the abstract base classes shared by every IR node
    bind.py                        IrBind — the field-binding marker generated model fields carry
    canonical.py                   canonicalize — the language-preserving normal form for a grammar IrAst
    concretize.py                  concretize — resolve an `IrAlphabet`'s spelling to an id
    encoding.py                    Encoding family — the codec that gives a char class's ordinals meaning
    escapes.py                     EscapeCodec — the flavour's emit-side spelling of canonical text, on the spine
    flavour.py                     IrFlavour ABC — config bundle every grammar flavour subclasses
    layout.py                      Layout algebra — width-aware document combinators on the record spine
    mapping.py                     Fast map family — a common IrMapping ancestor owning all shared logic
    meta.py                        IrMeta (dataclass-transform + _bound derivation); Singleton metaclasses
    nodes.py                       concrete grammar-AST nodes on the base.py spine (IrAlphabet lives here)
    operators.py                   Operator-algebra nodes — the operator family, sitting between spine and nodes
    order.py                       RuleOrder — deterministic start-first ordering of grammar rules
    walk.py                        Action-driven IR dispatcher on the IrSelf substrate
  parsing/
    __init__.py                    public API: parse_reduced/parse_model products + the Earley toolkit
    fold.py                        ParseTree → object fold — the instance-parsing bridge
    products.py                    The two product entries — reduce (text → the reducer's value), model (text → model)
    earley/
      __init__.py                  The Earley engine (SPPF, Scott 2008) over IrAst-shaped grammars
      chart.py                     The IR-native SPPF link table — the decoded form of a kernel parse
      engine.py                    Earley orchestration — the IR-native façade over the compiled kernel
      forest.py                    Parse forest — the shared packed parse forest (SPPF) and its reducible views
      kernel.py                    The flat Earley kernel — the compiled grammar's paid loop
      lexruns.py                   Run-terminal detection — where a grammar's lexical layer is *derived*
      normalize.py                 Desugar an IR grammar into classical Earley shape
      reduce.py                    Forest → IR reduction — the seam where a flavour's meaning attaches
      resume.py                    The resumable recognizer — mark / extend / rollback on one growing chart
      tables.py                    Compiled grammar tables — the parser's "codegen moment"
      tokenscan.py                 The token-scanning kernel — Earley over a token-segmented input
      trampoline.py                Depth-safe trampoline for the forest/reduce tree walks
    pda/
      __init__.py                  The predictive PDA runtime — analysis, clone compiler, flattener, kernel
      analysis/
        __init__.py                The PDA analysis — decide every decision point, then store the gate specs
        analysis.py                Grammar analysis + decision taxonomy — the PDA compiler's oracle
        cursors.py                 Analysis context cursors — the small data records that ride the nc channel
        kwindow.py                 FIRST_k over CharSet tuples — the k-window (bounded-lookahead) analysis
        leftrec.py                 Left-recursion detection — the predictive-descent impossibility check
        noise.py                   Noise/semantic attribution — the P6 licence + P3 noise-skip substrate
        structured.py              P3-structured / P5-probe — folding-aware loop gates
        taxonomy.py                Taxonomy — the analysis' classified-notes + gate-spec result record
      compiler/
        __init__.py                The PDA clone compiler — an IrAst into flat int-coded tables
        clones.py                  Clone compiler — the predictive-parser artifact beside `ParserTables`
        delegate_compile.py        Island-interior delegate compile — the per-island clone selector
        flatten.py                 Flat int-coded runtime program + post-flatten optimizer passes
        reduce_pda.py              Reduce (grammar-text) completion — the b1 twin of the model fold
        specs.py                   Clone-compiler intermediate specs — the NamedTuple vocabulary tests pin
      core/
        __init__.py                Shared PDA leaves — CharSet, the ScanGate scanner, PdaFail
        charsets.py                CharSet — polarity-aware co-finite character sets
        errors.py                  PdaFail — the predictive-parse failure signal, shared across the PDA
        scanner.py                 Structured-noise recognizer — the folding-aware P3/P5 scanner substrate
      runtime/
        __init__.py                The fused predictive runtime — execute the compiled tables
        build.py                   Frame vocabulary + the fused model-build tail (PDA runtime leaf)
        islands.py                 Island sub-parse + splice — the cold-path Earley escape for a PDA clone
        reduce_runtime.py          Reduce (grammar-text) predictive runtime — the b1 twin of `PdaKernel`
        runtime.py                 Fused predictive runtime — parses text to a model, no ParseTree on the path
tests/
  unit/lexic/           structural mirror of src/lexic/
  integration/          cross-module: layering, parity, round-trip, doc drift
  property/             hypothesis round-trip + reduce differentials
  paths.py              GROUND_TRUTH / GENERATED / tokenizer-fixture paths
ext/API/                NOT shipped — clients that FETCH third-party artefacts
  cache.py              where fetched artefacts live locally; imports only pathlib
  hf.py                 the Hugging Face hub: download into that cache
resources/ground_truth/ .gbnf + .abnf + .ebnf corpus used as fixtures
generated/              git-ignored; importable twin modules (export_module output)
```

`ext/` and `src/lexic/api/` split one job in two: `ext/` **gets** a
third-party artefact (network, credentials, caching — no business in a
grammar engine's wheel), `lexic.api` **reads** one, and `lexic.ir` models it
without knowing either. A format that merely happens to be hosted somewhere
does not belong to that host.

## Directives

Scanned from source comments *before* the grammar is parsed, by the private
`compile._scan_directives`:

```
# @start my_rule          — override the start rule (default: first defined)
# @non-semantic ws sp     — mark rules structural; their refs get min=0
```

A directive naming an undefined rule is silently ignored.

## Key invariants

- **Grammar is canonical.** Every class has a lossless `to_grammar(flavour)`.
- **Round-trip fidelity.** `parse(text).to_text() == text` on every valid input.
- **One way per task.** One parse function, one emit method, one round-trip
  method. No alternate APIs, and no sugar channel beside a real one.
- **No regression.** The suite stays green.

## Hard constraints

- **Never commit or push** unless the active plan records an explicit,
  still-current user grant for that effort.
- **No `# type: ignore`, `# noqa`, or `# pylint: disable`** without explicit
  permission. Fix the root cause.
- **`pyproject.toml` is harness** — never touch it, even under a broad grant.
  Fix the code or ask.
- **No `exec` or `eval`.** No external model/validation library — the
  `IrNamedTuple` spine IS the model layer.
- **No grammar-specific hardcoding in generic code**, and no privileged
  formulation: every mechanism works over ANY formulation of a language through
  the standard pipeline.
- **Never create git worktrees.**
- Tokenizer fixtures are fetched (`uv run python -m ext.API.hf`), never committed
  — they are LGPL. Tests skip when absent.
- Commits carry no `Co-Authored-By`; they are entirely the user's.

## Imports

```python
from lexic.compile import compile_text, compile_from_path, parse_grammar
from lexic.grammars import get_flavour, GBNF_FLAVOUR, ABNF_FLAVOUR
from lexic.ir.nodes import IrItem, IrAst, IrRule, IrLiteral, IrCharClass, IrRuleRef
from lexic.model import GrammarModel
```

Never `from src.lexic...` — `pyproject.toml` sets `pythonpath = ["src"]`.

## Session-usage watch (agent-heavy sessions)

When coordinating subagents, run `tools/usage_watch.sh <threshold> <poll-s>
<duration-s>` as a background task (e.g. `90 60 540`) and relaunch on every
wake. It polls the five-hour session utilization and exits `ALERT <pct>` at the
threshold. At **90%**: tell every in-flight agent to stop and report; write
partial state and a ledger line to the active plan. At **95%**: force it, plus a
"NEXT SESSION — start here" block above the plan's ledger.

Agents are told to **hold** (idle, state preserved), not exit. Then launch
`tools/usage_resume.sh` as a background task — it sleeps until the window
resets, confirms utilization dropped, and exits `RESUME <pct>`. On resume:
re-arm the watcher and `SendMessage` every held agent to continue.
