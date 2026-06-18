# Slice B — IrAction/IrOp substrate + Flavour-as-IrEmitter

**Date:** 2026-05-17
**Status:** Draft (brainstormed).
**Scope companion:** `2026-05-17-slice-b-deferred-work.md` — authoritative list of what is deliberately **out** of this slice (LarkFlavour, token reservation, codegen pass migration, pure-IrOp expression of stateful passes, `IrDispatch`-as-IrNode bonus features beyond what is listed here).
**Supersedes (in part):** `2026-05-14-slice-b-closure-and-dispatch-unification-design.md`. The 2026-05-14 spec stays in the tree for traceability; where the two conflict, this spec wins for everything inside its scope.
**Implementation plan:** to be written next.

## What changed since the 2026-05-14 spec

Tasks 1.1–1.3 of the 2026-05-14 plan landed: the rich IR node hierarchy (`IrNode` → `IrLeaf` / `IrStructure` → `IrCollection[_T]` / `IrComposite[*_Ts]`) exists, every concrete node has `children()` / `rebuild()` / `__str__` / `__repr__` via the hierarchy, and the placeholder canonical-form notation is in place.

Task 1.4 (introduce `IrAction` / `IrOp` algebra + collapse `IrDispatch` + delete `_CHILDREN` / `_REBUILD` / `_DUMP`) was a single monolithic task. Walking up to its design surfaced a deeper issue: **the existing closed-subclass passes (`_HoistTransformer`, `_RuleRefFinder`) still hardcode IR shape**. They subclass `IrTransformer` / `IrVisitor` and override `visit_<TypeName>` methods. The 2026-05-15 revision noted this for flavours but kept the IR-internal passes as closed subclasses.

That violates the same principle (P12) that motivated the substrate in the first place: **IR is open; consumers describe their closeness via data, not by subclassing**. The fresh design extends the action-table substrate to every IR pass — not just flavour emit. `_HoistTransformer` and `_RuleRefFinder` become factory functions that build `IrTransformer` / `IrVisitor` instances loaded with `actions` tables. No `visit_<TypeName>`. No closed subclasses.

A second shift: **`IrDispatch` is not parameterized over a single result type.** Each `IrAction` declares its own target type and result type. A dispatcher carrying actions with heterogeneous returns is valid. `IrTransformer` / `IrVisitor` / `IrEmitter` become thin presets that differ only in their default-on-miss behaviour.

A third shift: **`IrAction`, every `IrOp` variant, and `IrDispatch` itself are `IrNode` subclasses.** They inherit `children()` / `rebuild()` / `__str__` / `__repr__` mechanically from `IrCollection` / `IrComposite`. The IR describes the IR. A `Flavour` is literally an IR tree of actions; `repr(GbnfFlavour())` produces a structured dump of its dispatch behaviour. (The downstream payoff — `IrFlavour` text format, `PyFlavourCodegenRenderer` — is deferred per the scope companion. The structural claim is paid for here.)

## Architectural principles

Inherited from prior slices unchanged. This spec adds three (renumbered to follow P10/P11/P12 from the 2026-05-14 spec):

**P10. Intrinsic data lives on the node.** Per-type structural shape (children layout, reconstruction, canonical string, debug repr) belongs in methods on the IR node type, not in central registries. *(From 2026-05-14, restated.)*

**P11. String output is an `IrEmitter`.** Any flavour-controlled walk that yields a string is an `IrEmitter` instance loaded with actions. The `FlavourEmitter` ABC and per-flavour emitter subclasses are removed. *(From 2026-05-14, restated.)*

**P12. IR is open; behaviour is data.** New IR node types can be added at any time without touching any existing dispatcher or pass. Adding behaviour for them — emit, hoist, predicate, transform — is *adding an `IrAction` to a table*, not subclassing. No production pass in the codebase is a closed `IrDispatch` subclass with `visit_<TypeName>` overrides. *(Strengthened from 2026-05-14: the substrate now applies to IR-internal passes too, not just flavour emit.)*

**P13. The IR describes the IR.** `IrAction` and every `IrOp` variant are `IrNode` subclasses. `IrDispatch` (and its `IrTransformer` / `IrVisitor` / `IrEmitter` / `Flavour` subclasses) are `IrNode` subclasses. They inherit `children()` / `rebuild()` / `__str__` / `__repr__` mechanically. No bespoke debug paths; no off-protocol structural data.

**P14. `IrDispatch` does not bound its result type.** Each `IrAction` declares its own `target_type` and result type. The dispatcher's contract is "evaluate the body of the matching action, or fall through to `default()`" — not "produce a value of fixed type `T`". The presets (`IrTransformer` / `IrVisitor` / `IrEmitter`) differ only in their `default()` behaviour.

**P15. Action `target_type` participates in the type hierarchy.** Action lookup walks `type(node).__mro__` concrete-first, so an `IrAction` keyed on an abstract base (`IrLeaf`, `IrStructure`, `IrOp`, even `IrNode` for a universal catch-all) matches every subclass. Concrete keys win over abstract keys. This means the action table carries its own intra-table defaults — populating a table does not commit a flavour or pass to enumerating every concrete IR type; ABC-keyed actions express "for everything in this branch, do this."

**P16. Pre-recursion is a per-instance data hook.** `IrDispatch` carries an optional `pre_recurse: Callable[[IrNode], object] | None = None` field. Before recursing into children, the dispatcher invokes `pre_recurse(node)` if set; returning the class-level `_SKIP_RECURSION` sentinel suppresses recursion (used for short-circuit visitors like `has_ruleref` after the first hit). Any other return value is ignored. This is the only authorized substrate affordance beyond action lookup — no method-based `_pre_recurse` / `_post_recurse` hooks; no `__call__` override on subclasses. Bracketing-recursion (e.g. `_PatternAliasVisitor`'s IrGroup frame push) composes with action post-recursion: the `pre_recurse` callable pushes into a closure-captured frame stack; an `IrAction` on the relevant type pops after auto-recursion completes.

**P17. Dispatcher mutable scratch lives in closures.** `IrDispatch` instances are frozen dataclasses whose data fields are `actions` and `pre_recurse`. Per-pass mutable state (a "found" flag, a helpers list, a frame stack, an aliases dict) lives in a closure or external object that `IrCallable` handlers and `pre_recurse` capture. Dispatchers thus stay cleanly value-hashable. Implementation-detail caches (`_exact_table`, `_resolve_cache`) are declared as `field(init=False, hash=False, compare=False, repr=False)` and populated in `__post_init__` via `object.__setattr__` — they are not part of the dispatcher's identity. Mutating dict *contents* inside a frozen slot is permitted; frozen only blocks slot rebinding.

## Architecture

### `IrNode` — minimal protocol

Already in the codebase. `children()`, `rebuild()`, `__str__`, `__repr__`. Nothing else added in this slice. **No domain methods** (no `has_ruleref`, no `hoist`, no `needs_helper`). Domain questions are answered by dispatchers loaded with the right actions, not by methods on the node.

### `IrAction` and `IrOp` algebra — `src/lexic/ir/action.py`

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrOp(IrNode, ABC):
    """One operation in an action body. Self-describing IR node."""
    def eval(self, dispatch: IrDispatch, node: IrNode,
             new_children: tuple, /) -> object: ...

@dataclass(frozen=True, slots=True, repr=False)
class IrText(IrLeaf, IrOp):
    text: str
    def eval(self, *_): return self.text

@dataclass(frozen=True, slots=True, repr=False)
class IrField(IrLeaf, IrOp):
    """Read a named attribute of the dispatched node, raw."""
    field_name: str
    def eval(self, _d, node, _nc): return getattr(node, self.field_name)

@dataclass(frozen=True, slots=True, repr=False)
class IrRecurse(IrLeaf, IrOp):
    """Re-dispatch on a named child of the current node."""
    field_name: str
    def eval(self, d, node, _nc): return d(getattr(node, self.field_name))

@dataclass(frozen=True, slots=True, repr=False)
class IrSeq(IrCollection["IrOp"], IrOp):
    """Evaluate ops in order; return the str-concatenation of their results."""
    parts: tuple[IrOp, ...]
    _items_attr: ClassVar[str] = "parts"
    def eval(self, d, node, nc):
        return "".join(str(p.eval(d, node, nc)) for p in self.parts)

@dataclass(frozen=True, slots=True, repr=False)
class IrJoin(IrComposite["IrText", "IrText"], IrOp):
    """Dispatch each element of a named iterable child; join with separator;
    empty-iterable returns `empty`."""
    field_name: str
    separator: IrText
    empty: IrText
    _child_attrs: ClassVar[tuple[str, ...]] = ("separator", "empty")
    def eval(self, d, node, _nc):
        items = getattr(node, self.field_name)
        rendered = [str(d(it)) for it in items]
        return self.separator.text.join(rendered) if rendered else self.empty.text

@dataclass(frozen=True, slots=True, repr=False)
class IrCond(IrComposite["IrOp", "IrOp"], IrOp):
    """If the named attribute is truthy, evaluate then_op; else else_op."""
    field_name: str
    then_op: IrOp
    else_op: IrOp
    _child_attrs: ClassVar[tuple[str, ...]] = ("then_op", "else_op")
    def eval(self, d, node, nc):
        target = self.then_op if getattr(node, self.field_name) else self.else_op
        return target.eval(d, node, nc)

@dataclass(frozen=True, slots=True, repr=False)
class IrCallable(IrLeaf, IrOp):
    """Escape hatch. Procedural body — used where pure IrOp doesn't fit
    (stateful allocators, side-effect collectors, symbol-table lookups)."""
    handler: Callable[[IrDispatch, IrNode, tuple], object]
    def eval(self, d, node, nc): return self.handler(d, node, nc)

@dataclass(frozen=True, slots=True, repr=False)
class IrAction(IrComposite["IrOp"], IrOp):
    """Bind a target IR node type to an op body. The 'closeness expression'
    of a dispatcher: 'when you see this type, do this'."""
    target_type: type[IrNode]
    body: IrOp
    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    def eval(self, d, node, nc): return self.body.eval(d, node, nc)
```

`target_type` lives on `IrAction` only — it's a `type`, not an `IrNode`, so it doesn't go through `children()`. (`_child_attrs` enumerates IrNode-typed positional children; `target_type` is metadata. `_extra_field_names` / `_inner_str` from the existing `IrComposite` machinery render it inline in `__str__`.)

The canonical `IrOp` variant set for this slice is exactly the seven above. **No new variants in this slice** (anti-creep rule §5 of the deferred-work doc). If a flavour action needs more, the body is `IrCallable`.

### `IrDispatch` — unbounded, action-driven, an `IrNode`

```python
@dataclass(frozen=True, slots=True)
class IrDispatch(IrCollection["IrAction"], ABC):
    """Action-driven IR walker. The actions ARE the children — `IrDispatch`
    is itself an `IrNode`, so `repr(dispatch)` dumps the full behaviour tree.

    Dispatch is always soft at this base: a type miss falls through to
    `default(node, new_children)`. Subclasses customize `default()`.
    Lookup walks `type(node).__mro__` concrete-first so ABC-keyed actions
    catch whole hierarchy branches.

    Caches (`_exact_table`, `_resolve_cache`) are init=False fields opted out
    of eq/hash/repr — they are implementation detail, not identity. Mutating
    the dict contents inside the frozen slot is permitted; frozen only blocks
    slot rebinding.
    """
    actions: tuple[IrAction, ...] = ()
    pre_recurse: Callable[[IrNode], object] | None = None
    _exact_table: dict[type, IrAction] = field(
        init=False, hash=False, compare=False, repr=False,
    )
    _resolve_cache: dict[type, IrAction | None] = field(
        init=False, hash=False, compare=False, repr=False,
    )
    _items_attr: ClassVar[str] = "actions"
    _SKIP_RECURSION: ClassVar[object] = object()

    def __post_init__(self) -> None:
        object.__setattr__(self, "_exact_table",
                           {a.target_type: a for a in self.actions})
        object.__setattr__(self, "_resolve_cache", {})

    def _resolve(self, node_type: type) -> IrAction | None:
        """Concrete-first MRO walk. Memoized; misses cached as None."""
        cache = self._resolve_cache
        if node_type in cache:
            return cache[node_type]
        for cls in node_type.__mro__:
            action = self._exact_table.get(cls)
            if action is not None:
                cache[node_type] = action
                return action
        cache[node_type] = None
        return None

    def __call__(self, node: IrNode) -> object:
        if self.pre_recurse is not None and \
                self.pre_recurse(node) is self._SKIP_RECURSION:
            return self.default(node, ())
        new_children = tuple(self(c) for c in node.children())
        action = self._resolve(type(node))
        if action is not None:
            return action.eval(self, node, new_children)
        return self.default(node, new_children)

    @abstractmethod
    def default(self, node: IrNode, new_children: tuple) -> object: ...
```

`__call__` is the only entry point. **No `visit()` / `generic_visit()` / `_combine()` / `visit_<TypeName>` getattr machinery.** Recursion happens once, at the top of `__call__`; the action body decides how to use the recursed children (or whether to re-dispatch on a specific named child via `IrRecurse`).

### Preset subclasses

```python
class IrTransformer(IrDispatch):
    """Rewrite preset. Default: rebuild node from new_children if changed,
    else identity."""
    def default(self, node, new_children):
        old = node.children()
        if not old or all(nc is oc for nc, oc in zip(new_children, old)):
            return node
        return node.rebuild(new_children)

class IrVisitor(IrDispatch):
    """Side-effect preset. Default: None."""
    def default(self, _node, _nc): return None

class IrEmitter(IrDispatch):
    """String-emission preset. Default: `str(node)` when actions table is
    empty (canonical-form fallthrough); `raise UnsupportedConstructError`
    when actions table is non-empty (closed-world flavour saw an unknown
    type). A flavour that wants to fall back to canonical form for
    unknown types can declare an `IrAction(IrNode, IrCallable(str_node))`
    catch-all instead of relying on `default()`."""
    def default(self, node, _nc):
        if not self.actions:
            return str(node)
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no action for node type {type(node).__name__!r}")
```

These are the only three presets. Each is a thin subclass of `IrDispatch` that fixes `default()`.

### `Flavour` as `IrEmitter` singleton

```python
class Flavour(IrEmitter, ABC):
    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[type[EscapeCodec]]
    line_comment: ClassVar[str] = ""
    quantifier_symbols: ClassVar[dict[tuple[int, int | None], str]]

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> IrQuantifier: ...
    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]: ...
```

Per-flavour metadata lives as `ClassVar`s (class identity, not tree structure). Per-flavour behaviour lives in the `actions` tuple (tree structure, inherited via `IrCollection`).

Concrete flavours are module-level singletons:

```python
_GBNF_ACTIONS: tuple[IrAction, ...] = (
    IrAction(IrLiteral,     IrSeq((IrText('"'), IrCallable(_gbnf_encode_literal), IrText('"')))),
    IrAction(IrCharClass,   IrCallable(_gbnf_charclass)),       # negation handling
    IrAction(IrRuleRef,     IrField("name")),
    IrAction(IrGroup,       IrSeq((IrText("("), IrRecurse("body"), IrText(")")))),
    IrAction(IrQuantifier,  IrCallable(_gbnf_quantifier)),      # symbol-table lookup
    IrAction(IrItem,        IrSeq((IrRecurse("atom"), IrRecurse("quantifier")))),
    IrAction(IrSequence,    IrJoin("items", IrText(" "), IrText('""'))),
    IrAction(IrAlternation, IrJoin("arms", IrText(" | "), IrText(""))),
    IrAction(IrRule,        IrSeq((IrField("name"), IrText(" ::= "), IrRecurse("body")))),
    IrAction(IrAst,         IrCallable(_gbnf_ast)),             # newline-join + trailing newline
)

class GbnfFlavour(Flavour):
    name = "gbnf"
    extensions = (".gbnf",)
    meta_grammar = GBNF_META_GRAMMAR
    escapes = GbnfEscapes
    line_comment = "#"
    quantifier_symbols = {(1,1): "", (0,1): "?", (0,None): "*", (1,None): "+"}
    # ... parse_quantifier / parse_charclass static methods

GBNF = GbnfFlavour(actions=_GBNF_ACTIONS)
```

`AbnfFlavour` mirrors this with its own action tuple (prefix-placement on `IrItem`: `quantifier` before `atom`) and its own quantifier-symbols. No `place_quantifier` / `format_quantifier` decorators; the per-type action owns its layout.

`IrCallable` is used freely where a pure IrOp body would be contorted (escape encoding, char-class negation prefix, quantifier symbol-table lookup, AST trailing newline). The substrate proves itself on the cases that ARE pure IrOp (`IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`). Future slices migrate the `IrCallable`s.

### Migration of IR-internal passes

`_HoistTransformer` and `_RuleRefFinder` in `ir/derive.py` stop being closed subclasses. They become factory functions:

```python
def has_ruleref(node: IrNode) -> bool:
    finder = IrVisitor(actions=(
        IrAction(IrRuleRef, IrCallable(_set_found)),
    ))
    finder.found = False    # mutable scratch on the instance
    finder(node)
    return finder.found

def _set_found(d, _node, _nc):
    d.found = True

def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    helpers: list[IrRule] = []
    name_set = {r.name for r in ast.rules}
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        t = IrTransformer(actions=(
            IrAction(IrItem, IrCallable(
                _make_hoist_item(rule.name, name_set, helpers)
            )),
        ))
        new_body = t(rule.body)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), helpers
```

`_make_hoist_item(parent, name_set, helpers)` returns a closure handler bound to that pass's external state. The hoist *logic* (recurse into atom first; check `isinstance(new_atom, IrGroup)` + quantifier ≠ `(1,1)` + has-ruleref; allocate name; append helper) lives in the `IrCallable` body. The substrate handles dispatch and recursion.

No `visit_IrItem`. No `_RuleRefFinder` class. No `_HoistTransformer` class.

### Module map after this slice

```
src/lexic/
  ir/
    nodes.py            unchanged (1.1–1.3 already landed)
    action.py           NEW — IrOp / IrAction / IrText / IrField / IrRecurse /
                        IrSeq / IrJoin / IrCond / IrCallable
    walk.py             IrDispatch (action-driven, unbounded result, IrNode) +
                        IrTransformer + IrVisitor + IrEmitter presets.
                        NO _CHILDREN / _REBUILD / _DUMP / dump() / visit() /
                        generic_visit / visit_<TypeName>.
    emit.py             render_specs(specs, flavour) — thin shell
    derive.py           hoist_helpers / has_ruleref as factory functions.
                        NO _HoistTransformer / _RuleRefFinder classes.
    spec.py · directives.py · charclass.py · escapes.py · naming.py · topo.py
                        (unchanged in this slice)
    [helpers.py]        deletion candidate (opportunistic; see deferred §9)
  grammars/
    __init__.py         registers GbnfFlavour, AbnfFlavour
    flavour.py          Flavour(IrEmitter, ABC) — metadata ClassVars,
                        parse_* abstract staticmethods. NO pre_parse_check.
    gbnf/
      flavour.py        GbnfFlavour + module-level GBNF singleton + action tuple
      escapes.py · meta_grammar.py
      [emitter.py]      DELETED
    abnf/
      flavour.py        AbnfFlavour + module-level ABNF singleton + action tuple
      escapes.py · meta_grammar.py
      [emitter.py]      DELETED
  parsing/
    meta_parser.py      unchanged
    lark_builder.py     unchanged except mechanical fixes if IrDispatch API
                        changes force them. Stays a hand-written internal
                        target; NOT a registered Flavour.
    transformer/        unchanged
  codegen/
    aliases.py · model_emitter.py · __init__.py
                        closed-subclass visitors inside codegen/ stay closed;
                        mechanical fixes only if forced (deferred §3).
  utils/
    names.py
    [quantifiers.py]    DELETED
  base.py · compile.py · exceptions.py · parse.py · generate.py
    base.py             import target for `to_gbnf()` flips from
                        `lexic.grammars.gbnf.emitter` to the `GBNF` singleton.
```

## Migration strategy

Single campaign; the 448-test suite stays green at every numbered step. Each step independently revertable.

1. **Introduce `ir/action.py`.** `IrOp` ABC + the seven canonical variants (`IrText`, `IrField`, `IrRecurse`, `IrSeq`, `IrJoin`, `IrCond`, `IrCallable`) + `IrAction`. All are `IrNode` subclasses; mechanical `children()` / `rebuild()` / `__str__` / `__repr__` via `IrLeaf` / `IrComposite` / `IrCollection`. Unit tests cover each variant's `eval()` semantics in isolation and via a tiny ad-hoc dispatcher.

2. **Rewrite `IrDispatch`.** Replace the existing `IrDispatch` / `IrVisitor` / `IrTransformer` in `walk.py` with the action-driven, unbounded-result, `IrCollection["IrAction"]`-based dispatcher. `IrEmitter` arrives in this step too (closed-world default-on-miss). Delete `_CHILDREN`, `_REBUILD`, `_DUMP`, `dump()`, `visit()`, `generic_visit()`, `_combine()`. The legacy `visit_<TypeName>` discovery is gone.

3. **Migrate `_RuleRefFinder` and `_HoistTransformer`.** Convert to factory functions returning `IrVisitor` / `IrTransformer` instances loaded with `IrAction` tables. Delete the closed-subclass declarations.

   If `codegen/aliases.py` or other consumers carry closed-subclass `visit_<TypeName>` visitors, the **minimum mechanical fix** is applied to keep them compiling (e.g. they switch to calling `dispatch(node)` instead of `dispatch.visit(node)`); behavioural rewrite to action tables is deferred per scope §3 / §4.

4. **`Quantifier` → `IrQuantifier`.** Mechanical rename across `nodes.py`, `derive.py`, `transformer/build_transformer.py`, `generate.py`, `model_emitter.py`, tests. Already an `IrLeaf`; no shape change. Done as its own step for blame clarity.

5. **`Flavour` as `IrEmitter`.** Refactor `grammars/flavour.py`: `Flavour(IrEmitter, ABC)` with class-var metadata + abstract `parse_quantifier` / `parse_charclass`. Add `render_specs(specs, flavour)` in `ir/emit.py`.

6. **Migrate `GbnfFlavour`.** Build the GBNF action tuple. Construct `GBNF = GbnfFlavour(actions=_GBNF_ACTIONS)` at module scope. Delete `grammars/gbnf/emitter.py`.

7. **Migrate `AbnfFlavour`.** Same for ABNF. Delete `grammars/abnf/emitter.py`.

8. **Migrate consumers.** `base.py` → `GBNF` singleton instead of `GbnfEmitter`. Codegen / `lark_builder.py` adjusted only as forced by `IrDispatch` API changes. Delete `utils/quantifiers.py` (per-flavour quantifier rendering now lives in each flavour's `IrAction(IrQuantifier, ...)` body).

9. **Opportunistic cleanup.** If `ir/helpers.py` is trivially safe to delete at this point, delete it (and its unit test, and the export from `ir/__init__.py`). Otherwise leave it (see deferred §9).

10. **Wiki + docs.** Update `.wiki/lexic/architecture.md`, `flavour-system.md`, `ir-shapes.md` for: the substrate (IrAction/IrOp/IrDispatch shape), IR-pass-by-action-table convention, IrQuantifier, Flavour-as-IrEmitter, module map shift. Decision entries in `decisions.md` for P12-strengthened, P13 (IR-describes-IR), P14 (unbounded result type). `log.md` entry. Update CLAUDE.md's "two deliberate exceptions" wording: the first exception's import target flips from `lexic.grammars.gbnf.emitter` to the `GBNF` singleton in `lexic.grammars.gbnf.flavour`.

## Invariants enforced throughout

- Full test suite green after each numbered step.
- Round-trip fidelity: every existing ground-truth grammar still round-trips byte-equal under its source flavour.
- Layering: no new runtime → codegen import edges beyond the two documented exceptions. The first exception's target changes per step 10.
- No new `# type: ignore` / `# pylint: disable`. The two existing entries in `regex_portable.py` stay as-is.
- No closed-subclass `IrDispatch` with `visit_<TypeName>` overrides remains in `ir/` after step 3. (Closed subclasses in `codegen/` and `parsing/transformer/` are deferred per scope §3 / §4 — they keep working through mechanical fixes only.)
- No `IrOp` variant beyond the seven canonical ones is introduced. `IrCallable` covers anything the algebra can't express cleanly.
- `pre_parse_check` does not appear in `Flavour` or any subclass.

## Risk areas

- **Step 2 is the deepest cut.** `IrDispatch` semantics change for every existing consumer in the same step. Mitigation: if the unbounded-result refactor is hairier than expected, land it as 2a (introduce new `IrDispatch` alongside old under a different name, migrate consumers one by one) and 2b (rename + delete old). The plan can split this if needed; the spec doesn't pre-commit.
- **`IrCallable` discipline.** Easy to reach for the escape hatch on every action and never write pure IrOp. Mitigation: the GBNF and ABNF action tables MUST express the structurally simple cases (`IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`) in pure IrOp. `IrCallable` is permitted for `IrLiteral` (escape encoding), `IrCharClass` (negation prefix), `IrQuantifier` (symbol-table lookup), `IrAst` (newline join + trailing newline). Any other `IrCallable` use during execution is a flag-for-discussion item, not a silent acceptance.
- **`IrAction.target_type` is a `type`, not an `IrNode`.** It must NOT appear in `children()`. `IrComposite` machinery (`_child_attrs` / `_extra_field_names`) needs to render it as `__str__` metadata without claiming it as a child. Existing `IrComposite` already supports extras-not-children; the IrAction class declaration just enumerates them correctly.
- **`repr(GbnfFlavour())` smoke test.** The structural payoff of P13 is testable: `repr(GBNF)` should produce a readable multi-line dump of the action tree. A small smoke test asserts this; it's expected to be cheap to write because everything inherits from `IrCollection` / `IrComposite`.
- **MRO-walk lookup correctness.** P15's "concrete wins over ABC" semantic must be tested directly: a dispatcher loaded with both `IrAction(IrLeaf, body_a)` and `IrAction(IrLiteral, body_b)` must invoke `body_b` for `IrLiteral` and `body_a` for any other leaf. The `_resolve` cache must also handle the negative case (cached `None` for genuine misses) so the fall-through to `default()` isn't bypassed.
- **Frozen-slot dict mutation.** `_resolve_cache[node_type] = ...` mutates dict *contents* inside a frozen slot — that's allowed. Rebinding the slot itself (`object.__setattr__(self, "_resolve_cache", new_dict)`) is allowed only inside `__post_init__`. A test should attempt `dispatch._resolve_cache = {}` and assert it raises `FrozenInstanceError`; the cache writes during normal dispatch must succeed.
- **`pre_recurse` short-circuit semantics.** A visitor with `pre_recurse=lambda n: dispatch._SKIP_RECURSION if state.found else None` must not recurse into children once `state.found` is set. Test: construct a deep tree with rulerefs only at the leaves and confirm visit counts before/after the first hit.

## Out of scope

Authoritative list: `2026-05-17-slice-b-deferred-work.md`. Brief restatement of the largest items:

- LarkFlavour promotion / `.lark` as user-facing extension / `grammars/lark/` directory — deferred.
- Positional / indexed / negation token-reference syntax + `Flavour.pre_parse_check` hook — deferred. The hook does not exist in this slice.
- Codegen-side closed-subclass visitor migration (`_PatternAliasVisitor` and any other inside `codegen/`) — deferred.
- Pure-IrOp expression of stateful passes (`_HoistTransformer`, `_RuleRefFinder` migrate to action tables but keep `IrCallable` bodies) — deferred.
- New IrOp variants beyond the canonical seven — deferred.
- Self-description bonus features (`PyFlavourCodegenRenderer`, `IrFlavour` text format) — deferred. P13's structural claim is paid for here; the renderers built on top of it are not.

Anti-creep enforcement: see the deferred-work doc's "Anti-creep rules" section.
