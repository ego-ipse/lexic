# Slice B closure + dispatch unification: intrinsic-on-node, unified flavour emit, LarkFlavour promotion

**Date:** 2026-05-14
**Status:** Approved (brainstormed); revised 2026-05-15 mid-execution — see §Revision 2026-05-15.
**Supersedes (in part):** `docs/superpowers/plans/2026-04-23-slice-b-pattern-atom-tier-2-5-tokens.md` — closes the remaining Slice B Phase 3 deliverable (positional token reservation), folds in cleanup of stragglers (helpers.py, utils/quantifiers.py, FlavourEmitter), and adds a larger architectural cut.
**Implementation plan:** `docs/superpowers/plans/2026-05-14-slice-b-closure-and-dispatch-unification.md`.

## Revision 2026-05-15

Tasks 1.1 and 1.2 landed with deviations from the literal spec code; Tasks 1.3 and 1.4 were rebrainstormed before execution. Three concrete changes from the original §Architecture below:

1. **Richer node hierarchy.** Instead of every concrete IR node subclassing `IrNode` and implementing `children` / `rebuild` independently, the implementation grew an intermediate layer:

   ```
   IrNode (ABC) ─┬─ IrLeaf                     identity defaults (children=(), rebuild=self)
                 └─ IrStructure (ABC) ─┬─ IrCollection[_T]      homogeneous variable-length
                                       └─ IrComposite[*_Ts]    heterogeneous fixed-arity
   ```

   Concrete leaves inherit `IrLeaf`. Concrete branches inherit `IrCollection` (declaring `_items_attr: ClassVar[str]`) or `IrComposite` (declaring `_child_attrs: ClassVar[tuple[str, ...]]`). `children()` and `rebuild()` are auto-implemented on the bases via `getattr` and `dataclasses.replace`. No per-node overrides needed. `IrStructure` declares `__dataclass_fields__: ClassVar[...]` so `dataclasses.replace(self, ...)` typechecks without a cast. The TypeVarTuple variant on `IrComposite` lets `IrItem(IrComposite["IrAtom", "Quantifier"])` carry precise heterogeneous-child types.

2. **`__str__` / `__repr__` replace `emit()` and `dump()`.** The original spec collapsed both concerns onto a single `emit(indent)` method whose default matched the legacy `_DUMP` byte-for-byte. Two failure modes followed: it conflated *canonical rendering* (what an `IrEmitter` action does in the absence of a flavour override) with *debug visualization* (a raw structural dump), and it tied the IR's intrinsic API to a format we want to discard. The revision drops both `emit()` and `dump()` in favour of Python's dunder protocol:

   - **`__str__(self) -> str`** — the node's canonical-form string. This is the intrinsic action: an `IrEmitter.visit` falls back to `str(node)` when its `action.get(type(node))` returns `None`. New IR node types implement `__str__`; flavour overrides intercept via the action table without touching the node. For now the output is a placeholder notation (`LITERAL('a')`, `SEQ(...)`, `ALT(...)`, etc.) — deliberately not any user-facing grammar syntax. The eventual canonical IR-self-notation ("IrFlavour") is designed and slotted in as a Flavour like any other; until then the placeholder exercises the architecture without committing to syntax.
   - **`__repr__(self) -> str`** — debug raw visualization. `IrStructure` defines a generic indented multi-line `__repr__` that walks `children()` recursively. Concrete structural classes use `@dataclass(frozen=True, slots=True, repr=False)` so the dataclass-generated `__repr__` doesn't shadow it. Leaves use the dataclass-default `__repr__`. New IR node types participate automatically through `children()` and dataclass defaults.

   The `dump()` free function in `walk.py` is deleted. Callers use `repr(node)`. The `IrEmitter` fallback uses `str(node)`. No `emit()` method exists.

3. **`IrDispatch` is structural — an `IrCollection["IrAction"]`.** Treating it as a leaf with `children() == ()` was dishonest: a dispatcher's whole point is its action table. So a new leaf type `IrAction(IrLeaf)` wraps each `(target_type, handler)` pair, and `IrDispatch` inherits from `IrCollection["IrAction"]` with `_items_attr = "actions"`. The `children()` of a dispatcher are its actions; `rebuild()` reconstructs from a new action tuple. A `@cached_property _table: dict[type, Callable]` is derived from `actions` for O(1) lookup at dispatch time. TODO marker on `IrAction` documents the C-level destination: when the `handler` callable grows into a structural sub-algebra of typesetting/transformation operations, `IrAction` stops being a leaf — its operations become its children — and `IrDispatch` doesn't need to change. A Flavour then becomes a literal tree of IR nodes expressible *in* IR.

4. **Dispatch logic collapses.** With actions structural, the `visit` / `generic_visit` / `_combine` / `visit_<TypeName>` getattr indirection becomes rote scaffolding. The dispatcher is just `__call__`: walk children first, then either look up the handler in `_table` or fall back to `default`. Two semantic modes:
   - `actions == ()` — no flavour overrides; every node uses `self.default(node, new_children)`. This is the `IrMetaEmitter`-style use case.
   - `actions != ()` — the dispatcher has declared a closed world; a type miss raises `UnsupportedConstructError`. This is the flavour-as-emitter use case.

   `default(self, node, new_children) -> _T` is *not* abstract. The base returns `cast("_T", node)` — the identity pass-through, sensible for `IrTransformer[IrNode]`. `IrEmitter[str]` overrides to return `str(node)` (the node's intrinsic canonical action from `__str__`). `IrVisitor[None]` overrides to return `None`. Two overrides, one inherited default.

5. **`__str__` is a template method; `__repr__` is mechanical.** `IrNode.__str__` is a single template:

   ```
   f"{_str_name}{_str_opener}{_inner_str()}{_str_closer}"
   ```

   Three ClassVars (`_str_name`, `_str_opener`, `_str_closer`) and one abstract method (`_inner_str`) drive everything. `_str_name` is **auto-derived in `__init_subclass__`** from the class name (strip `Ir`, uppercase) — `IrRule` → `"RULE"`, `IrItem` → `"ITEM"`. Subclasses set it explicitly only when the auto-derivation isn't what we want (`IrRuleRef` → `"REF"`, `IrSequence` → `"SEQ"`, `IrAlternation` → `"ALT"`, `Quantifier` → `"Q"`). `_str_opener` / `_str_closer` default to `(` / `)`; `Quantifier` overrides to `[` / `]` (subscript/bounds notation).

   `_inner_str` is the only per-class extension point. `IrLeaf` default: `repr(first_dataclass_field)` — single-field leaves get it free. `IrStructure` default: `", ".join(_extra_str_parts() + [str(c) for c in children()])`. Extras come from each branch base's `_extra_field_names()` (mirrors `_items_attr` / `_child_attrs` from Task 1.2). `IrCollection` renders extras keyed (`start='r'` → `AST(start='r', ...)`); `IrComposite` renders them positionally (`'r'` → `RULE('r', ...)`).

   `__repr__` on `IrStructure` produces an indented multi-line walk over extras and children. Concrete structural dataclasses use `@dataclass(..., repr=False)` so the inherited `__repr__` isn't shadowed (dataclass runs after `__init_subclass__`, so the auto-derived `_str_name` survives).

   Adding a new IR node type is small: declare the dataclass, inherit from `IrLeaf` / `IrCollection` / `IrComposite`, override `_inner_str` only if the default doesn't fit, override `_str_name` only if the auto-derivation isn't right.

Sections §IrNode structural protocol and §`walk.py` collapse and `IrEmitter` below are retained for historical traceability. Where they conflict with this revision, the revision wins. Concrete shapes appear in the revised implementation plan (Tasks 1.3 and 1.4).

## Background

The IrItem-based cutover is complete (2026-05-13). The pipeline has one shape, one set of IR nodes, one flavour ABC. Slice B's audit (`.wiki/lexic/slice-b-status.md`) identified four pending items:

1. **Token reservation (Tasks 33–34)** — GBNF pre-scan rejecting `<name>`/`<[N]>`/`!<name>` with `UnsupportedConstructError`.
2. **`canonicalize_groups()` stub** in `ir/regex_portable.py`.
3. **Task 11 — `LarkBuilder.build_transformer`** — inline or keep.
4. **`validate_portable` wiring** — built but unwired.

A wider audit during brainstorming surfaced additional findings:

- **`ir/helpers.py`** (HelperRuleRegistry) is exported from `ir/__init__.py` and has unit tests but **zero production callers**. Dead code carried over from the old IRBuilder design.
- **`ir/regex_portable.py`** is half-live: `literal_to_regex_pattern` is used by `lark_builder.py`; the validator half (`validate_portable`, `features_used`, `PORTABLE_FEATURES`, `canonicalize_groups`) has no consumer. The validator half carries the only `# type: ignore` + `# pylint: disable` directives in the codebase (for private `re._constants` / `re._parser` imports).
- **`utils/quantifiers.py`** is actively used but clunky: it parses bounds → string → bounds across module boundaries, with one codec for GBNF/Lark and an entirely separate `format_quantifier`/`place_quantifier` pair on the ABNF emitter.
- **`Quantifier(1, 1)`** appears 8+ times across `derive.py`, `transformer/build_transformer.py`, `generate.py`, `model_emitter.py` as a sentinel for "unquantified" — the dataclass has no semantics methods, every consumer reaches into raw `(min, max)` tuples.

The deeper structural problem these findings point at: `walk.py` carries three central registries (`_CHILDREN`, `_REBUILD`, `_DUMP`) keyed on IR node type. Adding a new node type today requires editing all three plus its action handlers in every consumer. The per-node intrinsic data (children layout, rebuild constructor, debug format) lives in a global table when it belongs on the node itself.

This spec closes Slice B and inverts the dispatch architecture in one campaign.

## Strategy

**Cut 1 — intrinsic vs external.** Intrinsic data about a node's shape moves onto the node as a method protocol. External operations whose meaning depends on the asker (target flavour, codegen pass) stay in dispatch tables.

**Cut 2 — `IrEmitter` as the canonical string-producing dispatcher.** `IrDispatch[_N, _T]` already has two canonical instantiations: `IrVisitor` (T=None, side-effects) and `IrTransformer` (T=_N, rewrites). The third is `IrEmitter` (T=str). Every operation that walks the IR and produces a string IS an `IrEmitter`: GBNF rendering, ABNF rendering, Lark rendering, debug dump — all subclasses of one class, sharing one mechanism. `FlavourEmitter` ABC and the `dump` top-level function both collapse into `IrEmitter` subclasses.

**Cut 3 — `IrQuantifier` as IrNode.** Rename `Quantifier` → `IrQuantifier`, make it an `IrNode` subclass (leaf). One data-carrying class — no subclass hierarchy. Per-flavour symbol mapping handles weird syntax (`!` = `(1,2)`, `%` = `(47,47)`, etc.) without subclassing.

**Cut 4 — LarkFlavour as full peer.** Promote Lark to a first-class `Flavour` alongside `GbnfFlavour` and `AbnfFlavour`. Lexic gains `.lark` as a user-facing grammar format. The internal codegen target (`parsing/lark_builder.py`) and the user-facing parser share one Flavour.

**Cut 5 — token reservation (scoped).** Add positional `<identifier>` pre-scan only. Indexed `<[N]>` and negation `!<name>` are deferred to a future slice with a proper negation design.

**Cut 6 — cleanup.** Delete dead code (`ir/helpers.py`, `utils/quantifiers.py`, `FlavourEmitter` and its concrete subclasses). Keep `ir/regex_portable.py` as-is, reserved for the future portability gate.

The architectural payoff: adding a new IR node type becomes a single-file edit (define the node, implement three methods). Adding a new grammar flavour requires only an `emit` dispatch table plus the parse side. Adding weird quantifier syntax in a future flavour is a dict entry.

## Architectural principles

Inherited from prior slices unchanged. This spec adds two:

**P10. Intrinsic data lives on the node.** Per-type structural data (children layout, reconstruction shape, debug repr) belongs in methods on the IR node type, not in central registries. External operations (emission, codegen, derivation passes) keep their dispatch tables.

**P11. String output is `IrEmitter`.** Any *flavour-controlled* operation that walks the IR and yields a string is an `IrEmitter[IrNode]` subclass — the T=str instantiation of `IrDispatch`. The `FlavourEmitter` ABC and per-flavour emitter subclasses are removed; a `Flavour` *is* (or owns) an `IrEmitter`. New string-producing IR operations subclass `IrEmitter`; they don't get bespoke entry points. *(Revised 2026-05-15: debug `dump()` does NOT go through this mechanism — see P12. The intrinsic canonical form is `__str__`; `IrEmitter` falls through to `str(node)` when its action table has no entry.)*

**P12. IR is open; flavours are closed.** New IR node types can be added at any time without touching any flavour or central dispatcher. They bring their own `__str__` (intrinsic canonical action) and inherit `__repr__`, `children()`, and `rebuild()` from the `IrLeaf` / `IrCollection` / `IrComposite` bases. Flavours are inherently closed — each one fixes the syntax of a target grammar format and provides actions for the node types it knows. The two meet at the `IrEmitter` action table's `.get()` fallthrough into `str(node)`. Debug `repr()` is likewise open: it uses only the node protocol (`children()`, dataclass defaults on leaves) — no per-type registry, no closed dispatcher.

## Architecture

### IrNode structural protocol

```python
class IrNode(ABC):
    """Structural protocol every IR node implements.

    Subclasses own their shape: how to enumerate children, how to rebuild
    themselves, and how to render themselves as a string by default
    (consumed by IrMetaEmitter; flavour emitters override via dispatch).
    No central registry of any of this.
    """

    def children(self) -> tuple[IrNode, ...]:
        """Children in traversal order. Default: leaf."""
        return ()

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:
        """Reconstruct with new children. Default: identity (leaves)."""
        return self

    def emit(self, indent: int = 0) -> str:
        """Default string rendering — used by IrMetaEmitter. Leaves ignore indent
        and return repr(self); branches override to inject indentation
        themselves before recursing. (Matches legacy _DUMP, which fell
        through to repr() for any node type without an entry.) Flavour
        emitters bypass this via their dispatch table."""
        return repr(self)
```

Every concrete IR node implements (or inherits defaults for) these three methods. Examples:

```python
@dataclass(frozen=True, slots=True)
class IrItem(IrNode):
    atom: IrAtom
    quantifier: IrQuantifier

    def children(self) -> tuple[IrNode, ...]:
        # Atom AND quantifier — both are IrNode subclasses. Exposing
        # both means transformer walks see the full structure.
        return (self.atom, self.quantifier)

    def rebuild(self, new_children):
        return IrItem(atom=new_children[0], quantifier=new_children[1])

    def emit(self, indent=0):
        return f"{'  ' * indent}IrItem({self.atom.emit(indent+1)}, q={self.quantifier})"


@dataclass(frozen=True, slots=True)
class IrSequence(IrNode):
    items: tuple[IrItem, ...]
    def children(self): return self.items
    def rebuild(self, new_children): return IrSequence(items=new_children)
```

Leaves (`IrLiteral`, `IrCharClass`, `IrRuleRef`, `IrQuantifier`) inherit default `children`/`rebuild`; they override `emit()` with a node-appropriate format.

### `walk.py` collapse and `IrEmitter`

`_CHILDREN`, `_REBUILD`, `_DUMP` central dicts **delete**. `IrDispatch.generic_visit` calls `node.children()`. `IrTransformer._combine` calls `node.rebuild(new_children)`. The top-level `dump()` function deletes; debug rendering is replaced by `IrMetaEmitter` (see below).

`IrDispatch[_N, _T]` gains a third canonical instantiation: `IrEmitter` (T=str).

```python
class IrDispatch[_N, _T]:
    action: dict[type, Callable[..., _T]]  # external operations only

    def visit(self, node: _N) -> _T:
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        return method(node)

    def generic_visit(self, node: _N) -> _T:
        old_children = node.children()
        new_children = tuple(self.visit(c) for c in old_children)
        return self._combine(node, old_children, new_children)


class IrVisitor[_N](IrDispatch[_N, None]):
    """Side-effect walks. T=None."""


class IrTransformer[_N](IrDispatch[_N, _N]):
    """Rewrites. T=_N. Combines via node.rebuild()."""
    def _combine(self, node, old_children, new_children):
        if not old_children or all(nc is oc for nc, oc in zip(new_children, old_children)):
            return node
        return node.rebuild(new_children)


class IrEmitter[_N](IrDispatch[_N, str]):
    """String emission. T=str. The base class for every string-producing
    IR walk: flavour emitters, debug dump, anything that turns IR into text.

    Default behaviour when `action` has no entry for a node type: call
    `node.emit()` — the per-node default rendering. Subclasses populate
    `action` to override per-type rendering for a specific target format.
    """
    action: dict[type, Callable[..., str]] = {}

    def visit(self, node: _N) -> str:
        handler = self.action.get(type(node))
        if handler is not None:
            return handler(node, self.visit)
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is not None:
            return method(node)
        return node.emit()  # fallback to node's default rendering


class IrMetaEmitter(IrEmitter[IrNode]):
    """The trivial emitter: pure fallthrough to each node's `emit()` method.

    Used for debug output. Equivalent to the old top-level `dump()` function
    but slots into the IrEmitter hierarchy so it composes with the same
    mechanism flavours use.
    """
    action = {}  # empty — everything falls through to node.emit()
```

The action-table pattern survives for *external* dispatch (operations whose answer depends on the asker). Only the intrinsic-data tables (`_CHILDREN`, `_REBUILD`, `_DUMP`) disappear.

### `IrQuantifier`

```python
@dataclass(frozen=True, slots=True)
class IrQuantifier(IrNode):
    min: int = 1
    max: int | None = 1
    # IrNode protocol: leaf — inherits no-children/identity-rebuild/default-emit.
```

That is the entire type. No subclass hierarchy. No `accepts()`. No `bounds()`. No `relax_to_optional()`. Just data that satisfies the IrNode protocol, like `IrLiteral` or `IrRuleRef`.

Weird quantifier syntax (per-flavour `!` for `(1,2)`, `%` for `(47,47)`, etc.) is handled by the per-flavour symbol table, not by quantifier subclasses.

### `Flavour` as `IrEmitter`

A `Flavour` *is* an `IrEmitter`. The emit dispatch table is `Flavour.action` — the same field every `IrDispatch` subclass uses. No separate `render()` function; `flavour.visit(node)` produces the grammar string.

```python
class Flavour(IrEmitter[IrNode], ABC):
    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[EscapeCodec]
    line_comment: ClassVar[str] = ""

    # Punctuation (separators, joiners, quotes, empty-body sentinel) is
    # NOT carried as ClassVars. Each per-flavour difference lives inside
    # the action lambda for the relevant IR node type: action[IrRule]
    # knows its own separator, action[IrAlternation] knows its own
    # joiner, action[IrSequence] handles the empty-body case via
    # `or '""'`. Duplicating these as ClassVars would split state
    # across two homes.

    # The emit dispatch table (inherited slot from IrDispatch).
    # Keyed on IR node type. Renderers receive (node, recurse).
    action: ClassVar[dict[type[IrNode], Callable[[IrNode, Callable[[IrNode], str]], str]]]

    # Quantifier sub-dispatch — keyed on (min, max) for symbolic forms.
    # The action[IrQuantifier] renderer consults this then falls through
    # to the flavour's generic {n,m}-style formatting for unmapped bounds.
    quantifier_symbols: ClassVar[dict[tuple[int, int | None], str]]

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> IrQuantifier: ...

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]: ...

    @classmethod
    def pre_parse_check(cls, text: str) -> None:
        """Flavour-specific source-text validation hook.

        Called from MetaGrammarParser.parse() before the Lark parse runs.
        Default: no-op. GbnfFlavour overrides to scan for reserved
        token-reference syntax.
        """


def render_specs(specs: list[RuleSpec], flavour: Flavour) -> str:
    """RuleSpec-list entry point for grammar emission.

    Composes per-rule rendering via flavour.visit(). Thin orchestration
    around the existing IrDispatch machinery.
    """
    ...
```

`ir/emit.py` survives as a small shell holding `IrEmitter`, `IrMetaEmitter`, and `render_specs`. Or `IrEmitter` and `IrMetaEmitter` may live in `ir/walk.py` alongside `IrVisitor` / `IrTransformer`, with `ir/emit.py` containing only the `render_specs` helper. Decided at execution; placement is purely organizational.

### Example: `GbnfFlavour`

```python
def _emit_gbnf_quantifier(q: IrQuantifier, _r) -> str:
    key = (q.min, q.max)
    if key in GbnfFlavour.quantifier_symbols:
        return GbnfFlavour.quantifier_symbols[key]
    if q.min == q.max:    return f"{{{q.min}}}"
    if q.max is None:     return f"{{{q.min},}}"
    return f"{{{q.min},{q.max}}}"


class GbnfFlavour(Flavour):
    name = "gbnf"
    extensions = (".gbnf",)
    meta_grammar = GBNF_META_GRAMMAR
    escapes = GbnfEscapes
    line_comment = "#"

    quantifier_symbols = {(1,1): "", (0,1): "?", (0,None): "*", (1,None): "+"}

    action = {
        IrLiteral:     lambda n, _r: f'"{GbnfFlavour.escapes.encode(n.value)}"',
        IrCharClass:   lambda n, _r: f"[{'^' if n.negated else ''}{n.pattern}]",
        IrRuleRef:     lambda n, _r: n.name,
        IrGroup:       lambda n, r:  f"({r(n.body)})",
        IrQuantifier:  _emit_gbnf_quantifier,
        IrItem:        lambda n, r:  f"{r(n.atom)}{r(n.quantifier)}",
        IrSequence:    lambda n, r:  " ".join(r(it) for it in n.items) or '""',
        IrAlternation: lambda n, r:  " | ".join(r(arm) for arm in n.arms),
        IrRule:        lambda n, r:  f"{n.name} ::= {r(n.body)}",
        IrAst:         lambda n, r:  "\n".join(r(rule) for rule in n.rules) + "\n",
    }

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier: ...

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]: ...

    @classmethod
    def pre_parse_check(cls, text: str) -> None:
        _check_no_positional_token_syntax(text)  # § Token reservation
```

`AbnfFlavour` mirrors this structure with prefix-placement on `action[IrItem]` (quantifier before atom) and its own `_emit_abnf_quantifier`. No `place_quantifier` / `format_quantifier` decorators — the per-type lambda owns its layout.

### `LarkFlavour` — promotion to full peer

New module layout:

```
src/lexic/grammars/lark/
  __init__.py
  flavour.py        LarkFlavour(Flavour)
  meta_grammar.py   Lark meta-grammar for parsing user-written .lark files
  escapes.py        LarkEscapes(EscapeCodec)
```

Configuration:

- `name = "lark"`
- `extensions = (".lark",)` — registered via `grammars/__init__.py`
- `line_comment = "//"`
- `action[IrRule]` uses `":"` as the separator (Lark uses colon, not `::=`) — punctuation lives in the action lambda, not as a ClassVar.
- `parse_quantifier`: `?`, `*`, `+`, plus Lark-specific `~n` (exact) and `~n..m` (range)
- `parse_charclass`: regex char-class syntax (Lark embeds these inside `/.../`)
- `quantifier_symbols`: `{(1,1): "", (0,1): "?", (0,None): "*", (1,None): "+"}`; the `emit[IrQuantifier]` renderer falls through to `~{n}` / `~{n}..{m}` for non-symbolic bounds

`parsing/lark_builder.py` shrinks to a thin orchestrator:

```python
def build_lark(specs, classes, start_rule):
    grammar_str = render_specs(specs, LarkFlavour())
    parser = lark.Lark(grammar_str, start=start_rule, parser="lalr", ...)
    transformer = build_transformer(specs, classes)
    return grammar_str, parser, transformer
```

The bespoke `_regex_terminal`, `_bracket`, and per-atom helpers in the current `lark_builder.py` migrate into `LarkFlavour.action` entries. The internal codegen use case (runtime parser construction) and the user-facing use case (compile `.lark` files) share one Flavour.

**Sharp edge to flag for execution:** `LarkFlavour.action[IrItem]` needs the regex-terminal vs rule-token distinction — when bounds can't be expressed as suffix quantifiers (`?`/`*`/`+`), the atom must be rendered as `/pattern/` with `{n,m}` embedded inside the regex. This is the trickiest renderer in the migration.

### Token reservation (positional only)

`GbnfFlavour.pre_parse_check` scans source text for `<identifier>` patterns before the meta-grammar parser runs:

```python
def _check_no_positional_token_syntax(text: str) -> None:
    """Reject GBNF positional token-reference syntax.

    Scans for <identifier> patterns outside of comments and quoted literals.
    Indexed (<[N]>) and negation (!<name>) refs are not checked — those
    are deferred to a future slice with a proper negation design.
    """
    # Strip # line comments and "..." string literals, then regex-scan
    # for <name> patterns. Raise UnsupportedConstructError on match.
    ...
```

Error wording: `UnsupportedConstructError(f"GBNF positional token-reference syntax {match!r} is reserved for future Vyx use; rename the rule or remove the angle brackets")`.

The scanner skips `#`-line comments and `"..."` string literals so a literal `"<think>"` inside a quoted body does not trigger.

### Module map post-cutover

```
src/lexic/
  base.py · compile.py · exceptions.py · parse.py · generate.py
  ir/
    nodes.py            IrNode protocol + all IR node types incl. IrQuantifier
    spec.py · derive.py · directives.py · charclass.py · escapes.py
    naming.py · topo.py
    walk.py             IrDispatch + IrVisitor + IrTransformer + IrEmitter + IrMetaEmitter;
                        no _CHILDREN/_REBUILD/_DUMP
    emit.py             render_specs() — small RuleSpec-list shell
    regex_portable.py   unchanged (kept for future portability gate)
    [helpers.py]        DELETED
  grammars/
    __init__.py         registers GbnfFlavour, AbnfFlavour, LarkFlavour
    flavour.py          Flavour ABC with emit/quantifier_symbols/pre_parse_check
    gbnf/
      flavour.py        GbnfFlavour — emit table, parse, token-syntax scanner
      escapes.py · meta_grammar.py
      [emitter.py]      DELETED
    abnf/
      flavour.py        AbnfFlavour — emit table, parse
      escapes.py · meta_grammar.py
      [emitter.py]      DELETED
    lark/                NEW
      flavour.py · escapes.py · meta_grammar.py
  parsing/
    meta_parser.py      calls flavour.pre_parse_check before Lark parse
    lark_builder.py     thin: render_specs(specs, LarkFlavour) + parser/transformer wire
    transformer/
  codegen/
    aliases.py · model_emitter.py · __init__.py
  utils/
    names.py
    [quantifiers.py]    DELETED
```

## Migration strategy

Single campaign; tests are the safety net. The 448-test suite stays green at every numbered step.

1. **IrNode structural protocol.** Add `children()` / `rebuild()` / `emit()` to every IrNode subclass. Delete `_CHILDREN` / `_REBUILD` / `_DUMP` in `walk.py`. Generic-visit and transformer-combine now go through node methods. The top-level `dump()` function is preserved temporarily by delegating to `node.emit()` until step 3 introduces `IrMetaEmitter`. Pure mechanical move; tests pass.

2. **`IrQuantifier` rename + IrNode subclass.** Rename `Quantifier` → `IrQuantifier`, make it inherit `IrNode` (leaf). Mechanical rename across all call sites. No semantic change.

3. **`IrEmitter` + `IrMetaEmitter` + unified flavour emit.** Add `IrEmitter[_N]` (the T=str instantiation of `IrDispatch`) and `IrMetaEmitter` (debug-default) to `ir/walk.py`. Refactor `Flavour` to subclass `IrEmitter[IrNode]`; add `Flavour.action` (emit table), `Flavour.quantifier_symbols`, `Flavour.pre_parse_check`. Add `render_specs()` shell in `ir/emit.py`. Migrate `GbnfFlavour` and `AbnfFlavour` to populate their `action` tables. Delete `FlavourEmitter`, `GbnfEmitter`, `AbnfEmitter`. Delete `utils/quantifiers.py`. Per-flavour emit tests cover what `test_quantifiers.py` used to. Replace top-level `dump()` call sites with `IrMetaEmitter().visit(node)`.

   If this step gets messy in practice, split into 3a (add dispatch alongside FlavourEmitter, migrate consumers one-by-one) and 3b (delete FlavourEmitter once nothing references it).

4. **Promote `LarkFlavour`.** Create `grammars/lark/`. Register `.lark`. Migrate `parsing/lark_builder.py` to use `render_specs(specs, LarkFlavour())`. Add `tests/unit/lexic/grammars/lark/`, `tests/integration/test_compile_grammar_lark.py`; extend `test_cross_flavour.py` with Lark conversions.

   Sub-strategy: start with a tiny `.lark` grammar (one rule, one terminal), incrementally add features until the existing GBNF ground-truth grammars can be expressed as `.lark` equivalents.

5. **Token reservation.** Add positional `<identifier>` scan to `GbnfFlavour.pre_parse_check`. Add `tests/integration/test_token_reservation.py`.

6. **Small cleanup.** Delete `ir/helpers.py` + its test. Remove `HelperRuleRegistry` from `ir/__init__.py` exports. Decide on `LarkBuilder.build_transformer` inline-vs-keep.

7. **Wiki updates.** `slice-b-status.md` retires (slice closed). Update `architecture.md`, `flavour-system.md`, `ir-shapes.md` for: unified flavour emit dispatch, IrQuantifier rename + IrNode protocol, IrNode intrinsic methods, LarkFlavour as third peer. New decision entries in `decisions.md` for the intrinsic-on-node cut and unified dispatch. `log.md` entry summarizing slice closure.

## Invariants enforced throughout

- Full test suite green after each numbered step (each step independently revertable / commitable).
- Round-trip fidelity: every existing ground-truth grammar still round-trips byte-equal under its source flavour.
- Layering: no new runtime → codegen import edges beyond the two existing exceptions (`base.py` → `lexic.grammars.gbnf.emitter`; `compile.py` → `lexic.codegen` and `lexic.parsing.lark_builder`). Note: the first exception's import target changes (the emitter module is gone), so `base.py` will need to point at the new GBNF rendering entry point.
- No `# type: ignore` / `# pylint: disable` introduced. The existing two in `regex_portable.py` stay as-is.

## Risk areas

- **Step 3** is the largest single hop. Mitigation: split 3a/3b if needed.
- **Step 4** Lark meta-grammar is new code with no prior coverage. Mitigation: incremental build against `.lark` versions of existing ground-truth grammars.
- **Step 1** is easy to under-cover (miss a node type). Mitigation: temporarily assert in `IrDispatch.generic_visit` that `node.children()` matches what the old `_CHILDREN[type(node)]` would have returned, during the cutover step.
- **`base.py` → `lexic.grammars.gbnf.emitter` import edge** (CLAUDE.md-documented runtime→codegen exception) changes target when `GbnfEmitter` deletes. The new edge points at `GbnfFlavour` (its `action` table + `visit()` method, inherited from `IrEmitter`). Update CLAUDE.md and `.wiki/lexic/architecture.md` accordingly.

## Out of scope

- Indexed token refs (`<[N]>`) and negation refs (`!<name>`) — deferred to a future slice with a proper negation design.
- Wiring `validate_portable` / `PORTABLE_FEATURES` into the emit path — module kept as-is for the future portability gate; no consumer added in this slice.
- `IrPredicate` / `IrEnum` quantifier extension types — flat `IrQuantifier(min, max)` is enough for everything in scope; extension types resurface only if a future flavour actually needs them.
- Quantifier extension beyond bounds (e.g. predicate-based "Fibonacci many" quantifiers) — `(min, max)` covers every grammar format in scope.
- Absorbing `FlavourEmitter`'s decorator helpers (`quote`, `wrap_group`, `render_charclass`, `render_inline_regex`) as standalone utilities — they get inlined into the per-type lambdas; nothing reusable survives.

## Execution-time decisions (resolved)

- **`LarkBuilder.build_transformer`** — inlined into `build_lark` (Task 4.5). Task 6.2 is consequently a no-op and may be dropped.
- **Placement of `IrEmitter` / `IrMetaEmitter`** — `ir/walk.py` (next to `IrVisitor` / `IrTransformer`). `ir/emit.py` keeps only `render_specs`.
- **Lark `parse_quantifier` `~` syntax** — parse-side accepts `?` `*` `+` and `~n` / `~n..m` (full Lark). Emit-side always produces `{n,m}` form for non-symbolic bounds to preserve byte-equality with the legacy `bounds_to_quantifier` output (Task 4.3).
