# Slice B — IrAction/IrOp substrate + Flavour-as-IrEmitter

**Date:** 2026-05-18
**Status:** Draft (brainstormed).
**Scope companion:** `2026-05-17-slice-b-deferred-work.md` — authoritative list of what is deliberately **out** of this slice.
**Supersedes:** `2026-05-17-slice-b-substrate-and-flavour-as-emitter-design.md` (a prior draft of the same slice that overcommitted on mechanism and was rejected). The 2026-05-17 draft stays in tree for traceability; where it conflicts with this one, this one wins.
**Implementation plan:** to be written next.

## Architectural principles

Inherited unchanged from prior slices. This slice adds:

**P10. Intrinsic data lives on the node.** Per-type structural shape (`children()`, `rebuild()`, `__str__`, `__repr__`) belongs in methods on the IR node type. *(From 2026-05-14, restated.)*

**P11. String output is an `IrEmitter`.** Any flavour-controlled walk that yields a string is an `IrEmitter` instance loaded with actions. The `FlavourEmitter` ABC and per-flavour emitter subclasses are removed.

**P12. IR is open; behaviour is data.** New IR node types can be added at any time without touching any existing dispatcher or pass. Behaviour for them is *adding an `IrAction` to a table*, not subclassing. No production pass in the codebase is a closed `IrDispatch` subclass with `visit_<TypeName>` overrides — within the scope of this slice. (Closed-subclass visitors inside `codegen/` and `parsing/transformer/` are deferred per the scope companion §3 / §4; they keep working through mechanical fixes only.)

**P13. The IR describes the IR.** `IrAction` and every `IrOp` variant are `IrNode` subclasses. `IrDispatch` (and its `IrTransformer` / `IrVisitor` / `IrEmitter` / `Flavour` subclasses) are `IrNode` subclasses. They inherit `children()` / `rebuild()` / `__str__` / `__repr__` mechanically from `IrCollection` / `IrComposite`.

**P14. `IrDispatch` does not bound its result type.** `IrDispatch` is generic on `_T`. Each preset pins `_T` to a different concrete type (`IrVisitor: None`, `IrTransformer: IrNode`, `IrEmitter: str`). The dispatcher's contract is "evaluate the matched action's body against `(node, new_children)`, or use the preset default if no action matches" — not "produce a value of fixed type `T` for every node universally".

**P15. Action `target_type` participates in the type hierarchy.** Action lookup walks `type(node).__mro__` concrete-first. An `IrAction` keyed on an abstract base (`IrLeaf`, `IrStructure`, `IrOp`, even `IrNode`) matches every subclass. Concrete keys win over abstract keys. A user-supplied `IrAction(IrNode, …)` therefore acts as a per-instance default-override; the preset's built-in default is the type-system equivalent of the catch-all the dispatcher falls through to when no action — including an `IrNode`-keyed one — matches.

**P16. Skip-recursion is intrinsic to `IrReturn`, not to the dispatcher.** `IrReturn(value)` raises a control-flow exception (`_Return`, subclass of `BaseException`) when evaluated. The exception unwinds through every nested `__call__` frame on its own; the dispatcher's entry point catches it and returns the carried value. There is no `pre_recurse` hook, no `_SKIP_RECURSION` sentinel, no engine-level inspection of return values. Leaves don't recurse because `children()` is empty; `IrReturn` returns because it raises. Both behaviours are intrinsic to the thing that has them.

## Architecture

### `IrAction` and `IrOp` algebra — `src/lexic/ir/action.py`

`IrOp[_T]` is `Generic[_T]`, an `IrNode` subclass. Concrete variants either pin `_T` (e.g. `IrText(IrOp[str])`) or re-parameterize (e.g. `IrSeq(IrOp[_T], Generic[_T])`).

Canonical inventory — nine variants:

| Op | Purpose |
|---|---|
| `IrReturn[_T](value)` | Control-flow short-circuit. `eval` raises `_Return(value)`. |
| `IrChild(name)` | Fixed-arity child result. Looks up `name` in the dispatched node's `_child_attrs` (an `IrComposite`) and returns the corresponding entry from `new_children`. Single result. |
| `IrChildren(name)` | Variable-arity children. Asserts `name == node._items_attr` (an `IrCollection`) and returns the full `new_children` tuple. |
| `IrSeq(parts)` | Sequence/concat. `IrOp[str]` — evaluates `parts` in order and returns `"".join(str(p.eval(...)) for p in self.parts)`. Used in emit contexts; not used by visitor / transformer passes in this slice. |
| `IrText(text)` | Literal `str`. `IrOp[str]`. |
| `IrField(name)` | Non-IrNode attribute on the dispatched node, returned as `str` (via `str()` of the value). |
| `IrCond[_T](field, then, else)` | Truthy-field branch. Evaluates `then` if `getattr(node, field)` is truthy, else `else`. |
| `IrJoin(children_op, separator, empty)` | Variable-arity join. `children_op` is typically `IrChildren(name)`; returns `separator.join(...)` of the children tuple, or `empty` if empty. `IrOp[str]`. |
| `IrCallable[_T](handler)` | Escape hatch. Procedural body: `handler(dispatch, node, new_children) -> _T`. |

`IrAction(IrComposite["IrOp"])` carries `target_type: type` (metadata, not a child) and `body: IrOp` (the single child, via `_child_attrs = ("body",)`). `__str__` renders `target_type.__name__` inline.

Dataclass decoration on all op variants and `IrAction`: `@dataclass(frozen=True, slots=True, repr=False)`. `IrCallable` is `@dataclass(frozen=True, slots=True, eq=False, hash=False, repr=False)` because callables don't have structural equality.

### `IrDispatch` — action-driven, an `IrNode` itself — `src/lexic/ir/walk.py`

```python
@dataclass(frozen=True, slots=True, repr=False)
class IrDispatch(IrCollection["IrAction"], Generic[_T]):
    """Action-driven IR walker. children() is the actions tuple.

    __call__(node) walks node.children() automatically, builds the
    new_children tuple, resolves the matching action via concrete-first
    MRO walk on type(node), and calls action.body.eval(self, node,
    new_children). On no match, falls through to the preset default.

    Skip-recursion is intrinsic to IrReturn (raises _Return); the entry
    point catches once at the top, so the exception unwinds through every
    nested __call__ frame on its own.

    Caches (_resolve_cache) are init=False fields opted out of eq/hash/
    repr — implementation detail, not identity. Mutating dict contents
    inside a frozen slot is permitted; frozen blocks slot rebinding only.
    """
    actions: tuple[IrAction, ...] = ()
    _resolve_cache: dict[type, IrAction | None] = field(
        init=False, hash=False, compare=False, repr=False,
    )
    _items_attr: ClassVar[str] = "actions"

    def __post_init__(self) -> None:
        object.__setattr__(self, "_resolve_cache", {})

    def __call__(self, node: IrNode) -> _T:
        try:
            return self._walk(node)
        except _Return as ret:
            return ret.value

    def _walk(self, node: IrNode) -> _T:
        new_children = tuple(self._walk(c) for c in node.children())
        action = self._resolve(type(node))
        if action is not None:
            return action.body.eval(self, node, new_children)
        return self._default(node, new_children)

    def _resolve(self, node_type: type) -> IrAction | None:
        cache = self._resolve_cache
        if node_type in cache:
            return cache[node_type]
        for cls in node_type.__mro__:
            for action in self.actions:
                if action.target_type is cls:
                    cache[node_type] = action
                    return action
        cache[node_type] = None
        return None

    def _default(self, node: IrNode, new_children: tuple) -> _T:
        # Preset subclasses override.
        ...
```

Entry/recursion split: `__call__` catches `_Return` once; `_walk` is the recursive engine and doesn't catch. The exception unwinds through every `_walk` frame to the single catch point in `__call__`.

### Presets

```python
class IrVisitor(IrDispatch[None]):
    def _default(self, node, new_children) -> None:
        return None

class IrTransformer(IrDispatch[IrNode]):
    def _default(self, node, new_children) -> IrNode:
        old = node.children()
        if not old or all(nc is oc for nc, oc in zip(new_children, old)):
            return node
        return node.rebuild(new_children)

class IrEmitter(IrDispatch[str]):
    def _default(self, node, new_children) -> str:
        if not self.actions:
            return str(node)         # canonical-form fallback
        raise UnsupportedConstructError(
            f"{type(self).__name__}: no action for {type(node).__name__!r}"
        )
```

All three are concrete subclasses, instantiable directly with an `actions=` tuple. Per-instance default override is `IrAction(IrNode, …)` — MRO catches it before the preset default fires.

## IR-internal pass migrations

### `has_ruleref` — module-level singleton, two-action visitor

```python
_HAS_RULEREF = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn(True)),))

@cache
def has_ruleref(node: IrNode) -> bool:
    return bool(_HAS_RULEREF(node))
```

Walk hits an `IrRuleRef`; action body is `IrReturn(True)`; `_Return(True)` raises and unwinds to `__call__`'s catch; result is `True`. Siblings and parents never see the unwind explicitly — they're just absent from the trace. Short-circuit comes from the exception, not from any flag or sentinel.

`_RuleRefFinder` is deleted.

### Hoist — factory + sub-dispatcher, no method on `IrAtom`

`IrAtom` stays as `IrLeaf | IrGroup` (`TypeAlias`). Recognition lives in a `derive.py`-internal sub-dispatcher:

```python
def _group_extract(_d, group, _nc):
    return group.body if has_ruleref(group.body) else None

def _no_extract(_d, _n, _nc):
    return None

_EXTRACT_BODY: IrDispatch[IrAlternation | None] = IrDispatch(actions=(
    IrAction(IrGroup, IrCallable(_group_extract)),
    IrAction(IrNode, IrCallable(_no_extract)),       # default override
))
```

The hoist factory builds an `IrTransformer` with a single action whose body is an `IrCallable`:

```python
def _hoist_transformer(
    parent_name: str, name_set: set[str]
) -> tuple[IrTransformer, list[IrRule]]:
    helpers: list[IrRule] = []

    def _hoist_body(_d, item, new_children):
        rebuilt = item.rebuild(new_children)
        if rebuilt.quantifier == IrQuantifier(1, 1):
            return rebuilt
        body = _EXTRACT_BODY(rebuilt.atom)
        if body is None:
            return rebuilt
        name = _reserve_helper_name(parent_name, name_set)
        name_set.add(name)
        helpers.append(IrRule(name, body))
        return IrItem(IrRuleRef(name), rebuilt.quantifier)

    return IrTransformer(actions=(IrAction(IrItem, IrCallable(_hoist_body)),)), helpers


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    name_set = {r.name for r in ast.rules}
    all_helpers: list[IrRule] = []
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        t, helpers = _hoist_transformer(rule.name, name_set)
        new_body = t(rule.body)
        all_helpers.extend(helpers)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), all_helpers
```

Recognition is via dispatch table; the only constructed types are the *synthesized* `IrItem(IrRuleRef(name), q)` and `IrRule(name, body)` — pure node creation, irreducible. Quantifier triviality stays a direct attribute check because it's a property of the containing `IrItem`, not the atom.

`_HoistTransformer` is deleted.

### `_PatternAliasVisitor` — stays closed-subclass

Deferred per scope companion §3. Mechanical fixes only: the migrated `IrDispatch` API may force minor signature adjustments (e.g. callers swap `dispatch.visit(node)` for `dispatch(node)`). No behavioural rewrite to action-table form.

### `_IrRepr` in `codegen/model_emitter.py`

Migrates to action-table form using `IrEmitter` — each per-type repr lambda becomes `IrAction(NodeType, IrCallable(...))`. This is mechanical; the closed-subclass version was always a stand-in for "we don't have IrEmitter yet."

## Flavour migration

### `Flavour` becomes `IrEmitter` subclass

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

Per-flavour metadata lives as `ClassVar`s; per-flavour behaviour lives in the `actions` tuple inherited from `IrEmitter`.

### GBNF flavour

```python
_GBNF_ACTIONS: tuple[IrAction, ...] = (
    IrAction(IrLiteral,    IrSeq((IrText('"'), IrCallable(_gbnf_encode_literal), IrText('"')))),
    IrAction(IrCharClass,  IrCallable(_gbnf_charclass)),
    IrAction(IrRuleRef,    IrField("name")),
    IrAction(IrGroup,      IrSeq((IrText("("), IrChild("body"), IrText(")")))),
    IrAction(IrQuantifier, IrCallable(_gbnf_quantifier)),
    IrAction(IrItem,       IrSeq((IrChild("atom"), IrChild("quantifier")))),
    IrAction(IrSequence,   IrJoin(IrChildren("items"), IrText(" "), IrText('""'))),
    IrAction(IrAlternation,IrJoin(IrChildren("arms"), IrText(" | "), IrText(""))),
    IrAction(IrRule,       IrSeq((IrField("name"), IrText(" ::= "), IrChild("body")))),
    IrAction(IrAst,        IrCallable(_gbnf_ast)),
)

class GbnfFlavour(Flavour):
    name = "gbnf"
    extensions = (".gbnf",)
    meta_grammar = GBNF_META_GRAMMAR
    escapes = GbnfEscapes
    line_comment = "#"
    quantifier_symbols = {(1, 1): "", (0, 1): "?", (0, None): "*", (1, None): "+"}
    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier: ...
    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]: ...

GBNF = GbnfFlavour(actions=_GBNF_ACTIONS)
```

`IrCallable` is used for: literal-escape encoding (`_gbnf_encode_literal`), char-class negation prefix (`_gbnf_charclass`), quantifier symbol-table lookup (`_gbnf_quantifier`), AST newline-join (`_gbnf_ast`). Structurally simple cases (`IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`) are pure IrOp.

### ABNF flavour

Mirrors GBNF with:
- Prefix-quantifier ordering on `IrItem`: `IrSeq((IrChild("quantifier"), IrChild("atom")))`.
- Its own `quantifier_symbols` table.
- Its own `_abnf_*` callables for escape encoding and other procedural cases.

`AbnfFlavour` + `ABNF = AbnfFlavour(actions=_ABNF_ACTIONS)` at module scope.

### Consumers

- `base.py` — `to_gbnf()` flips from importing `GbnfEmitter` to calling `GBNF(self.__grammar__...)`. The deliberate runtime→codegen edge documented in CLAUDE.md changes target from `lexic.grammars.gbnf.emitter` to the `GBNF` singleton in `lexic.grammars.gbnf.flavour`.
- `parsing/lark_builder.py` — mechanical fixes only; stays the internal codegen target, not a registered Flavour.
- `codegen/aliases.py`, `codegen/model_emitter.py` — mechanical fixes for `IrDispatch` API changes; closed-subclass visitors stay closed per deferred §3.
- `MetaGrammarParser.for_flavour(GbnfFlavour)` still takes the class. Its only-class-attrs constraint stands.

## File structure

```
src/lexic/
  ir/
    action.py       NEW — IrOp + 9 variants + IrAction
    walk.py         IrDispatch + IrVisitor + IrTransformer + IrEmitter
                    No _CHILDREN / _REBUILD / _DUMP / dump() / visit() / visit_<TypeName>
    derive.py       has_ruleref via singleton _HAS_RULEREF
                    hoist_helpers via factory + _EXTRACT_BODY sub-dispatcher
                    No _RuleRefFinder / _HoistTransformer classes
    emit.py         render_specs(specs, flavour) thin shell
    nodes.py        Quantifier → IrQuantifier rename; otherwise unchanged
    [helpers.py]    Opportunistic deletion if trivially safe (see deferred §9)
  grammars/
    flavour.py      Flavour(IrEmitter, ABC) + metadata ClassVars + parse abstract methods
                    No pre_parse_check
    gbnf/
      flavour.py    GbnfFlavour + GBNF singleton + _GBNF_ACTIONS tuple
      escapes.py · meta_grammar.py
      [emitter.py]  DELETED
    abnf/
      flavour.py    AbnfFlavour + ABNF singleton + _ABNF_ACTIONS tuple
      escapes.py · meta_grammar.py
      [emitter.py]  DELETED
  parsing/
    meta_parser.py    unchanged
    lark_builder.py   unchanged except mechanical fixes
    transformer/      unchanged
  codegen/
    aliases.py        _PatternAliasVisitor stays closed (deferred §3)
    model_emitter.py  _IrRepr migrates to IrEmitter; other closed visitors stay closed
  utils/
    names.py
    [quantifiers.py]  DELETED
  base.py             to_gbnf() flips to GBNF singleton
  compile.py · exceptions.py · parse.py · generate.py
```

## Migration strategy

Single campaign. Full 448-test suite green at every numbered step. Each step independently revertable.

1. **Introduce `ir/action.py`.** `IrOp` ABC + nine canonical variants + `IrAction`. Standalone; no consumers migrated yet. Unit tests cover each variant's `eval` in isolation.

2. **Rewrite `ir/walk.py`.** New `IrDispatch` + `IrVisitor` + `IrTransformer` + `IrEmitter`. Entry/recursion split (`__call__` catches `_Return`, `_walk` recurses). Delete `_CHILDREN`, `_REBUILD`, `_DUMP`, `dump()`, `visit()`, `generic_visit()`, `_combine()`, `visit_<TypeName>` discovery. Apply minimum mechanical fixes to `codegen/aliases.py`, `codegen/model_emitter.py` so they keep compiling.

3. **Migrate `_RuleRefFinder` and `_HoistTransformer`.** Convert to module-level singleton (`_HAS_RULEREF`) and factory (`_hoist_transformer` + `_EXTRACT_BODY`). Delete the closed-subclass declarations.

4. **`Quantifier` → `IrQuantifier`.** Mechanical rename across `nodes.py`, `derive.py`, `parsing/`, `codegen/`, `generate.py`, tests. Pure rename, no behaviour change.

5. **`Flavour` as `IrEmitter`.** Refactor `grammars/flavour.py`: `Flavour(IrEmitter, ABC)` with metadata ClassVars + abstract `parse_quantifier` / `parse_charclass`. Add `render_specs(specs, flavour)` in `ir/emit.py`.

6. **Migrate `GbnfFlavour`.** Build `_GBNF_ACTIONS`. Construct `GBNF = GbnfFlavour(actions=_GBNF_ACTIONS)` at module scope. Delete `grammars/gbnf/emitter.py`.

7. **Migrate `AbnfFlavour`.** Same. Delete `grammars/abnf/emitter.py`.

8. **Migrate consumers.** `base.py` → `GBNF` singleton. Codegen / `lark_builder.py` mechanical adjustments. Delete `utils/quantifiers.py`.

9. **Opportunistic cleanup.** If `ir/helpers.py` is trivially safe to delete at this point, delete it (and its test + export).

10. **Wiki + docs.** Update `.wiki/lexic/architecture.md`, `flavour-system.md`, `ir-shapes.md` for: the substrate, IR-pass-by-action-table convention, IrQuantifier, Flavour-as-IrEmitter, module map shift. Decision entries for P12-strengthened, P13, P14, P15, P16. `log.md` entry. Update CLAUDE.md's two-exceptions wording: first exception's import target flips to the `GBNF` singleton.

## Invariants enforced throughout

- Full test suite green after each numbered step.
- Round-trip fidelity: every existing ground-truth grammar still round-trips byte-equal under its source flavour.
- Layering: no new runtime→codegen import edges beyond the two documented exceptions. The first exception's target changes per step 10.
- No new `# type: ignore` / `# pylint: disable`. The two existing entries in `regex_portable.py` stay as-is.
- `has_ruleref` short-circuit MUST work — verified by test: a deep tree with `IrRuleRef` at depth N is visited only as far as the first hit. Acceptance criterion is performance (no full-tree walk), not just correctness.
- No closed-subclass `IrDispatch` with `visit_<TypeName>` overrides remains in `ir/` after step 3.
- No `IrOp` variant beyond the nine canonical ones is introduced.
- `pre_parse_check` does not appear in `Flavour` or any subclass.

## Risk areas

- **Step 2 is the deepest cut.** `IrDispatch` semantics change for every existing consumer in the same step. Mitigation: if the rewrite is hairier than expected, land it as 2a (introduce new `IrDispatch` alongside old under a different name, migrate consumers one by one) and 2b (rename + delete old). The plan can split this if needed.

- **`IrCallable` discipline.** Easy to reach for the escape hatch on every action. Mitigation: the GBNF and ABNF action tables MUST express structurally simple cases (`IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`) in pure IrOp. `IrCallable` is permitted for `IrLiteral`, `IrCharClass`, `IrQuantifier`, `IrAst`. Any other `IrCallable` use during execution is a flag-for-discussion item.

- **`_Return` exception class.** Must inherit `BaseException`, not `Exception`. Otherwise an `IrCallable` body with a blanket `except Exception:` could swallow it. Test: an `IrCallable` body that catches `Exception` does not affect `IrReturn`'s unwinding.

- **MRO-walk lookup correctness.** A dispatcher loaded with both `IrAction(IrLeaf, body_a)` and `IrAction(IrLiteral, body_b)` must invoke `body_b` for `IrLiteral` and `body_a` for any other leaf. The `_resolve_cache` must also handle the negative case (cached `None` for genuine misses) so the fall-through to `_default` isn't bypassed.

- **`IrAction.target_type` is a `type`, not an `IrNode`.** It must NOT appear in `children()`. `IrComposite` machinery (`_child_attrs` / `_extra_field_names`) renders it as `__str__` metadata without claiming it as a child.

- **Frozen-slot dict mutation.** `_resolve_cache[node_type] = ...` mutates dict *contents* inside a frozen slot — allowed. Slot rebinding (`object.__setattr__(self, "_resolve_cache", new_dict)`) is allowed only inside `__post_init__`.

## Out of scope

Authoritative list: `2026-05-17-slice-b-deferred-work.md`. Brief restatement of the largest items:

- LarkFlavour promotion / `.lark` as user-facing extension — deferred.
- Positional / indexed / negation token-reference syntax + `Flavour.pre_parse_check` hook — deferred. The hook does not exist in this slice.
- Codegen-side closed-subclass visitor migration (`_PatternAliasVisitor` and others inside `codegen/`) — deferred.
- Pure-IrOp expression of stateful passes (`_HoistTransformer`, `_RuleRefFinder` migrate to action tables but keep `IrCallable` bodies where needed) — deferred.
- Hoist elimination — `_HoistTransformer` deletion + inline-group codegen — deferred (§11 of the scope companion).
- New IrOp variants beyond the canonical nine — deferred.
- Self-description bonus features (`PyFlavourCodegenRenderer`, `IrFlavour` text format) — deferred. P13's structural claim is paid for here; the renderers built on top of it are not.

Anti-creep enforcement: see the deferred-work doc's "Anti-creep rules" section.
