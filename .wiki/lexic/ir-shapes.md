# IR Shapes

**When to load:** working with `IrNode` / `IrItem` / `IrAst` / `IrRule`; building action bodies (`IrField`, `IrConcat`, `IrJoin`, `IrCond`, `IrThis`, `IrCallable`); understanding `kind` semantics, hoisting, non-semantic relaxation; understanding the `IrSelf` substrate and the **primitive-node (V2)** model.

See also: [[architecture]], [[field-naming]], [[decisions]]

The IR is the contract between parsers, transformers, codegen, and flavour emitters. Every IR node is callable and participates in dispatch.

## Primitive-node model (V2)

A node **is** its payload. There are NO `.value` / `.items` / `.arms` accessors — use the node directly. `IrType`, `coerce`, the load-bearing `IrNode.__init__`, `IrStrLeaf`, `IrCollection`/`_items_attr`, and the `_str_name`/`_inner_str`/`__str__` cascade are all GONE.

### `IrSelf[Iri, Ir_co]` root

Generic identity root and action-protocol base. `Iri` is the input node type; `Ir_co` the covariant return type (PEP 695 infers covariance since it is return-position only). Supplies:

- `__call__(d, n, nc) -> Self` — identity (PEP 673 `Self`).
- `eval(d, n, nc) -> Ir_co` — action protocol; default delegates to `__call__`.
- `children() -> Sequence` — default empty; `rebuild(new_children) -> Self` — default identity.
- `.bound` / `.bind(other)` — `_bound` is auto-derived from the **last** own type parameter's bound (i.e. `Ir_co`, since `Iri` comes first), or set explicitly. `.bind` widens-or-raises.

`__init_subclass__` derives `_bound` from the class's OWN last type parameter (never the MRO); an explicit `_bound` ClassVar wins.

### Absence — `IrNone` / `IrNoneType`

`IrNone` is the singleton value of `@final IrNoneType(IrSelf)` — the absence sentinel that replaces `IrNode | None` unions. It IS-A `IrSelf`, so it fits every dispatch slot. Use `IrNoneType` for `isinstance`/annotations, pass bare `IrNone`, compare `x is IrNone`.

### Three tiers — the node IS its payload

```
value-leaves IrScalar(IrLeaf)               IrStr ⇒ IrLiteral/IrCharClass/IrRuleRef; IrInt
variadic     IrTuple[T](IrNode, tuple)       IrSequence, IrAlternation
records      IrComposite (frozen dataclass)  IrItem, IrQuantifier, IrGroup, IrNot, IrRule, IrAst
```

- **`IrScalar(IrLeaf)`** — value-leaf base for scalar-payload leaves (`IrStr`, `IrInt`). Hosts the shared behaviour: self-evaluating `eval` (returns `self`); type-aware `__eq__`/`__ne__` (distinct leaf kinds never compare equal — `IrLiteral("x") != IrRuleRef("x")` — yet a leaf still equals its plain primitive — `IrLiteral("x") == "x"`, `IrInt(5) == 5`); `__hash__` and codegen `__repr__` — all delegating to the primitive via `super()` / `self._bound`. `IrScalar.__new__(*args)` forwards the payload to `str`/`int`, which makes `type[IrScalar]` constructor-callable (used by `IrField.out`) and lets `object.__init__` tolerate the construction arg. (`__eq__`/`__hash__` reach `str`/`int` because no IR base between `IrScalar` and the primitive defines them; `__repr__` can't use `super()` — `IrNode.__repr__` intercepts — so it renders `self._bound(self)!r`.)
- **`IrStr(IrScalar, str)`** / **`IrInt(IrScalar, int)`** — `_bound = str`/`int`, no methods of their own. The node IS the string/int; use it directly (`leaf == "x"`, `IrInt(5) + 1`). A **truth value is `IrInt ∈ {0,1}`** — there is no `IrBool`.
- **`IrTuple[T](IrNode, tuple)`** — `_bound = tuple`. The node IS its children tuple; iterate/index directly (`seq[0]`, `for arm in alt`). Constructor is variadic (`IrTuple(a, b, c)`). `children()` returns `self`; `eval` dispatches each element via `d` and rebuilds the tuple. **`eval` is annotated `-> IrSelf` (not `-> Self`)** so reducer subclasses (`IrAnd`) can override it with a non-tuple result (`IrInt`); for rebuild collections the runtime result is still `type(self)(...)`. (No `[T, R]` two-param generic — the relaxed return is enough.)
- **`IrComposite[Iri, Ir_co]`** — THE dataclass record base (frozen, slots, `repr=False`). The ClassVar `_child_attrs` names the dataclass fields that are dispatched children; `children()` returns them in order, `rebuild` reconstructs positionally via `replace`.

`IrNode[Iri, Ir_co](IrSelf, ABC)` adds `__repr__`-is-codegen: `repr` reproduces the constructor call (`IrLiteral('x')`, `IrRule(name='r', body=IrAlternation())`). No `__str__`.

`IrAtom(IrNode)` is a **non-generic role marker** mixed into atoms by plain inheritance; `IrItem.atom: IrAtom` accepts any subclass. Use `isinstance(x, IrAtom)` (role check), `isinstance(x, IrLeaf)` (structural).

## Grammar AST nodes (`ir/nodes.py`)

Quantifiers travel on `IrItem`, never on leaves.

```python
# str-leaves — the node IS the string
IrLiteral("x")          # IS-A IrStr, IS-A IrAtom
IrCharClass("0-9")      # POSIX-style interior
IrRuleRef("expr")       # rule name

# composites
IrQuantifier(min=1, max=1)          # plain ints; max=None means unbounded
IrItem(atom, quantifier)            # universal wrapper
IrGroup(body: IrAlternation)        # IS-A IrComposite, IS-A IrAtom
IrNot(body: IrAtom)                 # IS-A IrComposite, IS-A IrAtom; negation
IrRule(name: str, body: IrAlternation, semantic: bool = True)   # name plain str
IrAst(rules: IrTuple, start: str)        # children() -> (rules_tuple,)

# variadic collections — construct with *args
IrSequence(*items)      # tuple of IrItem
IrAlternation(*arms)    # tuple of IrSequence
```

**`IrAst.children()` returns `(rules_tuple,)`** — a 1-tuple wrapping the `IrTuple`. Dispatch-based walks are unaffected (they recurse into the wrapping tuple), but code that wants the rules directly iterates `ast.rules`.

**`IrRule.semantic`** (`bool = True`; user polarity ruling 2026-07-03: no negation in the attribute — a rule IS semantic by default) is `False` on a structural-noise rule (whitespace/comments/delimiters). It is **compile-channel metadata**, not grammar structure (like a source location), so `IrRule.__eq__`/`__hash__` exclude it — that exclusion is what lets the self-hosting fixpoint `parse_grammar(flavour.apply(GRAMMAR), flavour) == GRAMMAR` hold: a freshly parsed rule is `semantic=True` while the authored self-grammar flags its noise rules `semantic=False`.

**`IrAst.non_semantic`** is a **derived property** (not a field) — `frozenset(r.name for r in rules if not r.semantic)`. It is the single source of truth feeding `derive_specs` (quantifier relaxation + `semantic_dump` filter) and, for a flavour's self-grammar, its `Reducer` noise map (`GBNF_NOISE`/`ABNF_NOISE` are built *from* `GBNF_GRAMMAR.non_semantic`/`ABNF_GRAMMAR.non_semantic`). The name keeps the `@non-semantic` directive vocabulary though the flag's polarity is positive on the rule. `IrAst` needs **no** equality override (the exclusion lives on `IrRule`); plain tuple equality over `(rules, start)` composes `IrRule.__eq__`. `compile_grammar` applies a directive by reconstructing each named rule with `semantic=False`; the flavours flag their noise rules `semantic=False` individually.

**Record repr omits trailing default-valued fields** (`IrNamedTuple.__repr__`, 2026-07-03): fields are dropped from the end while each equals its declared default, stopping at the first non-default (or a field with no default). Still valid codegen — `IrItem(IrLiteral('a'), IrQuantifier(1,1))` reprs as `IrItem(IrLiteral('a'))`; `IrRule('ws', <body>, False)` keeps the flag; `IrRule('r', <body>)` (semantic default) omits it.

## Action-algebra nodes (`ir/action.py`)

| Node | `Ir_co` | Eval |
|---|---|---|
| `IrField(name, out=IrStr)` | `IrScalar` | `self.out(getattr(n, name))` — `out: type[IrScalar]` (open, cast-free; `IrField("min", IrInt)` reads an int). No enumerated union, not generic. |
| `IrOp(value)` | `IrInt` | operator leaf — the node IS its operator string (`IrOp(">")`, **no `Cmp` enum**); applies `_OPS[self]` (an `operator` builtin) to the two operands in `nc` → `IrInt(0/1)` |
| `IrCompare(left, op, right)` | `IrInt` | evals `left`/`right`, hands them to `op` (an `IrOp`) as `nc` → `IrInt(0/1)`; operands typed `IrSelf` |
| `IrAnd(*operands)` | `IrInt` | `IrTuple[IrSelf]` subclass; short-circuit conjunction → `IrInt(1)` (all truthy / empty) or `IrInt(0)` |
| `IrCallable(handler)` | any | `handler(d, n, nc)` — procedural escape hatch |
| `IrChild(name)` | any | hybrid: `nc[idx]` if `nc` truthy, else lazy `d.eval(...)` on the named child |
| `IrChildren()` | any | hybrid: `nc` if truthy, else dispatch all of `n.children()`. **No name arg** (R2). |
| `IrConcat(parts)` | `IrStr` | `bound().join(p.eval(d, n, nc) for p in parts)`; `parts: IrTuple` |
| `IrJoin(parts, separator, empty)` | `IrStr` | render `parts`; `bound(sep).join(rendered)` or `empty.eval(...)` |
| `IrCond(test, then_op, else_op)` | any | `(then_op if test.eval(d, n, nc) else else_op).eval(...)`; `test: IrSelf` (any predicate node, e.g. `IrCompare`/`IrAnd`) |
| `IrThis()` | any | returns the dispatched node `n` (identity body — declarative `lambda d, n, nc: n`) |
| `IrReturn(value=IrThis(), lazy_eval=True)` | any | lazy-evaluates its body against `(d, n, nc)` and re-raises the result via `_Return`; `IrReturn()` surfaces the matched node (find-first). With `lazy_eval=False` or a non-`IrSelf` value, raises `self` carrying the static value. |
| `IrAction(target_type, body)` | any | `body.eval(d, n, nc)` |

`IrConcat`/`IrJoin` are `IrComposite` holding `parts: IrTuple` (NOT `IrTuple` subclasses — the dual generic lineage breaks `bound`). All action operators are `IrComposite`; only the grammar AST collections (`IrSequence`, `IrAlternation`) are `IrTuple` subclasses.

### Default bodies

| Node | Use |
|---|---|
| `IrPass` | No-op → `IrNone`. |
| `IrWalk` | Visit children for side effects; honours `nc`. Default for `IrVisitor`. |
| `IrRaise(exc_type, message)` | Raise on unmatched. Default base for `IrDispatch`. |
| `IrEmit` | `IrLiteral(str(n))`. Default for `IrEmitter` (`_bound = IrLiteral`). |
| `IrRebuild` | Walk + reconstruct (identity on a leaf). Default for `IrTransformer`. |

## Dispatch (`ir/walk.py`)

`IrDispatch[Iri, Ir_co]` is an `IrComposite` whose `actions` tuple is the table (a plain field, NOT a dispatched child). Resolution is concrete-first MRO walk over `actions`, memoised in `_resolve_cache`; unmatched types fall to `default`. Entry seams: `eval(d, n, nc)` (protocol) and `apply(root)` (façade — catches `IrReturn`, surfaces `.value`). Presets: `IrVisitor` (default `IrWalk`), `IrTransformer` (default `IrRebuild`), `IrEmitter` (default `IrEmit`).

The find-first idiom: `IrVisitor(actions=(IrAction(IrRuleRef, IrReturn()),))` — `IrReturn()` (defaulting to `IrThis`) surfaces the matched ruleref; a non-match completes the walk and returns `IrNone`. This is how `derive.has_ruleref` works.

## `IrLiteral` dual role

`IrLiteral` surfaces in both positions:

- **AST role:** as `IrItem.atom`, the literal string in a rule body; the flavour's `IrAction(IrLiteral, …)` body fires.
- **Constant role:** inside an action algebra (`IrConcat(parts=IrTuple(IrLiteral("("), …))`, `IrJoin(separator=IrLiteral(" | "))`), a baked-in string round-tripped through dispatch unchanged — `IrStr.eval` returns `self`.

Distinguished by `nc`-marker semantics at eval time.

## `RuleSpec` (`ir/spec.py`)

```python
RuleSpec(
    rule_name: str,
    class_name: str,
    parent_class_name: str,
    kind: Literal["sequence", "alternation", "value_str"],
    items: list[IrItem | IrAlternation],
    field_map: dict[str, int],
    non_semantic_fields: frozenset[str],
)
```

Carries `to_ir_rule()` — converts the spec back into an `IrRule` for flavour emission. (`RuleSpec.items` is a plain `list` — unrelated to any node accessor.)

## `kind` semantics

| `kind` | `items` content | `field_map` | Generated class |
|---|---|---|---|
| `"sequence"` | `IrItem`s in grammar order | populated | concrete; fields from atoms |
| `"alternation"` | `[IrItem(IrRuleRef(arm), …)]` per arm | empty | abstract (ABC); subclasses are arms |
| `"value_str"` | `IrItem`s for emitters only | empty | `value: str` field |

**Multi-arm `value_str`:** `items = [IrAlternation(...)]`. Emitters dispatch on `isinstance`.

## Invariants

- Unquantified `IrLiteral` (`IrItem(IrLiteral(…), IrQuantifier(1, 1))`) → never in `field_map`.
- Quantified literals (`IrItem(IrLiteral("-"), IrQuantifier(0, 1))`) → produce a field via Tier-2 naming.
- `IrAlternation` items → never in `field_map`.
- `topo_sort` guarantees the start rule is first.
- Dispatch tables must have an explicit default — base `IrDispatch.default = IrRaise()`. See [[error-vocabulary]].
- Flavour dataclasses must NOT use `init=False` — it suppresses the generated `__init__`, silently resolving `actions` to the empty `IrDispatch` default.

## Hoisting (`ir/derive.py`)

`hoist_helpers(ast)` rewrites quantified `IrGroup` nodes containing rulerefs into synthetic helper rules (`<parent>-item`, `<parent>-item2`, …). Pure-literal groups are left in place regardless of quantifier — they become regex patterns.

## Non-semantic relaxation

Rules listed in `ast.non_semantic` (e.g. `ws`) get their `quantifier.min` relaxed to 0 in every referencing spec. Field names for these refs are recorded in `non_semantic_fields`; `GrammarModel.semantic_dump()` excludes them. (`derive_specs(ast)` reads `ast.non_semantic` — the former `non_semantic_rules` parameter is gone.)

## Open-set note (deferred rework)

IR consumers (`derive`, `codegen`, `parsing`, `generate`) still carry closed-set `isinstance` ladders and `dict[type, …]` tables. A separate, deferred effort re-homes node-intrinsic logic onto the nodes and consumer policy onto open `IrDispatch` tables. Until then those ladders are legacy, not the target. See [[decisions]].
