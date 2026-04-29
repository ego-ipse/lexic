# IR AST architecture: canonical AST in IR, configuration-driven flavours

**Date:** 2026-04-29
**Status:** Approved (brainstormed)
**Supersedes (in part):** `docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md` — specifically, the IR / classifier / converter design (its principles P3, the `RuleClassifier`/`SequenceConverter` Protocols, and the `GbnfClassifier`/`GbnfConverter` work in original Task 5). The packaging direction (`ir/` / `codegen/` / `parsing/` / `runtime/`), `EscapeCodec`, charclass enumeration, and per-consumer handler-table dispatch from the prior spec all stand and are inherited.
**Implementation plan:** to be written.
**Roadmap entry:** Slice B.5 — supersedes the original Slice B.5 IR layer. Of the original v1 plan, Tasks 1–4 are committed and survive (with retargeting); **Task 5 (GbnfClassifier + GbnfConverter) was not implemented** — only an untracked WIP file exists, which this spec discards. Tasks 6–12 (the `parsing/`/`runtime/` package moves and handler-table dispatch) continue as a separate follow-up slice.

## Background

The 2026-04-25 B.5 spec (call it v1) restructured the codebase into flavour-agnostic packages and pulled generic algorithms — `IRBuilder`, `classify_rule`, `convert_*`, `FlavourEmitter` ABC, `EscapeCodec` ABC, `parse_charclass_chars` — into `lexic/ir/`. **Tasks 1–4 of v1's plan are committed; Task 5 was not implemented** (only an untracked `grammars/gbnf/ast_to_ir.py` WIP file exists, which this spec discards). Tasks 6–12 are also unimplemented and continue as a follow-up slice unchanged in spirit.

A review of v1's Task 5 (the would-be `GbnfClassifier` + `GbnfConverter` work) surfaced an architectural problem the rest of the v1 spec hides: **the AST is owned by each flavour, and the IR sees only post-classification atoms.** The `RuleClassifier[Node]` and `SequenceConverter[Node]` Protocols treat each flavour's AST shape as the substrate; the IR-side algorithms operate over those Protocols. The result:

- "What counts as `value_str` vs `alternation` vs `sequence`" is implemented per-flavour against per-flavour AST classes.
- "When does an inline group become an `InlineRegexAtom` / `InlineAlternationAtom` / helper rule" is implemented per-flavour.
- ws-stripping, group-unwrapping, single-ruleref detection — all per-flavour.

This logic is **not flavour-specific in nature** — it's generic grammar-AST decomposition. But it lives in flavour code because the AST it walks is flavour-shaped. To add ABNF, every line of `GbnfClassifier`/`GbnfConverter` would have to be rewritten against ABNF AST shapes. Any classification disagreement between the two implementations is a transpilation bug.

**The transpilation failure mode is the diagnostic.** GBNF → IrAst → ABNF requires the IR to carry enough structural information to render idiomatic ABNF. With v1's design, by the time data reaches an emitter it is a flat list of atoms; the original group structure, the alternation that got flattened into a `value_str`'s linear literal list, the helper rule that emerged from a `(a|b)+` group — all gone. Structural information was eaten by the flavour-side converter. There is no path for an ABNF emitter to recover what it needs.

The fix: **move the AST into IR.** The IR owns a canonical AST shape; every flavour translates source text directly to that AST. Flavour boundaries shrink to: a meta-grammar string, an escape codec, two tiny token-value parsers, and emitter syntax constants. All structural logic — classification, helper-rule extraction, `RuleSpec` derivation, traversal — is generic and lives in `lexic/ir/`.

This spec preserves v1's packaging direction but rewrites the IR layer around an IR AST.

## Architectural principles

The principles below replace v1's P3 entirely. P1 (canonical IR), P2 (open atom set), P4 (adapter-bound dispatch), P5 (capability declarations), P6 (lookup-at-call-time on `GrammarModel`) carry over from v1 unchanged.

**P3a. Canonical AST in IR.** The IR defines a canonical grammar AST (frozen dataclasses, immutable tuples, `__slots__`). Every flavour produces this AST from its source text. The AST is the lingua franca for transpilation, codegen, runtime parsing, and emit.

**P3b. Configuration-driven flavours.** A flavour module is configuration: a Lark meta-grammar string with canonical-tagged productions, an `EscapeCodec` subclass, a `FlavourEmitter` subclass with syntax constants, and two tiny token-value parsers (`parse_quantifier`, `parse_charclass`). No classifier, no converter, no transformer class, no shape-detection imperative code per flavour.

**P3c. Generic IR machinery.** A single `MetaGrammarParser(flavour)` class consumes any conforming flavour and produces an IR AST. A single `derive_specs(ast, *, non_semantic_rules)` function walks the IR AST and produces the codegen `RuleSpec` view. Both are flavour-agnostic.

**P3d. Sugar dies at the parser boundary.** Flavour-specific syntactic sugar that does not directly map to canonical AST nodes (ABNF case-insensitive `"abc"`, hex escapes, etc.) is normalized away in the parser. The IR AST is uniform; downstream code sees no flavour-specific concepts.

**P3e. Author-declared metadata travels through comments.** Source-level concerns that are properties of a specific grammar instance, not of the formalism (which rules are non-semantic, which rule is the start, etc.), are declared via in-source comment directives (`# @<name> <args>`). The flavour declares its line-comment marker; the IR defines the directive vocabulary.

## IR AST node set

`lexic/ir/nodes.py`. Frozen dataclasses, `__slots__`, immutable tuples for collections.

```python
@dataclass(frozen=True, slots=True)
class Quantifier:
    min: int = 1
    max: int | None = 1            # None = unbounded

# Leaves — pure values, no quantifier
@dataclass(frozen=True, slots=True)
class IrLiteral:
    value: str                     # canonical Python (escapes decoded)

@dataclass(frozen=True, slots=True)
class IrCharClass:
    pattern: str                   # canonical POSIX interior, e.g. "a-z0-9"
    negated: bool = False          # source had `[^…]`

@dataclass(frozen=True, slots=True)
class IrRuleRef:
    name: str

# Wrapper — atom + quantifier
@dataclass(frozen=True, slots=True)
class IrItem:
    atom: IrLiteral | IrCharClass | IrRuleRef | IrGroup
    quantifier: Quantifier = Quantifier()

# Structure
@dataclass(frozen=True, slots=True)
class IrSequence:
    items: tuple[IrItem, ...]

@dataclass(frozen=True, slots=True)
class IrAlternation:
    arms: tuple[IrSequence, ...]   # always ≥ 1 arm; single-arm = bare sequence

@dataclass(frozen=True, slots=True)
class IrGroup:
    body: IrAlternation

@dataclass(frozen=True, slots=True)
class IrRule:
    name: str
    body: IrAlternation            # always wrapped, even for single-arm rules

@dataclass(frozen=True, slots=True)
class IrAst:
    rules: tuple[IrRule, ...]
    start: str                     # name of start rule
```

Design choices:

- **Quantifiers on `IrItem`, not on leaves.** `a+` and `(a|b)+` are uniformly an item with a quantifier; only the atom inside differs. The current `LiteralAtom` (no quantifier) vs `QuantifiedLiteralAtom` (with quantifier) split disappears.
- **`IrGroup.body: IrAlternation`, always.** A bare-sequence group is an alternation-of-one. Uniform shape; no special-case nodes.
- **`IrRule.body: IrAlternation`, always.** Same uniformity at the rule level.
- **`IrCharClass.negated: bool` is structural,** not a `^` smuggled into the pattern string.
- **No `Inline*Atom`, no `InlineRegexAtom`, no `AlternationAtom`.** Those were the codegen view leaking into IR. Under the new design, "literal-only group becomes a regex pattern" and "ruleref-only multi-arm group becomes a Union field" are decisions made by `derive_specs` when it walks the IR AST. The IR AST itself only knows structure.

**One type family.** The IR AST leaves *are* the `RuleSpec` field types — there is no separate `*Atom` family. The existing types in `ir/atoms.py` (`LiteralAtom`, `CharClassAtom`, `RuleRefAtom`) are renamed and moved into `ir/nodes.py` as `IrLiteral`, `IrCharClass`, `IrRuleRef`. Other existing atom types (`QuantifiedLiteralAtom`, `InlineAlternationAtom`, `InlineRegexAtom`, `AlternationAtom`) are deleted outright. Quantifier travels on `IrItem` everywhere — including inside `RuleSpec.items`, which becomes `list[IrItem]`. No information is lost; it just moves to where it semantically belongs.

(Naming note: `RuleRefAtom.rule_name` becomes `IrRuleRef.name`. Mechanical rename; aligns with `IrRule.name` and removes the redundant prefix.)

## Per-flavour module shape

A flavour directory is approximately five small files:

```
grammars/gbnf/
    meta_grammar.py    # Lark grammar string with canonical tags
    escapes.py         # GbnfEscapes(EscapeCodec) — survives from v1
    emitter.py         # GbnfEmitter(FlavourEmitter) — survives from v1; already config-shaped
    flavour.py         # GbnfFlavour(Flavour) — binds everything
    __init__.py        # registers GbnfFlavour
```

### `Flavour` ABC

```python
class Flavour(ABC):
    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]                # Lark grammar with tagged productions
    escapes: ClassVar[EscapeCodec]
    emitter: ClassVar[FlavourEmitter]
    line_comment: ClassVar[str] = ""           # for comment-channel directives

    # Token-value parsers — the only flavour-side imperative code
    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> Quantifier: ...

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:  # (pattern, negated)
        ...

    # Optional sugar-expansion hook; default is identity
    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup:
        return IrLiteral(decoded)
```

### Tag convention in the meta-grammar

The generic `MetaGrammarParser` knows a fixed set of tag names. The flavour's meta-grammar uses these names to label productions. This is the contract.

| Tag             | Lark production produces                         | Generic handler does                                       |
|-----------------|--------------------------------------------------|------------------------------------------------------------|
| `ir_rule`       | `(name_token, body_node)`                        | `IrRule(name, body)`                                       |
| `ir_alternation`| list of arm nodes                                | `IrAlternation(tuple(arms))`                               |
| `ir_sequence`   | list of item nodes                               | `IrSequence(tuple(items))`                                 |
| `ir_item`       | `(atom_node, quantifier_token \| None)`          | `IrItem(atom, flavour.parse_quantifier(qt) or default)`    |
| `ir_literal`    | quoted-string token                              | `flavour.normalize_literal(escapes.decode(strip_quotes(text)))` |
| `ir_charclass`  | bracket-expression token                         | `IrCharClass(*flavour.parse_charclass(text))`              |
| `ir_ruleref`    | name token                                       | `IrRuleRef(text)`                                          |
| `ir_group`      | alternation node                                 | `IrGroup(body)`                                            |

### GBNF meta-grammar (illustrative)

```
META_GRAMMAR = r"""
start: rule+
rule: NAME "::=" alternation     -> ir_rule
alternation: sequence ("|" sequence)*  -> ir_alternation
sequence: item*                  -> ir_sequence
item: atom QUANTIFIER?           -> ir_item
atom: LITERAL                    -> ir_literal
    | CHARCLASS                  -> ir_charclass
    | NAME                       -> ir_ruleref
    | "(" alternation ")"        -> ir_group

NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
LITERAL: /"([^"\\]|\\.)*"/
CHARCLASS: /\[(?:\^)?(?:[^\]\\]|\\.)*\]/
QUANTIFIER: /[?*+]|\{[0-9]+(?:,[0-9]*)?\}/

%ignore /[ \t\n\r]+/
%ignore /#[^\n]*/
"""
```

That is the whole GBNF parser. The current `_GBNFTransformer` class disappears; its responsibilities reduce to two staticmethods on `GbnfFlavour` (`parse_quantifier`, `parse_charclass`).

## IR-side machinery

### `MetaGrammarParser(flavour) → IrAst`

`lexic/parsing/meta_parser.py`. Generic. Stateless.

```python
class MetaGrammarParser:
    def __init__(self, flavour: type[Flavour]) -> None:
        self._flavour = flavour
        self._lark = Lark(flavour.meta_grammar, parser="earley", ambiguity="resolve")
        self._transformer = _IrTagTransformer(flavour)

    def parse(self, text: str) -> IrAst:
        return self._transformer.transform(self._lark.parse(text))
```

The transformer (`_IrTagTransformer`) implements the eight tag methods from the table above. Token-value handling delegates to `flavour.escapes.decode` (literals), `flavour.parse_charclass` (bracket interior), `flavour.parse_quantifier` (quantifier text), and `flavour.normalize_literal` (sugar expansion). That is the full extent of flavour involvement at parse time.

### `derive_specs(ast, *, non_semantic_rules) → list[RuleSpec]`

`lexic/ir/derive.py`. Pure function. **No flavour parameter** — `RuleSpec` derivation is structural.

```python
def derive_specs(
    ast: IrAst,
    *,
    non_semantic_rules: frozenset[str] = frozenset(),
) -> list[RuleSpec]: ...
```

For each `IrRule`:

1. **Classify body kind.** Three cases over IR AST:
   - `value_str` ↔ no `IrRuleRef` anywhere in `rule.body` (entire subtree)
   - `alternation` ↔ multiple non-empty arms with rulerefs
   - `sequence` ↔ single non-empty arm with rulerefs
2. **Helper-rule hoisting.** Walk groups in the body. Groups with quantifiers and either multi-arm bodies or ruleref content are hoisted into synthetic rules; the group is replaced with an `IrRuleRef` to the hoisted rule. Pure literal-only groups stay inline as regex pattern candidates.
3. **Compute parent class.** A rule referenced as a single-arm of an alternation gets that alternation's class as its parent (existing convention; `term ::= num | ident` makes `Num` and `Ident` subclasses of `Term`).
4. **Build the spec.** Flatten the (post-hoist) body into `RuleSpec.items: list[IrItem]`. `kind`, `class_name`, `parent_class_name` are set; `field_map` is computed by `assign_field_names` (existing module).
5. **Mark non-semantic.** For each `IrItem` whose atom is `IrRuleRef(name in non_semantic_rules)`, force `quantifier.min = 0`; record the derived field name in `RuleSpec.non_semantic_fields`.
6. **Topo sort.** Existing `topo.py` survives.

The classification is dramatically smaller than the current `GbnfClassifier._classify` because the IR AST already canonicalized the structural messiness (no group-unwrapping, no ws-stripping, no nested-group special cases). The `_is_structurally_complex` predicate disappears.

### `lexic/ir/walk.py` — Python-`ast`-style traversal

Borrowed pattern from Python's `ast` module:

```python
class IrVisitor:
    def visit(self, node): ...           # dispatches to visit_<NodeType>
    def generic_visit(self, node): ...   # walks all child IR nodes

class IrTransformer(IrVisitor):
    """Returns a (possibly new) node from each visit, enabling tree rewrites."""
```

Used by `derive_specs` (helper-rule hoisting is a tree rewrite), by future transpilation passes, and for debugging (`ir.dump(ast)`-style helpers can sit alongside).

### End-to-end flow

```
text ──► MetaGrammarParser(flavour) ──► IrAst ──► derive_specs() ──► list[RuleSpec] ──► ModelEmitter ──► Pydantic classes
                                          │
                                          └──────────────► FlavourEmitter ──► text   (transpilation: pick any flavour)
```

`FlavourEmitter` (existing, slimmed in v1) consumes either `IrAst` directly or `list[RuleSpec]`. The `IrAst` path serves transpilation; the `RuleSpec` path serves "render the codegen view back as text" for debugging and round-trip tests. Implementation may converge on `IrAst` as the canonical input, with the `RuleSpec` view re-projected through it.

## Non-semantic rules and directives

GBNF's actual lexical trivia is comments and inter-token whitespace at the meta-grammar level — already handled by the meta-grammar's `%ignore` rules. The notion of "rules whose content shouldn't appear in `semantic_dump()`" is **not** a flavour-level concept. It is a property of a *specific grammar source* declared by the *author*. A `.gbnf` file using `ws` for whitespace and one renaming that to `foo` are the same flavour but have different non-semantic rule sets.

### Comment-channel directives

The author rides on the formalism's own trivia channel. Comments are the directive vehicle.

```python
# lexic/ir/directives.py

@dataclass(frozen=True, slots=True)
class Directives:
    non_semantic: frozenset[str] = frozenset()
    # future: start, imports, …

def parse_directives(text: str, line_comment: str) -> Directives:
    """Extract IR-level directives from source comments.
    Convention: `<line_comment> @<name> <args...>` lines.
    """
```

**Example: `json_ws.gbnf`**

```
# @non-semantic ws
root ::= ws value
value ::= "null" | "true" | "false" | number
ws ::= [ \t\n]*
```

The Lark meta-grammar still `%ignore`s the comment line. Directives don't reach the AST; they're extracted by a separate scan over the raw source text before parsing.

### Compile entry point

```python
def compile_grammar(
    text: str,
    flavour: type[Flavour],
    *,
    non_semantic_rules: frozenset[str] | None = None,   # explicit override
) -> list[RuleSpec]:
    if non_semantic_rules is None:
        non_semantic_rules = parse_directives(text, flavour.line_comment).non_semantic
    ast = MetaGrammarParser(flavour).parse(text)
    return derive_specs(ast, non_semantic_rules=non_semantic_rules)
```

Net result: the string `"ws"` does not appear anywhere in `lexic.ir` or `lexic.grammars.gbnf`. It only appears in grammar source files (`json_ws.gbnf`, etc.) and in tests that explicitly override.

## Migration phasing

Tasks 1–4 of v1's plan are committed in lexic. The phasing below respects committed work, keeps both pipelines green during cutover, and isolates the architectural change from the packaging continuation.

### What survives intact

| Module | Purpose |
|---|---|
| `ir/escapes.py` | `EscapeCodec` ABC + `CANONICAL_ESCAPES` |
| `ir/charclass.py` | `parse_charclass_chars(inner, codec)` — used at runtime |
| `ir/helpers.py` | `HelperRuleRegistry` — used by `derive_specs` |
| `ir/naming.py` | `assign_field_names`, `to_pascal` |
| `ir/topo.py` | `topo_sort` — final step of `derive_specs` |
| `ir/regex_portable.py` | Cross-flavour regex helpers |
| `ir/spec.py` | `RuleSpec` definition (minor field-type changes) |
| `ir/emit.py` | `FlavourEmitter` ABC (already config-driven) |
| `grammars/gbnf/escapes.py` (or folded in `adapter.py`) | `GbnfEscapes` |
| `grammars/gbnf/emitter.py` | `GbnfEmitter(FlavourEmitter)` — already config-shaped |

### What gets retargeted

| File | Change |
|---|---|
| `ir/protocols.py` | Drop `RuleClassifier`, `SequenceConverter`, `FlavourAdapter`. Keep handler type aliases. Add `Flavour` ABC (or move to `grammars/flavour.py`) |
| `ir/spec.py:RuleSpec` | `items: list[IrItem]`. `non_semantic_fields: frozenset[str]` stays |
| `grammars/gbnf/parser.py` | Thin module: instantiates `MetaGrammarParser(GbnfFlavour)`, exposes `parse(text) → IrAst` |

### What gets deleted

- `ir/atoms.py` — leaf types rename and move into `ir/nodes.py` (`LiteralAtom`→`IrLiteral`, `CharClassAtom`→`IrCharClass`, `RuleRefAtom`→`IrRuleRef`, slimmed of `min`/`max`); `QuantifiedLiteralAtom`/`InlineAlternationAtom`/`InlineRegexAtom`/`AlternationAtom` removed entirely.
- `ir/builder.py`, `ir/classify.py`, `ir/convert.py` — replaced by `ir/derive.py`.
- `grammars/gbnf/ast.py` — flavour AST gone; IR AST is canonical.
- `grammars/gbnf/ast_to_ir.py` — untracked WIP from v1's would-be Task 5; replaced by tag-based generic transformer.
- `codegen/ir_builder.py`, `codegen/classify.py`, `codegen/seq_to_atoms.py`, `codegen/ast_utils.py` — already slated for removal in v1.

### What gets added

`ir/nodes.py`, `ir/walk.py`, `ir/derive.py`, `ir/directives.py`, `grammars/flavour.py` (or folded into `ir/protocols.py`), `parsing/meta_parser.py`, `grammars/gbnf/meta_grammar.py`, `grammars/gbnf/flavour.py`. Plus the stub flavour package (Section: "Stub second flavour").

### Phases

Each phase ends with a green test suite. Old and new pipelines coexist until cutover.

**Phase A — IR-side foundations.** Add `ir/nodes.py`, `ir/walk.py`, `ir/derive.py`, `ir/directives.py`, the `Flavour` ABC, and `parsing/meta_parser.py`. Tested against fake/stub flavours. The existing GBNF pipeline (still routed through `codegen/ir_builder.py` since v1's Task 5 was never implemented) keeps running unchanged; tests stay green.

**Phase B — GBNF flavour migration.** Add `grammars/gbnf/meta_grammar.py` and `grammars/gbnf/flavour.py`. Wire a new `compile_grammar(text, GbnfFlavour)` entry point through `MetaGrammarParser` + `derive_specs`. Validate against `resources/ground_truth/*.gbnf` fixtures: GBNF → `IrAst` → `RuleSpec` → Pydantic round-trip equivalence with the old pipeline. Both pipelines coexist; tests run against both.

**Phase C — Stub flavour validates the surface.** Add the second flavour module (minimal ABNF subset). Round-trip a small set of cross-flavour fixtures. Goal: prove the IR AST surface is genuinely flavour-agnostic.

**Phase D — Cutover.** Switch the public `compile()` entry to the new pipeline. Delete `ir/builder.py`, `ir/classify.py`, `ir/convert.py`, `ir/atoms.py`, `grammars/gbnf/ast.py`, and the untracked `grammars/gbnf/ast_to_ir.py`. Update `codegen/model_emitter.py`, `codegen/lark_builder.py`, `codegen/transformer/`, `runtime/base.py` to consume the new `RuleSpec` shape (`items: list[IrItem]`, leaves are `IrLiteral`/`IrCharClass`/`IrRuleRef`, quantifier on `IrItem`).

**Phase E — Documentation and supersession housekeeping.** A single task closing the slice. Mirrors B5 v1's Task 12 pattern: walk back through the predecessor docs and update them to reflect what landed.

Files touched:
- `CLAUDE.md` — update the "Project layout" tree and the "Architecture" prose to describe the IR-AST-canonical pipeline (parser → IrAst → derive_specs → RuleSpec → emit). Update import-path examples.
- `prototyping/next/2_ARCHITECTURE.md` — replace the architecture description with the IR-AST-canonical model. Spell out the boundary contract (flavour = config; IR owns AST + derivation).
- `prototyping/next/3_ROADMAP.md` — update the Slice B.5 entry to point at this spec; add a new follow-up Slice (call it B.6 or B.5-continuation) for the unimplemented v1 packaging work.
- `docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md` (the v1 spec) — add a header note: this spec is partially superseded by `2026-04-29-ir-ast-architecture-design.md`. P1/P2/P4/P5/P6 stand; P3 is replaced by P3a–e in the new spec. v1's `RuleClassifier`/`SequenceConverter` Protocols and v1's Task 5 GBNF ast_to_ir work are abandoned. v1's Tasks 6–12 (packaging) carry forward unchanged in spirit and ship as a separate follow-up slice.
- `docs/superpowers/plans/2026-04-25-slice-b5-package-restructure.md` (the v1 plan) — add a banner at the top noting that Tasks 1–4 were implemented, Task 5 is abandoned (this spec replaces it), and Tasks 6–12 will be re-issued as a follow-up slice plan adapted to the IR AST layer.

**The v1 packaging continuation (`parsing/`/`runtime/` package moves, handler-table dispatch — formerly v1 Tasks 6–12) is not in this slice.** It's deferred to a subsequent follow-up slice that operates on the post-Phase-D architecture. The Phase E housekeeping just updates the docs to make that hand-off explicit.

This spec covers Phase A through Phase E as one slice.

## Stub second flavour: minimal ABNF subset

The second flavour stress-tests the IR AST surface. ABNF (RFC 5234) provides the right quirks: prefix quantifiers, hex escapes, case-insensitive literals, semicolon comments. Pick a deliberately narrow subset.

### In scope

| Feature | ABNF syntax | Architectural seam exercised |
|---|---|---|
| Rule separator | `name = body` (single `=`, not `::=`) | `FlavourEmitter` syntax constants |
| Alternation separator | `/` (forward slash, not `\|`) | `FlavourEmitter` syntax constants |
| Quantifiers | `*N body`, `n*m body`, `n body` (prefix, not suffix) | `parse_quantifier` — non-trivial parse |
| Char classes | `%x41-5A` (hex ranges) | `parse_charclass` — different syntax |
| Escape codec | `%x41` for hex; no `\n`/`\t` | `EscapeCodec` subclass |
| Literals | `"abc"` is **case-insensitive** by default | `normalize_literal` hook — sugar expansion to char-class group |
| Comments | `;` line comment | `line_comment` ClassVar + directive parsing |
| Groups | `(...)` | Identical to GBNF — control case |

### Out of scope

`%d` decimal, `%b` binary, numeric-value concatenation (`%d65.66.67`), prose-val (`<text>`), incremental alternatives (`=/`). Those are full-ABNF concerns, not architectural validation.

### Sizing constraint

The stub flavour module weighs in around the same size as `grammars/gbnf/`. If `grammars/abnf/` ends up substantially larger, that is a signal the architecture isn't actually flat enough and the design needs another pass before continuing.

### Validation tests under this stub

1. **Round-trip per flavour.** GBNF text → `IrAst` → emit GBNF → parse → identical `IrAst` (up to canonical normalization). Same for ABNF.
2. **Cross-flavour transpile.** A small grammar — arithmetic — written in both GBNF and ABNF, parsed to `IrAst` from each, asserted structurally equivalent. Then emit in the other flavour and parse back. Validates that the IR AST genuinely is the lingua franca.
3. **Sugar-expansion correctness.** ABNF `"abc"` → `IrAst` expanded to a group of char classes for `[aA][bB][cC]`-style matching; the GBNF emitter renders that group correctly without knowing about case-insensitivity.

## Out of scope

- **Full ABNF support.** Only the subset above. Numeric-value concatenation, prose-val, incremental alternatives, etc., await a future slice if ABNF becomes a real target.
- **GBNF → ABNF transpilation as a public API.** The architecture *enables* it; an actual transpilation entry point (e.g. `transpile(text, src=GbnfFlavour, dst=AbnfFlavour) -> str`) can be added trivially in a follow-up but is not built here.
- **In-source directives beyond `@non-semantic`.** The `Directives` dataclass leaves room for `start`, `imports`, etc.; only `@non-semantic` is parsed in this slice.
- **Codegen via `ast.unparse`.** `model_emitter.py` continues using string templates. Migrating to `ast.Module` + `ast.unparse` is a possible improvement but orthogonal to this spec.
- **v1 packaging continuation.** Phase E (`parsing/`/`runtime/` moves, handler-table dispatch from v1's Tasks 6–12) ships as a separate slice.

## Success criteria

1. `compile_grammar(text, GbnfFlavour)` produces `RuleSpec` lists structurally equivalent (modulo the slimmed atom shape) to the current pipeline for every grammar in `resources/ground_truth/`.
2. `compile_grammar(text, AbnfFlavour)` works for the small ABNF subset fixtures and passes the round-trip test.
3. Cross-flavour transpilation tests pass: a grammar parsed from GBNF and the same grammar parsed from ABNF produce structurally equivalent `IrAst`s; emitting one and re-parsing through the other yields identical `IrAst`.
4. The string `"ws"` does not appear in any file under `lexic/ir/` or `lexic/grammars/gbnf/`.
5. `grammars/gbnf/` contains no classifier, converter, or transformer class. The directory weighs roughly five small files: `meta_grammar.py`, `escapes.py`, `emitter.py`, `flavour.py`, `__init__.py`.
6. `grammars/abnf/` weighs comparably.
7. `lexic/ir/derive.py` is a single file containing the entire structural decomposition algorithm, with no flavour imports.
8. The full test suite passes at every commit during Phase A → E. Tests for the old pipeline can be removed at Phase D cutover.
9. The v1 spec (`2026-04-25-slice-b5-package-restructure-design.md`) and v1 plan have supersession headers added; ROADMAP, ARCHITECTURE, and CLAUDE.md describe the post-Phase-D architecture; the v1 packaging continuation (former Tasks 6–12) appears as a distinct follow-up slice in the roadmap with a clear hand-off note.
