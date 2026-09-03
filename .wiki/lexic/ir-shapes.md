# IR Shapes

**When to load:** working with `IrNode` / `IrItem` / `IrAst` / `IrRule`; building action bodies (`IrField`, `IrConcat`, `IrJoin`, `IrCond`, `IrThis`, `IrLambda`); understanding `kind` semantics, hoisting, non-semantic relaxation; understanding the `IrSelf` substrate and the **primitive-node (V2)** model.

See also: [[architecture]], [[field-naming]], [[decisions]]

The IR is the contract between parsers, transformers, codegen, and flavour emitters. Every IR node is callable and participates in dispatch.

## Primitive-node model (V2)

A node **is** its payload. There are NO `.value` / `.items` / `.arms` accessors — use the node directly. `IrType`, `coerce`, the load-bearing `IrNode.__init__`, `IrStrLeaf`, `IrCollection`/`_items_attr`, and the `_str_name`/`_inner_str`/`__str__` cascade are all GONE.

### How a record's fields are derived — and why it is not `__dict__`

`IrNamedTuple.__init_subclass__` reads the class body's annotations with
`annotationlib.get_annotations(cls, format=Format.STRING)`. Two properties
matter and neither is incidental:

**It must not read `cls.__dict__["__annotations__"]`.** Under **PEP 649** a
class body carrying annotations compiles to an `__annotate_func__`, and
`__annotations__` is computed on *access* — so at `__init_subclass__` time
`__dict__` holds nothing to read and every field registers as none. A module
carrying `from __future__ import annotations` opts *out* of 649 and stores a
plain dict eagerly, which is the only reason a `__dict__` read ever appeared to
work: it was never reading annotations, it was reading a side effect of PEP
563. The future import is therefore **irrelevant to correctness** here, and
must stay that way — a record's fields work with or without it.

**`format=STRING` never evaluates.** A forward reference in a field
annotation cannot raise during class creation, which is what makes the
self-referential records (`Spec`, `IrMap[IrStr, "Keep | Spec"]`) definable at
all.

The failure this replaced was silent in a way worth remembering: fields
registering as none does not raise. The record still constructs, `repr` still
looks right, and attribute reads still answer — from the class-level default
rather than from the tuple. `len()` is 0. Every surface a person checks by
hand looks correct.

Two related guarantees, both tested:

- **Surplus positional values raise.** A record given more values than it has
  fields names the count and the fields rather than discarding the extras.
- **A subclass adding no fields keeps its parent's.** `__init_subclass__`
  merges rather than overwrites; a bare `type("Mine", (Num,), {})` has `Num`'s
  fields. (`IrCachingTuple` merges its own bases and dedups, and is unaffected.)

### `IrSelf[Iri, Ir_co]` root

Generic identity root and action-protocol base. `Iri` is the input node type; `Ir_co` the covariant return type (PEP 695 infers covariance since it is return-position only). Supplies:

- `__call__(d, n, nc) -> Self` — identity (PEP 673 `Self`).
- `eval(d, n, nc) -> Ir_co` — action protocol; default delegates to `__call__`.
- `children() -> Sequence` — default empty; `rebuild(new_children) -> Self` — default identity.
- `.bound` / `.bind(other)` — `_bound` is auto-derived from the **last** own type parameter's bound (i.e. `Ir_co`, since `Iri` comes first), or set explicitly. `.bind` widens-or-raises.

- `Cls.ensure(node, what="")` — the **boundary narrow**: returns `node` typed
  as `Cls`, else raises `UnsupportedConstructError`. The class-level sibling
  of `.bind` (which narrows a dispatch result to an instance's `_bound` at
  runtime); `ensure` narrows an untyped value to a named class *statically* —
  `IrMap.ensure(x)` is an `IrMap` to a type checker.

`__init_subclass__` derives `_bound` from the class's OWN last type parameter (never the MRO); an explicit `_bound` ClassVar wins.

**Use `ensure`, never `assert isinstance`, at a boundary.** Several seams
hand a value back wider than the caller can use — a reducer body returns
`IrSelf` because it folds to whatever its declarations produce, and a
document's actual shape is runtime information no signature carries.
Asserting that shape is legitimate; hand-rolling the assert at every seam is
not, and an `assert` is *stripped by `python -O`*, so the check silently
vanishes in optimized mode. `ensure` raises. Nothing is coerced: a value of
the wrong type raises rather than being reinterpreted.

Adding a public method here has a cost worth knowing: every name on
`GrammarModel`'s public surface is a reserved field name, so a grammar rule
called `ensure` mangles to `ensure_` ([[field-naming]]).

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

**`IrAst.non_semantic`** is a **derived property** (not a field) — `frozenset(r.name for r in rules if not r.semantic)`. It is the single source of truth feeding the codegen passes (`lexic.compile.pipeline.passes.relax_non_semantic` — quantifier relaxation) and `model.py`'s `semantic_dump()` filter (via each field's `IrBind.semantic`), and, for a flavour's self-grammar, its `Reducer` noise map (`GBNF_NOISE`/`ABNF_NOISE` are built *from* `GBNF_GRAMMAR.non_semantic`/`ABNF_GRAMMAR.non_semantic`). The name keeps the `@non-semantic` directive vocabulary though the flag's polarity is positive on the rule. `IrAst` needs **no** equality override (the exclusion lives on `IrRule`); plain tuple equality over `(rules, start)` composes `IrRule.__eq__`. `canonical_grammar` (the compile package) applies a directive by reconstructing each named rule with `semantic=False`; the flavours flag their noise rules `semantic=False` individually in their own self-grammar.

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

**`IrMap` joins the walk**: `children()` yields its dyads as fresh `(key, value)` records — constructor-mirroring, so `rebuild(children())` round-trips through `__new__` (duplicate keys still refuse) — and `IrEach` iterates a mapping focus the same way. A dispatch table, a reducer's action map, or any map-shaped value therefore stands under `IrBottomUp`/`IrEach` like any other node. `IrMultiMap` stays a leaf (`children() == ()`), keeping the mutable exception unwalked.

**`IrBottomUp` walks the model layer's concessions.** Models are deliberately not IR-strict — an absent optional is Python `None`, a `models`-mode field a plain `tuple`, payload slots plain strings/classes — and the driver takes each for what it is: a plain tuple is transparent (elements walked; when changed it rebuilds as `IrTuple`, which IS a tuple, so the model field contract holds), everything else non-IR is an opaque leaf never offered to the action table. This is what makes a cross-class model transform (the transpile seam, `ex16`/`ex17`) a plain `IrTypeMap` over model classes: each body receives already-transformed children on `nc`, and each intermediate rebuild threads them through the parent's CHECKED constructor (the spine isinstance, not the exact arm) — a wrong transform refuses with `FieldValidationError` instead of shipping.

## Dispatch (`ir/walk.py`)

`IrDispatch[Iri, Ir_co]` is an `IrCachingTuple` of `(actions, default)` — `actions: IrTypeMap` (not a plain tuple), `_child_attrs = ()` so the dispatcher is never itself walked as a grammar node. Resolution is `actions`' own concrete-first MRO lookup (see above) — a miss falls through to `default`, `IrRaise()` by default. Entry seams: `eval(d, n, nc)` (protocol) and `apply(root)` (façade — catches `IrReturn`, surfaces `.value` or the return node itself when it satisfies the `Ir_co` bound). Presets: `IrVisitor` (default `IrWalk`), `IrTransformer` (default `IrRebuild`), `IrEmitter` (default `IrEmit`).

The find-first idiom: `IrVisitor(actions=IrTypeMap(IrAction(IrRuleRef, IrReturn())))` — `IrReturn()` (defaulting to `IrThis`) surfaces the matched ruleref; a non-match completes the walk and returns `IrNone`. This is how `codegen/binding.py`'s `has_ruleref` works (moved there from the retired `ir/derive.py`).

## `IrLiteral` dual role

`IrLiteral` surfaces in both positions:

- **AST role:** as `IrItem.atom`, the literal string in a rule body; the flavour's `IrAction(IrLiteral, …)` body fires.
- **Constant role:** inside an action algebra (`IrConcat(parts=IrTuple(IrLiteral("("), …))`, `IrJoin(separator=IrLiteral(" | "))`), a baked-in string round-tripped through dispatch unchanged — `IrStr.eval` returns `self`.

Distinguished by `nc`-marker semantics at eval time.

## Addresses and spans (`ir/text/spans.py`)

Where an occurrence stands, and what it covers. An **occurrence** is a value standing somewhere; the spine deliberately cannot tell two equal values apart (a node IS its payload, and equal subtrees are routinely the SAME object — one `Ws` is reached seven times in `{"a": 1, "b": 1}` under `json.gbnf`), so only its place identifies it.

```python
IrStep(field: str, slot: int)      # what the parent calls a part, and where it sits
IrAddress(IrSeq[IrStep])           # the path from the root; .child(field, slot) extends it
IrSpan(start: int, end: int)       # half-open, in CODE UNITS; .of(text) slices it back
IrExtent(address, span)            # emit-side correspondence
IrExtents(IrSeq[IrExtent])         # one emission's, document order, parents first
IrEmission(text: str, extents)     # what `GrammarModel.emit_addressed()` returns
IrOrigin(address, source)          # transform-side: built occurrence ← source occurrence
IrOrigins(IrSeq[IrOrigin])
```

Four rules the family exists to keep, each of which has already been got wrong somewhere:

- **Top-down, positional.** An address is built by the walk that produces it, each step supplied by the parent from its own emission order. It is never recovered from a value and never looked up by equality — `list.index` finds the first EQUAL sibling, which is a different occurrence with the same payload.
- **No share-splice.** A walk producing addresses may not run on an id-memoising driver. `IrBottomUp` transforms a shared object once and splices the result everywhere it appeared (`walk.py`) — right for a transform, wrong for an address, because sharing is the normal case here.
- **Emission order, not declaration order.** Steps follow the parent's `emit_parts` order (item-slot, i.e. document order). `JsonText` declares `(value, ws, ws2)` and emits `ws, value, ws2`; `children()` follows the emission order and `_fields` does not.
- **Code units.** `len` of the emitted string — the only measure that can slice it back. Terminal columns (wide glyphs counted twice) and pixels are consumer projections. Note `ir/text/layout.py`'s width solve also counts code units, and for its own reason: the budget it serves is a linter's line length, counted in characters over emitted files.

`GrammarModel.emit_addressed()` produces the emit-side set and `GrammarModel.occurrence(address)` reads it back — the same `_sub_parts` definition drives both, so the address contract has one definition and two directions. `to_text()` stays its own loop (the hot path pays nothing); a corpus gate pins the two texts to each other.

## The identity walk (`ir/identity.py`)

What a value's graph IS, under **one stated child definition**: a node's children are the node-valued parts it CARRIES — the elements of its field tuple, and, for the map family (whose payload is a table rather than a tuple), its entries, each value under its own key. `field_children` is public so the definition can be checked rather than only stated. Naming it is the point — sharing counted under one definition and reported under another manufactures a delta out of nothing.

```python
IrIdentity(node, reached: int, unspellable: bool)   # one DISTINCT node
IrCensus(IrSeq[IrIdentity])                         # .shared() / .refusals()
census(root) -> IrCensus                            # first-reach order, iterative
```

`reached` counts ARRIVALS — one per edge pointing at the node, plus one for the root — so `sum(reached) == edges + 1` and anything above `1` is sharing. Distinctness is by IDENTITY: two equal `IrLiteral('a')` objects are two entries, which is the same fact `spans.py` exists to survive.

Two consequences of the definition, both deliberate and both gated:

- it drops nothing `_child_attrs` drops: `IrRule.name` is a node, and an identity walk that missed it would undercount;
- it opens the tables. `children()` reports an `IrMapping` as a leaf, because rebuilding a table is not what a transform does — but a dispatch table's whole content is its entries. A flavour's reducer censuses as 272 nodes rather than 5, and a compiled grammar's `fold.bodies` as 115 rather than 1, of which 35 are the `IrLambda(<class>)` constructors that ARE the refusal boundary. Under a tuple-only definition that boundary read as an empty set on every real artefact.

`unspellable` is the refusal boundary: `IrLambda` (the spine's one callable-carrying node), plus any node holding a bare callable that is neither a node nor a class — a class has a name and the notation spells names.

## Equality up to renaming (`ir/grammar/alignment.py`)

`canonicalize` folds spelling but never quotients NAMES, so two grammars differing only in what their rules are called canonicalise to two different ASTs. `align_names(left, right) -> IrAlignment` decides whether they are one grammar anyway, and hands back the transport that proves it:

```python
IrRename(source: str, target: str)     # one pair; dict(renaming) is the table
IrRenaming(IrSeq[IrRename])            # one complete bijection; .renamed(ast) carries a grammar across
IrRenamings(IrSeq[IrRenaming])
IrAlignment(renamings, capped: bool)
```

Both sides are canonicalised first, and the comparison is over the rule SET (a renaming may reorder the canonical rule list, and rule order is not a difference). The search is colour refinement over the rule graph — a rule's colour is its name-blind body plus the colours of the rules it references, refined to a fixpoint over BOTH grammars at once — then candidate bijections consistent with the colouring, each verified by applying it.

**ALL valid bijections are returned.** Two rules with identical bodies admit both pairings; offering them is the no-silent-pick doctrine applied to isomorphism. The enumeration is bounded by `CANDIDATE_CAP` and a run that hit it says so in `capped` rather than passing off a truncated list as complete.

What is NOT decided: language equality. Two grammars describing one language by different factorings do not align (`json.gbnf` vs `json_arr.gbnf` refuses), and an empty alignment says only "no renaming relates these", never "different languages".

## `IrBind` (`ir/bind.py`)

There is no `RuleSpec` anymore. Every generated field carries an `IrBind` in its `Annotated` metadata instead:

```python
IrBind(item: int, mode: str, semantic: bool = True)
```

`item` is the positional index into the rule's single sequence arm (`= the kid slot` in the parse tree — `normalize()` preserves item↔kid positions, so `kids[i] ↔ items[i]`, see [[architecture]]); `mode` is one of `BIND_MODES = ("text", "gtext", "model", "models")` — how the kid at that slot folds into the field value (`text`: terminal atom text; `gtext`: literal-only group text, absent when optional-and-empty; `model`: one sub-model; `models`: a list of sub-models; `span`: the slot's `IrSpan` — WHERE it was consumed rather than what it says); `semantic` is `False` for a structural-noise field (whitespace ref). `IrBind` is a plain `IrNamedTuple`-family record with `_child_attrs = ()` (all three fields are scalar payload), importable by generated modules and readable by `model.py`/the compile package.

**`span` is a fold mode, never a binding one.** `compute_binding` cannot produce it — a generated field is what a rule MEANS, and a position is not — so no model class ever carries one. It exists for a fold that is asking WHERE: templating's raw-span capture binds the same two slots twice, in `text` mode and in `span` mode, so one capture yields both what the entry says and where it said it. Each route serves it from what it already had: the PDA reads the frame offsets it computes the span text from (`pda/runtime/build.py`), and the tree route accumulates them over the leaves `_subtree_text` already walks in order (`_tree_offsets`, `parsing/fold.py`), paid only by a fold that asked (`ModelFold.wants_spans`). A parity gate pins the two routes to each other, because a product that differed by engine would be worse than none.

Sharing, on the tree route: the forest interns nodes, and the first occurrence wins in the offset pass. That is exact for every NON-EMPTY node — a non-empty derivation is chart-keyed by its span, so it cannot be shared across positions — and only zero-width nodes can collide, which is the one case that route cannot separate.

`codegen/binding.py`'s `compute_binding(codegen_grammar)` produces these (one `RuleMap` per rule, `fields: dict[str, IrBind]`); `codegen/model_emitter.py` renders them into `Annotated[<type>, IrBind(...)]` field metadata; `parsing/fold.py`'s `ModelFold` bakes its IR body-table (`IrMap[IrRuleRef, ModelBody]`) to the same plain-data `FieldFold` shape (`(item, mode, name, lo)`), built by `compile.py` — the fold never imports `IrBind`/codegen directly, only the `BIND_MODES` vocabulary.

## `kind` semantics

There is no `RuleSpec.kind` field anymore. `codegen/binding.py`'s `classify_rule(rule)` derives a rule's kind fresh from the codegen grammar (`RuleKind = Literal["sequence", "alternation", "value_str"]`), carried on `RuleMap.kind`:

| `kind` | Body shape | `RuleMap.fields` | Generated class |
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
- `relax_non_semantic(ast)` sets `min=0` on every arm-level ref to a rule named in `ast.non_semantic` (e.g. `ws`). `model.py`'s `semantic_dump()` excludes the corresponding field by reading each `IrBind.semantic` — there is no separate `non_semantic_fields` set anymore.

## Open-set note (rework complete, 2026-07-04)

`codegen/binding.py` and `codegen/passes.py` were first to move their classification/naming/mode logic onto open `IrDispatch`/`IrTypeMap` tables with raising defaults. The remaining closed-set holdouts — `generate.py`'s atom ladder, `codegen/model_emitter.py`'s `_base_field_type`/`_value_str_type`, `codegen/aliases.py`'s `regex_for_*` ladders — have since landed the same treatment: `_GEN_ATOM`+`_Generator`, `_MODEL_TYPE`/`_GTEXT_TYPE`/`_TEXT_TYPE`+`_VALUE_TYPE`, and `_FRAGMENT` respectively, all with raising defaults and the post-canon-dead `IrNot` branches deleted. `_group_union_type` (a ref-arm filter) and `_visit_item`'s recursing group-frame `isinstance` are deliberately not tabled — they're control flow, not atom-type classification. See [[decisions]], [[codegen]], [[field-naming]].

---

## A map yields KEY order, not document order

`IrMap` indexes its dyads into canonical key-sorted order at construction. That
is what makes its views, repr and equality order-stable, and it is the property
the whole map family rests on — but it means **the source sequence is not
retained and cannot be recovered**.

```python
keys = ["version", "model", "added_tokens"]
IrMap(*(IrTuple(IrStr(k), IrInt(i)) for i, k in enumerate(keys))).children()
# yields added_tokens, model, version — sorted, not as spelled
```

This is a **stated product property**, not a leak: a map IS its table. There is
deliberately no ordered reading, because retaining source order would mean
either a second source of truth beside the table or giving up the canonical
order that equality depends on.

The consequence for consumers: **anything walking a reduced value and expecting
to meet entries in the order the document spelled them is wrong.** It is wrong
intermittently, which is worse than always — small maps bucket in an order that
matches the source often enough that a suite of two- and three-key documents
will agree with the false premise throughout. A real document with nine
top-level keys is where it separates.

When two things must be told apart, prefer removing the ambiguity upstream over
resolving it downstream: give each candidate a distinct stand-in and take
exactly one match or refuse, rather than breaking ties by a position the data
does not carry.
