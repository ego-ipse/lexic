# Slice A — Foundational Refactor — Design Spec

**Date:** 2026-04-21
**Status:** Approved (brainstormed)
**Implementation plan:** `docs/superpowers/plans/2026-04-21-slice-a-foundational-refactor.md`
**Roadmap entry:** `prototyping/next/3_ROADMAP.md` §Slice A

## Background

Slice A is a pure refactor that closes V3 review items §1, §2, §3, §8, §10, §B, §C and the STYLE §1/§2 violations flagged on 669-line `ir_builder.py`, 267-line `_build_instance`, and 274-line `generate.generate`. No public-API changes. No generated-code-shape changes. No IR atom changes.

This spec resolves the four open questions deferred to Slice A's brainstorming session in `3_ROADMAP.md` §Slice A and audits a handful of additional design points surfaced during review of the pre-brainstorming draft plan.

## Open questions — resolutions

The roadmap deferred four questions. Each is resolved below, with rationale.

### Q1. Builder dispatch protocol (BuildContext/FieldResult)

**Resolution:** Immutable context; orchestrator owns the cursor; builders are pure functions over a frozen ctx snapshot.

```python
# src/lexic/codegen/transformer/context.py
@dataclass(frozen=True)
class BuildContext:
    spec: RuleSpec
    children: tuple[Any, ...]
    hints: Mapping[str, type]
    cursor: int = 0

    def peek(self) -> Any | None:
        return self.children[self.cursor] if self.cursor < len(self.children) else None

    def exhausted(self) -> bool:
        return self.cursor >= len(self.children)


@dataclass(frozen=True)
class SkipField:
    """Signal: the field this builder was asked for should not appear in kwargs."""


SKIP_FIELD = SkipField()


@dataclass(frozen=True)
class FieldResult:
    value: Any
    consumed: int


BuildResult = FieldResult | SkipField
```

Builders take `(atom, field_name, ctx) -> BuildResult`. The orchestrator keeps a local `cursor` int, advances it by `result.consumed` between calls, and constructs a fresh `BuildContext(..., cursor=cursor)` for each builder call (via `dataclasses.replace`). No `consume()` method on ctx. No mutation.

**Rationale.** Makes builders trivially unit-testable: frozen input → known output. Eliminates the draft's dual bookkeeping (mutable `ctx.consume()` alongside a returned `consumed` count). The skip variant replaces the draft's `_MISSING` sentinel with a typed, match-dispatchable primitive.

**Rejected alternatives:**
- Pure-function style without a context object. Fails because list/optional builders need `hints` and the full children view to decide dynamically how many children to take.
- Mutable cursor, no return-count. Hides state; harder to test; mutation in an otherwise declarative dispatch is a smell.
- Draft's hybrid (mutable ctx + returned `consumed`). Redundant; builders in the draft's own code never call `consume()`, proving the method is dead weight.

### Q2. Classifier return shape

**Resolution:** Union of per-kind dataclasses. Each variant carries exactly the payload its per-kind `_build_*` method consumes — `_build_rule` unpacks in the `match` arm and hands the payload through. No `_build_*` method re-calls `unwrap_group_alt` or `strip_ws` on `rule.body`; the Classifier has already done it.

```python
# src/lexic/codegen/classify.py
@dataclass(frozen=True)
class ValueStr:
    alt: Alternation           # unwrapped alt; _build_value_str iterates every seq/item

@dataclass(frozen=True)
class PureLiteralAlt:
    alt: Alternation           # unwrapped alt; same shape so match can unify with ValueStr

@dataclass(frozen=True)
class NamedAlt:
    arms: list[Sequence]       # ws-stripped, non-empty; iterated directly by _build_named_alt

@dataclass(frozen=True)
class SequenceKind:
    body: Sequence             # non-stripped first arm; passed through to seq_to_atoms

Classification = ValueStr | PureLiteralAlt | NamedAlt | SequenceKind
```

Payload asymmetry is deliberate: each variant carries what its downstream consumer needs, not a uniform shape. `SequenceKind.body` is **non-stripped** because `seq_to_atoms` preserves `ws` atoms in its output (needed for round-trip `to_text()`); `NamedAlt.arms` is **stripped** because named-alt arm-dispatch (`single_ruleref_of`) and the `seq_to_atoms` call in the non-ruleref arm case both operate on the ws-stripped form in today's code; `ValueStr` / `PureLiteralAlt` carry the full unwrapped `alt` because their consumer (`_build_value_str`) iterates every arm and every item.

`PureLiteralAlt` does **not** carry extracted arm literals (`list[list[str]]`) in Slice A — nothing consumes them. Slice C will add that payload when it emits `Literal[...]`.

`Classifier.classify(rule) -> Classification` does all AST extraction once. `_build_rule` is:

```python
match self._classifier.classify(rule):
    case ValueStr(alt=alt) | PureLiteralAlt(alt=alt):
        return self._build_value_str(rule, alt, cls_name, parent_cls)
    case NamedAlt(arms=arms):
        return self._build_named_alt(rule, arms, cls_name, parent_cls, parent_of)
    case SequenceKind(body=body):
        return self._build_sequence(rule, body, cls_name, parent_cls, parent_of)
    case _:
        assert_never(classification)
```

**Rationale.** Closes the draft's leaky abstraction — the draft's flat `Classification(kind: str)` forced `IRBuilder` to re-traverse the AST via re-exported `_is_single_ruleref`/`_strip_ws`/`_unwrap_group_alt` from `classify.py` with underscored names. The union form makes `Classifier` a complete extractor: once it has classified, the per-kind methods never look at `rule.body` again. Pairs symmetrically with the `BUILDER_BY_ATOM` dispatch in Q1: match-on-union on the classification side, table-lookup-on-type on the builder side.

**Rejected alternatives:**
- Flat `Classification(kind: str)` (draft). Caller re-traverses; leaks predicates back into `ir_builder.py`.
- Flat `Classification` with all optional fields populated (roadmap's implied intent). Equivalent expressive power to the union but with "remember which fields are valid for which kind" cognitive load and no exhaustiveness checking.
- Uniform payload (every variant carries the unwrapped `alt`). Rejected because `_build_named_alt` would then re-derive the stripped arms — same re-traversal problem the union is meant to kill.

### Q3. CompiledGrammar memoization

**Resolution.** Grammar compilation is fundamentally a `text → classes + specs + parser + transformer` pipeline. The canonical input is the string; reading a file is a convenience layer. Both the codegen and compile surfaces reflect this: the unqualified name takes the string, and the path-accepting name is the thin wrapper with a `_from_path` suffix.

- **codegen API** (in `src/lexic/codegen/__init__.py`) — three public symbols:
  - `build_classes_and_specs(text: str, *, stem: str) -> tuple[dict[str, type], list[RuleSpec]]` — full parse + IR-build + emit + load pipeline. Returns both classes and specs. Exists for callers (`compile.py`) that need both; avoids the double parse+build that would result from calling `codegen()` after having built specs independently.
  - `codegen(text: str, *, stem: str) -> dict[str, type]` — classes-only wrapper over `build_classes_and_specs`. Primary public surface for callers who just want the generated Pydantic classes.
  - `codegen_from_path(grammar_path: str | Path) -> dict[str, type]` — 2-line wrapper: `path = Path(grammar_path); return codegen(path.read_text(), stem=path.stem)`.
- **compile API** (in `src/lexic/compile.py`):
  - `compile(text: str, *, cache_key: Hashable | None = None) -> CompiledGrammar` — primary. `cache_key=None` means "do not memoize".
  - `compile_from_path(grammar_path: str | Path) -> CompiledGrammar` — thin wrapper. Builds a `(str(resolved_path), mtime, size)` stat-based key, checks the cache before reading, delegates to `compile` with the key on miss.
- **Memo key.** `(path_str, mtime, size)` — one-line upgrade over the draft's `(path, mtime)`, zero added cost (same `stat()` call). For the primary `compile`, the key is whatever the caller passes (or omitted).
- **CompiledGrammar.specs type.** `dict[str, RuleSpec]` — matches the roadmap signature (the draft had `list`, which is a roadmap deviation).

```python
# src/lexic/compile.py
from lexic.codegen import build_classes_and_specs        # public, single edge
from lexic.codegen.lark_builder import LarkBuilder       # public


@dataclass(frozen=True)
class CompiledGrammar:
    classes: dict[str, type[GrammarModel]]
    specs: dict[str, RuleSpec]
    parser: lark.Lark
    transformer: Transformer

    def parse(self, text: str) -> GrammarModel: ...


_CACHE: dict[Hashable, CompiledGrammar] = {}


def reset_cache_for_tests() -> None:
    """Test seam: clear the compile cache. Public name so tests do not
    reach into a leading-underscore symbol across modules."""
    _CACHE.clear()


def _stem_for_text(text: str) -> str:
    """Stable filename for an anonymous grammar string. Used by compile()
    when it needs to emit a module without a path."""
    return "anon_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _compile_core(text: str, *, stem: str) -> CompiledGrammar:
    classes, specs_list = build_classes_and_specs(text, stem=stem)
    specs = {s.rule_name: s for s in specs_list}
    builder = LarkBuilder(specs_list)
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    transformer = builder.build_transformer(classes)
    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer
    )


def compile(text: str, *, cache_key: Hashable | None = None) -> CompiledGrammar:
    if cache_key is not None and (hit := _CACHE.get(cache_key)):
        return hit
    cg = _compile_core(text, stem=_stem_for_text(text))
    if cache_key is not None:
        _CACHE[cache_key] = cg
    return cg


def compile_from_path(grammar_path: str | Path) -> CompiledGrammar:
    path = Path(grammar_path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size)
    if hit := _CACHE.get(key):
        return hit
    return compile(path.read_text(), cache_key=key)
```

The hash-stem helper lives in `compile.py`, not `codegen/`. `build_classes_and_specs` requires an explicit `stem` from its caller; the "anonymous" naming policy is a `compile.py` concern (it's the module that invents a stem when the grammar came from a string).

`compile.py` imports exactly two public symbols from `lexic.codegen`: `build_classes_and_specs` (for the classes + specs pipeline) and `LarkBuilder` (for the lark parser + transformer). No private-symbol imports across the runtime↔codegen boundary. Today's plan would have had four imports (`codegen`, `IRBuilder`, `LarkBuilder`, `parse_gbnf`) with a double parse+build; `build_classes_and_specs` collapses that into one call and narrows the seam.

**Rationale.** `(path, mtime, size)` closes the draft's most likely real-world failure mode — tests that rewrite a grammar inside a single mtime tick. Adding `size` costs nothing (same `stat()`). Network-FS fragility remains inside the roadmap's documented risk budget.

The primary/wrapper direction (string-taker unqualified, path-taker suffixed) matches the reality of the pipeline: grammar text is the canonical input; file I/O is a convenience layer. It also matches Pydantic's convention (`model_validate_json(str)` is primary; path helpers wrap it) and the general Unix/functional rule that IO lives at the edges.

The `compile` name shadows Python's builtin; this is acceptable (stdlib itself does this in `re.compile`, `codecs.compile` etc.) and matches the roadmap. Callers who dislike the shadowing can `import lexic` and call `lexic.compile(...)`.

`reset_cache_for_tests()` is the public test seam — no cross-module underscore imports.

**Layering note.** `compile.py` is runtime and imports two public symbols from `lexic.codegen` at module scope: `build_classes_and_specs` and `LarkBuilder`. This is explicitly permitted by `2_ARCHITECTURE.md` §Layering rules as the second of two deliberate runtime→codegen seams (alongside `base.py::to_grammar`). Both imports are eager; no lazy intra-function imports; no underscore symbols cross the seam.

The `build_classes_and_specs` entry exists precisely to keep this seam narrow: without it, `compile.py` would need to call `codegen()` for classes and then re-run `parse_gbnf` + `IRBuilder` for specs (four imports, double work). With it, one public call gets both. `codegen()` itself becomes a thin classes-only wrapper — same public behaviour for its existing callers, tighter internal factoring.

### Q4. FieldNamer lifetime

**Resolution:** Not a class. Module-level function.

```python
# src/lexic/codegen/naming.py
def assign_field_names(atoms: list[Atom]) -> dict[str, int]:
    """Per-rule scope. Stateless. Unchanged semantic vs. today."""
```

**Rationale.** The roadmap framed the question as "per-build vs shared across builds". Per-build would be a behavior change (`ws` in rule A and `ws` in rule B would collide into `ws`/`ws2`) and would break the 312-test suite. Shared-across-builds is even more aggressive. Both options imply state; the actual required semantic is per-rule, stateless. The right resolution of the open question is "neither option — it's a function, not a class."

The pre-brainstorming draft implemented a third, worse option: stateless class with instance-per-call (`FieldNamer().assign(atoms)`). Its own docstring acknowledged: "A single instance carries no state between assign() calls."

Slice C will replace the naming policy wholesale with the four-tier cascade. That policy may or may not need state; if it does, it will introduce a class with its own shape (`FieldNamer(pattern_library, sidecar)` or similar). Keeping a pretend-class now does not save migration work — the constructor signature will change either way.

## Additional design points (surfaced during draft audit)

### §A. Skip-field representation — see Q1

Use `SkipField`/`FieldResult` union. Orchestrator matches:
```python
match result:
    case SkipField():
        continue  # do not add fname to kwargs
    case FieldResult(value=v, consumed=n):
        kwargs[fname] = v
        cursor += n
```

### §B. Task 12 relocates from Part E to Part B

`IRBuilder._build_rule` splitting is ir_builder decomposition work, not SOLID-sweep cleanup. It belongs in Part B alongside the Classifier extraction, since the per-kind methods naturally consume the Classification-union variants.

**Roadmap update required:** `prototyping/next/3_ROADMAP.md` §Slice A §Scope must note this task move. The `IRBuilder._build_rule` split is now part of the "Extract `Classifier`" bullet's deliverables.

### §C. CompiledGrammar.specs type — roadmap wins

The draft had `specs: list`. The roadmap has `specs: dict[str, RuleSpec]`. Use the dict form — enables O(1) lookup by rule name, which `generate.py` and future emitters need.

### §D. HelperRuleRegistry API

Draft's API (`reserve`/`register`/`all_specs`) is sound and accepted unchanged. Key properties:
- `reserve(base_name)` is non-mutating — returns a unique name without marking it taken.
- `register(spec)` raises on duplicate registration.
- `all_specs()` returns specs in registration order.

The non-mutating reserve + mutating register split avoids an entire class of ordering bugs where a reserved-but-unused name blocks a subsequent legitimate use.

### §E. Test coverage thin spots

Beyond the draft's coverage, two builders/modules warrant additional tests:

- `RuleRefBuilder` has four behavioral branches: (ws rule vs non-ws rule) × (child available vs not). Each branch needs a test.
- `Classifier` needs tests for edge cases beyond the four kinds: structurally-complex alternations, group-unwrapping, empty-arm case.

### §F. Error class temporary state

Slice A raises bare `ValueError` from `builder_for(atom)` when an atom type has no registered builder. Slice B replaces this with `UnsupportedConstructError` when `lexic.exceptions` lands. Accept the transitional form in Slice A.

## Architecture summary

### Module layout after Slice A

```
src/lexic/
  base.py                               GrammarModel (unchanged)
  parse.py                              parse(text, path) — one-liner over compile()
  compile.py                            compile, compile_from_path, CompiledGrammar
  generate.py                           split into per-kind helpers (Part E)
  ir/                                   unchanged; 7 atoms still (Slice B collapses to 5)
  codegen/
    __init__.py                         build_classes_and_specs, codegen, codegen_from_path
    ast_utils.py                        strip_ws, is_ws_item, unwrap_group_alt,
                                          single_ruleref_of (NEW)
    classify.py                         Classifier + Classification union (NEW)
    naming.py                           assign_field_names (NEW)
    helpers.py                          HelperRuleRegistry (NEW)
    seq_to_atoms.py                     seq_to_atoms + Group→regex/gbnf converters (NEW)
    ir_builder.py                       < 200 LoC orchestrator
    model_emitter.py                    unchanged
    lark_builder.py                     to_lark_name moved out
    gbnf_emitter.py                     unchanged
    parser.py / ast.py                  unchanged (Slice B moves these)
    transformer/                        NEW sub-package (was transformer.py)
      __init__.py                       re-exports build_transformer
      build_transformer.py              orchestrator; dispatches via BUILDER_BY_ATOM
      context.py                        BuildContext, FieldResult, SkipField
      registry.py                       BUILDER_BY_ATOM, builder_for
      builders.py                       FieldBuilder implementations
  utils/
    escapes.py                          unchanged
    quantifiers.py                      + quantifier_to_bounds (inverse function)
    names.py                            to_lark_name, to_pascal, to_snake (NEW)
    charclass.py                        parse_escape, parse_charclass_chars (NEW)
```

### Dispatch table shape (Part C)

```python
BUILDER_BY_ATOM: dict[type[Atom], FieldBuilder] = {
    LiteralAtom:           LiteralSkipBuilder(),
    CharClassAtom:         CharClassFieldBuilder(),
    QuantifiedLiteralAtom: QuantifiedLiteralBuilder(),
    InlineRegexAtom:       InlineRegexBuilder(),
    RuleRefAtom:           RuleRefBuilder(),
    InlineAlternationAtom: InlineAlternationBuilder(),
    AlternationAtom:       AbstractAlternationBuilder(),
}
```

Seven entries matching today's seven atoms. Slice B will collapse three of these into one (`PatternAtom`), reducing the table to five entries — that change is a two-line diff over this dispatch, which is the whole point of the table-driven refactor.

`Optional[X]`/`List[X]` are wrapping builders (`OptionalFieldBuilder(inner)`, `ListFieldBuilder(inner, inner_type=...)`) chosen by the orchestrator based on type hints, not forked branches inside the core loop.

### Classification dispatch (Part B)

```python
def _build_rule(self, rule, parent_of) -> list[RuleSpec]:
    cls_name = self._name_map[rule.name]
    parent_cls = parent_of.get(rule.name, "GrammarModel")
    match self._classifier.classify(rule):
        case ValueStr(alt=alt) | PureLiteralAlt(alt=alt):
            return self._build_value_str(rule, alt, cls_name, parent_cls)
        case NamedAlt(arms=arms):
            return self._build_named_alt(rule, arms, cls_name, parent_cls, parent_of)
        case SequenceKind(body=body):
            return self._build_sequence(rule, body, cls_name, parent_cls, parent_of)
        case _:
            assert_never(classification)
```

Each helper receives exactly the payload it needs, pre-extracted. No helper calls `unwrap_group_alt` or `strip_ws` on `rule.body`; the Classifier owns that work. `rule` itself is still threaded through only because `RuleSpec` requires `rule.name` for `rule_name` — the helpers do not re-traverse `rule.body`.

## Exit criteria (carried from roadmap, unchanged)

- 312+ tests pass; property round-trips on all seven grammars green.
- `ir_builder.py` under 200 LoC.
- Every `FieldBuilder` has its own unit test over a focused IR fixture.
- `parse()` after warm-up under 1ms/call (today: ~20ms/call).
- `transformer/builders.py` contains no `isinstance` cascade over atom types.
- `base.py` has exactly one `lexic.codegen` import (the `GBNFEmitter` import powering `to_gbnf`; Slice B replaces this with the eager `to_grammar` edge).
- No `from codegen.X` imports anywhere; all imports are `from lexic.X`.

## Non-goals (carried from roadmap, unchanged)

- No IR atom changes (Slice B).
- No `flavour=` parameter (Slice B).
- No `@grammar_rule` decorator (Slice D).
- No sidecar (Slice C/D).
- No generated-code shape changes (Slice C).

## References

- Preserved Task 12 content (relocated to Part B): `prototyping/next/draft/slice-b-moved.md`
- Roadmap: `prototyping/next/3_ROADMAP.md` §Slice A
- North star: `prototyping/next/1_NORTH_STAR.md`
- Architecture target: `prototyping/next/2_ARCHITECTURE.md`
