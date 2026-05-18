# Slice B — IrAction/IrOp substrate + Flavour-as-IrEmitter

**Date:** 2026-05-18
**Status:** Draft.
**Scope companion:** `2026-05-17-slice-b-deferred-work.md` — authoritative list of what is deliberately out of this slice.
**Supersedes:** `2026-05-17-slice-b-substrate-and-flavour-as-emitter-design.md` — a prior draft that overcommitted on mechanism (pre-recurse hook, sentinel short-circuit). Where the two conflict, this one wins.
**Implementation plan:** to be written next.

## Architectural principles added in this slice

**P10. Intrinsic data lives on the node.** Per-type structural shape — `children()`, `rebuild()`, `__str__`, `__repr__` — belongs on the IR node type, not in central registries.

**P11. String output is an `IrEmitter`.** Any flavour-controlled walk that yields a string is an `IrEmitter` instance loaded with actions. `FlavourEmitter` and per-flavour emitter subclasses go away.

**P12. IR is open; behaviour is data.** Adding behaviour for a new IR node type is adding an `IrAction` to a table, not subclassing a dispatcher. No production pass within this slice's scope is a closed `IrDispatch` subclass with `visit_<TypeName>` overrides. (Closed-subclass visitors inside `codegen/` and `parsing/transformer/` stay closed per scope-companion §3 / §4 — mechanical fixes only.)

**P13. The IR describes the IR.** `IrAction` and every `IrOp` variant are `IrNode` subclasses. `IrDispatch` (and its presets `IrTransformer` / `IrVisitor` / `IrEmitter` / `Flavour`) are `IrNode` subclasses. They inherit `children()` / `rebuild()` / `__str__` / `__repr__` mechanically from `IrCollection` / `IrComposite`.

**P14. `IrDispatch` does not bound its result type.** `IrDispatch` is generic on `_T`. Each preset pins `_T` (`IrVisitor: None`, `IrTransformer: IrNode`, `IrEmitter: str`). A dispatcher with no matching action returns the preset default for the dispatched node; a dispatcher carrying actions whose bodies produce different concrete types is duck-typed in the Python sense.

**P15. Action `target_type` participates in the type hierarchy.** Action lookup walks `type(node).__mro__` concrete-first. An `IrAction` keyed on an abstract base (`IrLeaf`, `IrStructure`, `IrOp`, even `IrNode`) matches every subclass. A user-supplied `IrAction(IrNode, …)` is therefore a per-instance default-override that wins over the preset default.

**P16. Short-circuit is intrinsic to `IrReturn`, not to the dispatcher.** Evaluating an `IrReturn(value)` op raises a control-flow exception that unwinds the recursion. The dispatcher's entry catches it once at the top. There is no `pre_recurse` hook, no `_SKIP_RECURSION` sentinel, no engine inspection of return values. A leaf doesn't recurse because `children()` is empty; `IrReturn` returns because it raises. Both behaviours are intrinsic to the thing that has them — *nomen est omen*.

## Substrate

### `IrAction` and `IrOp` — `src/lexic/ir/action.py`

`IrOp[_T]` is generic on `_T`, an `IrNode` subclass. Concrete variants either pin `_T` (`IrText: IrOp[str]`) or re-parameterize (`IrReturn[_T]`, `IrCond[_T]`, `IrCallable[_T]`).

Canonical inventory — nine variants:

| Op | `_T` | What it does |
|---|---|---|
| `IrReturn[_T](value)` | `_T` | Raises a control-flow exception carrying `value`. Unwinds to the dispatcher's entry. |
| `IrChild(name)` | result of dispatching that child | Returns `new_children[i]` where `i = type(node)._child_attrs.index(name)`. Fixed-arity. |
| `IrChildren(name)` | tuple of child results | Asserts `name == type(node)._items_attr`; returns the full `new_children` tuple. Variable-arity. |
| `IrSeq(parts)` | `str` | Evaluates parts in order; returns `"".join(str(...))` of results. Emit-side primitive. |
| `IrText(text)` | `str` | Literal `text`. |
| `IrField(name)` | `str` | `str(getattr(node, name))` — non-IrNode attribute on the dispatched node. |
| `IrCond[_T](field, then, else)` | `_T` | Truthy-field branch. |
| `IrJoin(children_op, sep, empty)` | `str` | `sep.text.join(...)` of `children_op`'s result tuple; or `empty.text` if the tuple is empty. |
| `IrCallable[_T](handler)` | `_T` | Escape hatch. `handler(dispatch, node, new_children) -> _T`. |

`IrAction(IrComposite["IrOp"])` carries `target_type: type` (rendered as `__str__` metadata, not a child) and `body: IrOp` (its one child, via `_child_attrs = ("body",)`).

All op variants and `IrAction`: `@dataclass(frozen=True, slots=True, repr=False)`. `IrCallable` is additionally `eq=False, hash=False` because callables don't compare structurally.

### `IrDispatch` — `src/lexic/ir/walk.py`

`IrDispatch(IrCollection["IrAction"], Generic[_T])`. Instantiable directly (not an ABC). `children()` is the actions tuple. `_items_attr = "actions"`. Frozen, slotted.

**Behaviour.** Calling `dispatcher(node)`:

1. Recurse into `node.children()`, building a `new_children` tuple by dispatching each child.
2. Resolve the matching action by walking `type(node).__mro__` concrete-first, scanning `self.actions`. The MRO walk is memoized per dispatcher instance.
3. If an action matches, evaluate its body against `(self, node, new_children)` and return the result.
4. Otherwise, return the preset default for `(node, new_children)`.

**Skip-recursion.** `IrReturn.eval` raises a `_Return` exception (`BaseException` subclass — `Exception` would risk swallowing in `IrCallable` bodies that do `except Exception:`). The exception unwinds through every recursive call until the dispatcher's entry catches it once and returns the carried value. Internal recursion intentionally does not catch; this is one paragraph of implementation, not a design concept.

### Presets

- `IrVisitor(IrDispatch[None])` — preset default: `None`.
- `IrTransformer(IrDispatch[IrNode])` — preset default: `node.rebuild(new_children)` if any child differs from the corresponding `node.children()` entry, else `node`. Identity transformer when given no actions.
- `IrEmitter(IrDispatch[str])` — preset default: `str(node)` if `self.actions` is empty (canonical-form fallthrough); `raise UnsupportedConstructError` if non-empty (closed-world flavour saw an unhandled type).

All three are concrete subclasses, instantiable with an `actions=` tuple.

## IR-internal pass migrations

### `has_ruleref`

```python
_HAS_RULEREF = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn(True)),))

@cache
def has_ruleref(node: IrNode) -> bool:
    return bool(_HAS_RULEREF(node))
```

Module-level singleton; one action. The first `IrRuleRef` reached raises `_Return(True)`; the rest of the subtree is never visited. `_RuleRefFinder` is deleted.

### Hoist

`IrAtom` stays as `IrLeaf | IrGroup` (`TypeAlias`). Recognition lives in a `derive.py`-internal sub-dispatcher; an `IrAction(IrNode, …)` provides the "no extraction" fallthrough:

```python
_EXTRACT_BODY: IrDispatch[IrAlternation | None] = IrDispatch(actions=(
    IrAction(IrGroup, IrCallable(_group_extract)),
    IrAction(IrNode,  IrCallable(_no_extract)),
))
```

A future hoistable atom type registers an action in `_EXTRACT_BODY`; the surrounding pass needs no change. Open-set.

The hoist transformer becomes a factory returning an `IrTransformer` with a single action whose body is an `IrCallable`. Inside that body: `rebuilt = item.rebuild(new_children)`; check the quantifier directly (it's a property of the *containing* `IrItem`, not the atom); ask `_EXTRACT_BODY(rebuilt.atom)` for a body to extract. If `None`, return `rebuilt`. Otherwise allocate a helper name, append `IrRule(name, body)` to a closure-captured helpers list, and return `IrItem(IrRuleRef(name), rebuilt.quantifier)`.

The only typed construction in the body is the synthesized `IrItem(IrRuleRef, q)` and helper `IrRule` — pure node creation, not classification.

`_HoistTransformer` is deleted.

### Other passes

- `_PatternAliasVisitor` (`codegen/aliases.py`) — stays closed-subclass per scope-companion §3. Mechanical fixes only.
- `_IrRepr` (`codegen/model_emitter.py`) — migrates to `IrEmitter` with action-table form. The closed-subclass version was always a stand-in for "no `IrEmitter` yet."

## Flavour migration

`Flavour` becomes `IrEmitter` subclass:

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

Per-flavour metadata is `ClassVar`s; per-flavour behaviour is the `actions` tuple inherited from `IrEmitter`. Per-flavour modules build the tuple at module scope and export a singleton.

### GBNF action tuple — the structural cases

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
GBNF = GbnfFlavour(actions=_GBNF_ACTIONS)
```

`IrCallable` is permitted for: literal-escape encoding, char-class negation prefix, quantifier symbol-table lookup, AST newline-join + trailing newline. The structurally simple cases (`IrRuleRef`, `IrGroup`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`) are pure IrOp — this is the discipline that proves the substrate.

### ABNF

Mirrors GBNF with prefix-quantifier ordering on `IrItem` (`IrSeq((IrChild("quantifier"), IrChild("atom")))`), its own quantifier-symbols table, and its own per-flavour `IrCallable` bodies. `ABNF = AbnfFlavour(actions=_ABNF_ACTIONS)` at module scope.

### Consumers

- `base.py`: `to_gbnf()` flips from importing `GbnfEmitter` to calling the `GBNF` singleton. CLAUDE.md's first runtime→codegen exception's import target changes from `lexic.grammars.gbnf.emitter` to the `GBNF` singleton in `lexic.grammars.gbnf.flavour`.
- `parsing/lark_builder.py`: mechanical fixes only. Stays the internal codegen target; not a registered Flavour.
- `codegen/`: mechanical fixes for any `IrDispatch` API change; closed-subclass visitors stay closed per scope-companion §3.
- `MetaGrammarParser.for_flavour(GbnfFlavour)`: still takes the class. Its class-attrs-only constraint stands.

## Other in-scope work

- `Quantifier` → `IrQuantifier` rename across `nodes.py`, `derive.py`, `parsing/`, `codegen/`, `generate.py`, tests. Pure rename, separate step for blame clarity.
- Delete `FlavourEmitter`, `GbnfEmitter`, `AbnfEmitter`, `utils/quantifiers.py`.
- Opportunistic deletion of `ir/helpers.py` if trivially safe (scope-companion §9).

## File structure after the slice

```
src/lexic/
  ir/
    action.py       NEW — IrOp + 9 variants + IrAction
    walk.py         IrDispatch + IrVisitor + IrTransformer + IrEmitter
                    No _CHILDREN / _REBUILD / _DUMP / dump() / visit_<TypeName>
    derive.py       has_ruleref via singleton _HAS_RULEREF
                    hoist_helpers via factory + _EXTRACT_BODY sub-dispatcher
                    No _RuleRefFinder / _HoistTransformer classes
    emit.py         render_specs(specs, flavour) — thin shell
    nodes.py        Quantifier → IrQuantifier; otherwise unchanged
    [helpers.py]    Opportunistic deletion if trivially safe
  grammars/
    flavour.py      Flavour(IrEmitter, ABC) + metadata ClassVars + abstract parse methods
                    No pre_parse_check
    gbnf/
      flavour.py    GbnfFlavour + GBNF singleton + _GBNF_ACTIONS
      [emitter.py]  DELETED
    abnf/
      flavour.py    AbnfFlavour + ABNF singleton + _ABNF_ACTIONS
      [emitter.py]  DELETED
  parsing/
    lark_builder.py     mechanical fixes only
    meta_parser.py · transformer/    unchanged
  codegen/
    aliases.py          _PatternAliasVisitor stays closed (deferred §3)
    model_emitter.py    _IrRepr migrates to IrEmitter; other closed visitors stay closed
  utils/
    [quantifiers.py]    DELETED
  base.py               to_gbnf() flips to GBNF singleton
```

## Migration strategy

Single campaign. Test suite green at every numbered step. Each step independently revertable.

1. Introduce `ir/action.py` — nine canonical `IrOp` variants + `IrAction`. Standalone, no consumers yet. Unit tests cover each variant's eval semantics.
2. Rewrite `ir/walk.py` — new `IrDispatch` + three presets. Apply minimum mechanical fixes to `codegen/aliases.py` and `codegen/model_emitter.py` so they keep compiling.
3. Migrate `_RuleRefFinder` and `_HoistTransformer` to the substrate (singleton `_HAS_RULEREF`; factory + `_EXTRACT_BODY` for hoist). Delete the closed-subclass declarations.
4. `Quantifier` → `IrQuantifier` rename.
5. `Flavour` becomes `IrEmitter`. Add `render_specs(specs, flavour)` in `ir/emit.py`.
6. Migrate `GbnfFlavour` — build `_GBNF_ACTIONS`, construct `GBNF` singleton. Delete `gbnf/emitter.py`.
7. Migrate `AbnfFlavour` — same. Delete `abnf/emitter.py`.
8. Migrate consumers — `base.py`, `lark_builder.py`. Delete `utils/quantifiers.py`.
9. Opportunistic cleanup — `ir/helpers.py` if trivially safe.
10. Wiki + CLAUDE.md updates: P12-strengthened, P13, P14, P15, P16; substrate; IR-pass-by-action-table convention; IrQuantifier; Flavour-as-IrEmitter; module map shift; `log.md` entry.

## Invariants enforced throughout

- Full test suite green after each numbered step.
- Round-trip fidelity: every ground-truth grammar still round-trips byte-equal under its source flavour.
- Layering: no new runtime→codegen import edges beyond the two documented exceptions. The first exception's target changes per step 10.
- No new `# type: ignore` / `# pylint: disable`. The two existing entries in `regex_portable.py` stay as-is.
- `has_ruleref` short-circuit MUST work — verified by a test that constructs a tree with `IrRuleRef` at depth N and asserts visit count, not just truthiness. Performance regression here is not acceptable.
- No closed-subclass `IrDispatch` with `visit_<TypeName>` overrides remains in `ir/` after step 3.
- No `IrOp` variant beyond the nine canonical ones is introduced.
- `pre_parse_check` does not appear in `Flavour` or any subclass.

## Risk areas

- **Step 2 is the deepest cut.** `IrDispatch` semantics change for every existing consumer in the same step. If the rewrite is hairier than expected, the plan may split it (2a introduce new dispatcher under a temporary name, migrate consumers one by one; 2b rename + delete old). The spec doesn't pre-commit.
- **`IrCallable` discipline.** Easy to reach for the escape hatch on every action. GBNF and ABNF action tables MUST express the structurally simple cases in pure IrOp; `IrCallable` is permitted only for the four documented per-flavour cases. Any other `IrCallable` use is a flag-for-discussion item, not silent acceptance.
- **`_Return` must inherit `BaseException`.** Tests assert that an `IrCallable` body wrapping its work in `except Exception:` does not swallow an `IrReturn` raised by inner ops.
- **MRO lookup correctness.** A dispatcher loaded with both `IrAction(IrLeaf, body_a)` and `IrAction(IrLiteral, body_b)` must invoke `body_b` for `IrLiteral` and `body_a` for any other leaf. The resolve cache must also memoize negative hits so fall-through to the preset default isn't bypassed.
- **`IrAction.target_type` is a `type`, not an `IrNode`.** It must not appear in `children()`. `IrComposite`'s extra-fields machinery renders it as `__str__` metadata.

## Out of scope

Authoritative list: `2026-05-17-slice-b-deferred-work.md`. Headline items:

- LarkFlavour promotion / `.lark` as user-facing extension — deferred.
- Positional / indexed / negation token-reference syntax + `Flavour.pre_parse_check` — deferred.
- Codegen-side closed-subclass visitor migration — deferred (§3).
- Pure-IrOp expression of stateful passes — deferred (§5). `_HoistTransformer`'s body stays `IrCallable` in this slice.
- Hoist elimination — `_HoistTransformer` deletion + inline-group codegen — deferred (§11).
- New IrOp variants beyond the canonical nine — deferred.
- Self-description bonus features (`PyFlavourCodegenRenderer`, `IrFlavour` text format) — deferred. P13's structural claim is paid for here; the renderers on top of it are not.
