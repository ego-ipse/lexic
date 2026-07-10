# IR Shapes

**When to load:** working with `IrNode` / `IrItem` / `IrAst` / `IrRule`; building action bodies (`IrField`, `IrConcat`, `IrJoin`, `IrCond`, `IrThis`, `IrLambda`); understanding `kind` semantics, hoisting, non-semantic relaxation; understanding the `IrSelf` substrate and the **primitive-node (V2)** model.

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
value-leaves IrScalar(IrLeaf)                IrStr ⇒ IrLiteral/IrCharClass/IrRuleRef; IrInt
variadic     IrTuple[*Ts]/IrSeq[T](tuple)     IrSequence, IrAlternation
records      IrNamedTuple[*Ts](tuple)         IrItem, IrQuantifier, IrRule, IrAst
```

There is no `IrComposite`/frozen-dataclass tier anymore — fixed-arity records are `IrNamedTuple` subclasses (see below); the dataclass-record shape retired with the primitive-node migration.

- **`IrScalar(IrLeaf)`** — value-leaf base for scalar-payload leaves (`IrStr`, `IrInt`). Hosts the shared behaviour: self-evaluating `eval` (returns `self`); type-aware `__eq__`/`__ne__` (distinct leaf kinds never compare equal — `IrLiteral("x") != IrRuleRef("x")` — yet a leaf still equals its plain primitive — `IrLiteral("x") == "x"`, `IrInt(5) == 5`); `__hash__` and codegen `__repr__` — all delegating to the primitive via `super()` / `self._bound`. `IrScalar.__new__(*args)` forwards the payload to `str`/`int`, which makes `type[IrScalar]` constructor-callable (used by `IrField.out`) and lets `object.__init__` tolerate the construction arg. (`__eq__`/`__hash__` reach `str`/`int` because no IR base between `IrScalar` and the primitive defines them; `__repr__` can't use `super()` — `IrNode.__repr__` intercepts — so it renders `self._bound(self)!r`.)
- **`IrStr(IrScalar, str)`** / **`IrInt(IrScalar, int)`** — `_bound = str`/`int`, no methods of their own. The node IS the string/int; use it directly (`leaf == "x"`, `IrInt(5) + 1`). A **truth value is `IrInt ∈ {0,1}`** — there is no `IrBool`.
- **`IrTuple[*Ts](IrNode, tuple)`** — heterogeneous base, `_bound = tuple`. The node IS its children tuple; iterate/index directly (`seq[0]`, `for arm in alt`). Constructor is variadic (`IrTuple(a, b, c)`). `children()` returns `self`; `eval` dispatches each element via `d` and rebuilds the tuple. **`eval` is annotated `-> IrSelf` (not `-> Self`)** so reducer subclasses (`IrAnd`) can override it with a non-tuple result (`IrInt`); for rebuild collections the runtime result is still `type(self)(...)`. `IrSeq[T]` names a **homogeneous** specialisation over a bounded `TypeVar` (`IrSequence(IrSeq["IrItem"])` rejects any non-`IrItem` element; `IrTuple` itself, over `*Ts`, cannot express that bound).
- **`IrNamedTuple[*Ts](IrTuple)`** — fixed-arity **named** tuple, `dataclass_transform`-decorated: the node IS the tuple (no separate per-field storage — a tuple subtype cannot carry non-empty `__slots__`); each class-body annotation is a field in declaration order, and `__init_subclass__` installs a `property(itemgetter(i))` accessor per field so `rec.field` and `rec[i]` are the same read. `__new__` builds the tuple positionally/by-keyword/with declared defaults (`_field_defaults`). The ClassVar `_child_attrs` names which fields are dispatched children (defaults to every field; a record with scalar-only payload, e.g. `IrBounds`, declares an empty `_child_attrs`) — no `_items_attr`, `IrCollection` is gone. `children()` returns just the `_child_attrs` fields; `rebuild(new_children)` splices replacements into those slots and reconstructs via the class constructor. `IrCachingTuple[*Ts](IrNamedTuple)` is a further specialisation whose `Field(default=...)`/`Field(default_factory=...)` field values resolve to a **fresh per-instance value** (deep-copied or factory-called) instead of one object shared across every instance — used for dispatcher/transformer state (`IrDispatch`'s `actions`/`default`, `_HoistTransformer`'s `helpers`/`name_set`).

`IrNode[Iri, Ir_co](IrSelf, ABC)` adds `__repr__`-is-codegen: `repr` reproduces the constructor call (`IrLiteral('x')`, `IrRule('r', IrAlternation())`). No `__str__`.

`IrAtom(IrNode)` is a **non-generic role marker** mixed into atoms by plain inheritance; `IrItem.atom: IrAtom` accepts any subclass. Use `isinstance(x, IrAtom)` (role check), `isinstance(x, IrLeaf)` (structural).

## Grammar AST nodes (`ir/nodes.py`)

Quantifiers travel on `IrItem`, never on leaves.

```python
# str-leaves — the node IS the string
IrLiteral("x")          # IS-A IrStr, IS-A IrAtom
IrCharClass(IrChr("0"), IrRange(IrChr("1"), IrChr("9")))  # elements are IrChr/IrRange, not a raw string
IrRuleRef("expr")       # rule name

# records — IrNamedTuple subclasses
IrQuantifier(lo=1, hi=1)             # plain ints; hi=IrNone means unbounded
IrItem(atom, quantifier)             # universal wrapper
IrRule(name: str, body: IrAlternation, semantic: bool = True)   # name plain str
IrAst(rules: IrSeq[IrRule], start: str)   # children() -> (rules_tuple,)

# variadic collections — construct with *args
IrSequence(*items)      # tuple of IrItem
IrAlternation(*arms)    # tuple of IrSequence; an inline "(...)" group is just
                        # an IrAlternation used directly as an IrItem.atom —
                        # there is no separate IrGroup type
```

`IrNot` (negation, `[^...]`) lives in `ir/operators.py`, not `ir/nodes.py` — it is `class IrNot(MonadicOp)`, `MonadicOp(IrOpNode, IrTuple[IrSelf])`: a single-element **variadic-tuple** wrapper (`IrNot(charclass)[0]` is the negated atom), not a record. `IrOp(IrStr)` (also `operators.py`) is the infix-operator leaf used by `IrCompare` — the node IS its operator string (`IrOp(">")`), **no `Cmp` enum**.

Authoring coercion widens `__new__` on `IrSequence`/`IrAlternation`/`IrItem`/`IrRule` so a bare atom/item/sequence lifts to the wrapping shape: `IrSequence(atom)` → wraps to `IrItem(atom)`; `IrAlternation(item_or_atom)` → wraps via `IrSequence`; `IrItem(bare_sequence)` → wraps to `IrAlternation(seq)` (so a quantified inline group need not be spelled `IrItem(IrAlternation(IrSequence(...)))`); `IrRule(name, non_alternation_body)` → wraps up to a single-arm `IrAlternation`. Unknown types (e.g. mid-transform values) pass through unchanged. All of this is idempotent on already-canonical input.

**`IrAst.children()` returns `(rules_tuple,)`** — a 1-tuple wrapping the `IrSeq`. Dispatch-based walks are unaffected (they recurse into the wrapping tuple), but code that wants the rules directly iterates `ast.rules`.

**`IrRule.semantic`** (`bool = True`; user polarity ruling 2026-07-03: no negation in the attribute — a rule IS semantic by default) is `False` on a structural-noise rule (whitespace/comments/delimiters). It is **compile-channel metadata**, not grammar structure (like a source location), so `IrRule.__eq__`/`__hash__` exclude it — that exclusion is what lets the self-hosting fixpoint `parse_grammar(flavour.apply(GRAMMAR), flavour) == GRAMMAR` hold: a freshly parsed rule is `semantic=True` while the authored self-grammar flags its noise rules `semantic=False`.

**`IrAst.non_semantic`** is a **derived property** (not a field) — `frozenset(r.name for r in rules if not r.semantic)`. It is the single source of truth feeding the codegen passes (`lexic.codegen.passes.relax_non_semantic` — quantifier relaxation) and `base.py`'s `semantic_dump()` filter (via each field's `IrBind.semantic`), and, for a flavour's self-grammar, its `Reducer` noise map (`GBNF_NOISE`/`ABNF_NOISE` are built *from* `GBNF_GRAMMAR.non_semantic`/`ABNF_GRAMMAR.non_semantic`). The name keeps the `@non-semantic` directive vocabulary though the flag's polarity is positive on the rule. `IrAst` needs **no** equality override (the exclusion lives on `IrRule`); plain tuple equality over `(rules, start)` composes `IrRule.__eq__`. `canonical_grammar` (`compile.py`) applies a directive by reconstructing each named rule with `semantic=False`; the flavours flag their noise rules `semantic=False` individually in their own self-grammar.

**Record repr omits trailing default-valued fields** (`IrNamedTuple.__repr__`, 2026-07-03): fields are dropped from the end while each equals its declared default, stopping at the first non-default (or a field with no default). Still valid codegen — `IrItem(IrLiteral('a'), IrQuantifier(1,1))` reprs as `IrItem(IrLiteral('a'))`; `IrRule('ws', <body>, False)` keeps the flag; `IrRule('r', <body>)` (semantic default) omits it.

## Action-algebra nodes (`ir/action.py`)

| Node | `Ir_co` | Eval |
|---|---|---|
| `IrField(name, out=IrStr)` | `IrScalar` | `self.out(getattr(n, name))` — `out: type[IrScalar]` (open, cast-free; `IrField("min", IrInt)` reads an int). No enumerated union, not generic. |
| `IrCompare(left, op, right)` | `IrInt` | evals `left`/`right`, hands them to `op` (an `IrOp`, `ir/operators.py`) as `nc` → `IrInt(0/1)`; operands typed `IrSelf` |
| `IrAnd(*operands)` | `IrInt` | `IrSeq[IrSelf]` subclass; short-circuit conjunction → `IrInt(1)` (all truthy / empty) or `IrInt(0)` |
| `IrLambda(handler)` | any | `handler(d, n, nc)` — procedural escape hatch (lives in `ir/base.py`, not `action.py`; there is no `IrCallable` anymore) |
| `IrChild(name)` | any | hybrid: `nc[idx]` if `nc` truthy, else lazy `d.eval(...)` on the named child |
| `IrChildren()` | any | hybrid: `nc` if truthy, else dispatch all of `n.children()`. No name arg. |
| `IrConcat(parts)` | `IrStr` | `bound().join(p.eval(d, n, nc) for p in parts)`; `parts: IrTuple` |
| `IrJoin(parts, separator, empty)` | `IrStr` | render `parts`; `bound(sep).join(rendered)` or `empty.eval(...)` |
| `IrCond(test, then_op, else_op)` | any | `(then_op if test.eval(d, n, nc) else else_op).eval(...)`; `test: IrSelf` (any predicate node, e.g. `IrCompare`/`IrAnd`) |
| `IrThis()` | any | returns the dispatched node `n` (identity body — declarative `lambda d, n, nc: n`) |
| `IrReturn(value=IrThis(), lazy_eval=True)` | any | lazy-evaluates its body against `(d, n, nc)` and re-raises the result via `_Return`; `IrReturn()` surfaces the matched node (find-first). With `lazy_eval=False` or a non-`IrSelf` value, raises `self` carrying the static value. |
| `IrAction(target_type, body)` | any | `body.eval(d, n, nc)` |

`IrConcat`/`IrJoin` hold `parts: IrTuple` as a plain-record field (NOT `IrTuple` subclasses themselves — the dual generic lineage breaks `bound`). Only the grammar AST collections (`IrSequence`, `IrAlternation`) and `IrAnd` are `IrTuple`/`IrSeq` subclasses in their own right.

### Default bodies

| Node | Use |
|---|---|
| `IrPass` | No-op → `IrNone`. |
| `IrWalk` | Visit children for side effects; honours `nc`. Default for `IrVisitor`. |
| `IrRaise(exc_type, message)` | Raise on unmatched. Default base for `IrDispatch`. |
| `IrEmit` | `IrLiteral(str(n))`. Default for `IrEmitter` (`_bound = IrLiteral`). |
| `IrRebuild` | Walk + reconstruct (identity on a leaf). Default for `IrTransformer`. |

## Mapping nodes (`ir/mapping.py`)

`IrMapping[K, V, R](IrLeaf)` is the common ancestor of the map family — owns a plain `_table: dict`, the frozen container surface (`__getitem__`/`__contains__`/`get`/`keys`/`values`/`items`/`__iter__`/`__repr__`), and structural equality. `IrMap[K, V: IrSelf](IrMapping[K, V, V])` is the immutable dispatch base: `resolve(n)` looks up `n`'s value (falling back to the `IR_DEFAULT` sentinel key, else raising `IrKeyError`), `eval` resolves then evaluates. `IrTypeMap[Ir_co](IrMap[type, IrSelf])` is the type-keyed specialisation `IrDispatch.actions` uses: `resolve` tries the exact `type(n)` first, then walks `t.__mro__` concrete-first, then `IR_DEFAULT` — **no cache, no memoisation**, every resolution is a live dict/MRO walk (kept off the hot path by the exact-type fast path). `IrMultiMap[K, V](IrMapping[K, V, Sequence[V]])` is the one deliberately **mutable** exception (identity equality, `mm += (k, v)` files a bucket in O(1), `mm[k]` returns the live bucket never a copy) — used only by the Earley engine's internal per-column waiting index, never walked/emitted/reduced as a tree.

## Dispatch (`ir/walk.py`)

`IrDispatch[Iri, Ir_co]` is an `IrCachingTuple` of `(actions, default)` — `actions: IrTypeMap` (not a plain tuple), `_child_attrs = ()` so the dispatcher is never itself walked as a grammar node. Resolution is `actions`' own concrete-first MRO lookup (see above) — a miss falls through to `default`, `IrRaise()` by default. Entry seams: `eval(d, n, nc)` (protocol) and `apply(root)` (façade — catches `IrReturn`, surfaces `.value` or the return node itself when it satisfies the `Ir_co` bound). Presets: `IrVisitor` (default `IrWalk`), `IrTransformer` (default `IrRebuild`), `IrEmitter` (default `IrEmit`).

The find-first idiom: `IrVisitor(actions=IrTypeMap(IrAction(IrRuleRef, IrReturn())))` — `IrReturn()` (defaulting to `IrThis`) surfaces the matched ruleref; a non-match completes the walk and returns `IrNone`. This is how `codegen/binding.py`'s `has_ruleref` works (moved there from the retired `ir/derive.py`).

## `IrLiteral` dual role

`IrLiteral` surfaces in both positions:

- **AST role:** as `IrItem.atom`, the literal string in a rule body; the flavour's `IrAction(IrLiteral, …)` body fires.
- **Constant role:** inside an action algebra (`IrConcat(parts=IrTuple(IrLiteral("("), …))`, `IrJoin(separator=IrLiteral(" | "))`), a baked-in string round-tripped through dispatch unchanged — `IrStr.eval` returns `self`.

Distinguished by `nc`-marker semantics at eval time.

## `IrBind` (`ir/bind.py`)

There is no `RuleSpec` anymore. Every generated field carries an `IrBind` in its `Annotated` metadata instead:

```python
IrBind(item: int, mode: str, semantic: bool = True)
```

`item` is the positional index into the rule's single sequence arm (`= the kid slot` in the parse tree — `normalize()` preserves item↔kid positions, so `kids[i] ↔ items[i]`, see [[architecture]]); `mode` is one of `BIND_MODES = ("text", "gtext", "model", "models")` — how the kid at that slot folds into the field value (`text`: terminal atom text; `gtext`: literal-only group text, absent when optional-and-empty; `model`: one sub-model; `models`: a list of sub-models); `semantic` is `False` for a structural-noise field (whitespace ref). `IrBind` is a plain `IrNamedTuple`-family record with `_child_attrs = ()` (all three fields are scalar payload), importable by generated modules and readable by `base.py`/`compile.py` without touching `lexic.codegen`.

`codegen/binding.py`'s `compute_binding(codegen_grammar)` produces these (one `RuleBinding` per rule, `fields: dict[str, IrBind]`); `codegen/model_emitter.py` renders them into `Annotated[<type>, IrBind(...)]` field metadata; `parsing/fold.py`'s `ModelFold` bakes its IR body-table (`IrMap[IrRuleRef, ModelBody]`) to the same plain-data `FieldFold` shape (`(item, mode, name, lo)`), built by `compile.py` — the fold never imports `IrBind`/pydantic/codegen directly, only the `BIND_MODES` vocabulary.

## `kind` semantics

There is no `RuleSpec.kind` field anymore. `codegen/binding.py`'s `classify_rule(rule)` derives a rule's kind fresh from the codegen grammar (`RuleKind = Literal["sequence", "alternation", "value_str"]`), carried on `RuleBinding.kind`:

| `kind` | Body shape | `RuleBinding.fields` | Generated class |
|---|---|---|---|
| `"value_str"` | no `IrRuleRef` anywhere in the body | empty (implicit `value` field, no `IrBind`) | concrete; `value: <pattern type>` |
| `"alternation"` | more than one non-empty arm remains after `hoist_arms` | empty | abstract (ABC); each arm's target rule is a subclass |
| `"sequence"` | one non-empty arm | populated (`bind_fields` over the arm) | concrete; fields from the arm's items |

**Multi-arm `value_str`:** a pure-literal alternation (every arm a single unquantified `IrLiteral`) becomes a `Literal[...]` field type in the emitter (`_value_str_type`), not a class hierarchy.

## Invariants

- Unquantified `IrLiteral` (`IrItem(IrLiteral(…), IrQuantifier(1, 1))`) → never bound to a field (`_is_structural_literal`).
- Quantified literals (`IrItem(IrLiteral("-"), IrQuantifier(0, 1))`) → produce a field via Tier-2 naming (`_literal_token`), never Tier-3 positional.
- `IrAst.non_semantic` derives the rule's `semantic=False` flag from the flavour's own noise declarations or the `@non-semantic` directive — never a hardcoded rule-name string in generic code.
- `ir/order.py`'s `RuleOrder` guarantees the start rule is first — `by_refs`/`order_by_refs` (ref-edge policy, canonicaliser's rule order) and `ordered_parents_first` (parent-edge policy, codegen emission order — a class always follows its inheritance parent).
- Dispatch tables must have an explicit default — base `IrDispatch.default = IrRaise()`. See [[error-vocabulary]].
- Flavour dataclasses must NOT use `init=False` — it suppresses the generated `__init__`, silently resolving `actions` to the empty `IrDispatch` default.

## Canonicalization (`ir/canonical.py`)

`canonicalize(ast) -> IrAst` is a language-preserving normal form, the mandatory second stage of `compile.py`'s `canonical_grammar` (right after `parse_grammar`, before directive/semantic-flag binding). It rewrites: one-member charclass → `IrLiteral`; alternation whose arms all derive single chars (literal/charclass/range) → one merged `IrCharClass`; adjacent single-char literal runs → one multi-char `IrLiteral`; `IrNot(charclass)` → positive `IrRange` spans over the Unicode complement (`IrCharClass.complement()`); redundant single-arm/single-item unquantified group → inlined atom (and a quantified one pushes its quantifier onto the inner atom); charclass normal form (members deduped, ranges coalesced, sorted by codepoint); empty-literal (`IrLiteral('')`) item elimination (epsilon — an engine precondition, since the Earley engine cannot parse a grammar containing an empty-literal item at all); rule names + refs folded to lowercase/`_`→`-` (`fold_name`; a post-fold collision between distinct rules raises `UnsupportedConstructError`); and canonical rule order (`ir/order.py`'s `RuleOrder.by_refs` — start first, then first-reference BFS order, unreferenced rules last alphabetically). The headline fixpoint this buys: `canonicalize(parse(json.gbnf)) == canonicalize(parse(json.abnf)) == JSON_GRAMMAR` — two flavours describing the same language converge on the same canonical `IrAst`.

The arm-merge (`_merge_arms`) is **interval-native**: it collects each mergeable arm's `(lo,hi)` cover via `IrCharClass.intervals()` and rebuilds the fused class via `IrCharClass.from_intervals(spans)` — never through `members()`. This matters because rewrite 4's `[^…]` complement spans ~1.1M code points; the old points-based merge materialised one `IrChr` per point (≈900 ms on `json.gbnf`), the interval path is ~3.8 ms. `IrCharClass` member/complement math is intrinsic to the node: `intervals()` (sorted disjoint cover), `from_intervals(spans)` (coalesce + build, already `normalized()`-form), `members()` (per-point enumeration — kept for small-class consumers/tests, **not** for Unicode-scale use), plus `normalized()`/`complement()`/`sample()`. All interval sort+merge lives once in `IrCharClass._coalesce`.

## Hoisting and non-semantic relaxation (`codegen/passes.py`)

These moved out of the retired `ir/derive.py` into grammar→grammar passes over the *canonical* grammar, composed as `build_codegen_grammar = relax_non_semantic(hoist_arms(hoist_groups(ast)))`:

- `hoist_groups(ast)` rewrites quantified ref-bearing groups (an `IrAlternation` atom containing an `IrRuleRef` anywhere) into synthetic helper rules (`<parent>-item`, `<parent>-item2`, …). Pure-literal groups are left in place regardless of quantifier — they become regex patterns.
- `hoist_arms(ast)` hoists every non-empty alternation arm that isn't already a single unit ruleref into a named `<rule>-arm<N>` sequence rule, restoring the "every non-empty alternation arm is a single unit ruleref" premise `codegen/binding.py`'s parent inference and `parsing/fold.py`'s positional fold both rest on. Empty arms stay in place (a zero-kid match discriminates them).
- `relax_non_semantic(ast)` sets `min=0` on every arm-level ref to a rule named in `ast.non_semantic` (e.g. `ws`). `base.py`'s `semantic_dump()` excludes the corresponding field by reading each `IrBind.semantic` — there is no separate `non_semantic_fields` set anymore.

## Open-set note (rework complete, 2026-07-04)

`codegen/binding.py` and `codegen/passes.py` were first to move their classification/naming/mode logic onto open `IrDispatch`/`IrTypeMap` tables with raising defaults. The remaining closed-set holdouts — `generate.py`'s atom ladder, `codegen/model_emitter.py`'s `_base_field_type`/`_value_str_type`, `codegen/aliases.py`'s `regex_for_*` ladders — have since landed the same treatment: `_GEN_ATOM`+`_Generator`, `_MODEL_TYPE`/`_GTEXT_TYPE`/`_TEXT_TYPE`+`_VALUE_TYPE`, and `_FRAGMENT` respectively, all with raising defaults and the post-canon-dead `IrNot` branches deleted. `_group_union_type` (a ref-arm filter) and `_visit_item`'s recursing group-frame `isinstance` are deliberately not tabled — they're control flow, not atom-type classification. See [[decisions]], [[codegen]], [[field-naming]].
