# Current bug report — shipped ambiguity defects

Four defects in the **currently shipped** engine, found while building the
ambiguity witnesses. None is deferred work and none is introduced by the
target-shaped effort: all four reproduce against the tip of
`src/` with no prototype involved. They are recorded here rather than in
`TBD_after.md` because that file is for work re-evaluated *after* the
architecture lands, and these are wrong answers being returned today.

The first three were verified through the public API and the engine's own
machinery, with the first two additionally checked through `build` /
`same_value`. The fourth is in the shipped `DERIVATIONS` reader over a real
kernel chart. My first
characterisation of the first two was wrong; what follows is the corrected,
reproduced version.

---

## BUG 1 — a nullable quantified item is silently decided, and `parse()` returns one of two different models

**Severity: high.** `CompiledGrammar.parse(text)` with no resolver returns a
model without refusing, on an input whose derivations build **different**
`GrammarModel`s. `src/lexic/compile/artifact.py:252` documents `resolve=None`
as "refuse ambiguity"; it does not refuse here.

**This is not the resolver.** No resolver is supplied in the reproduction. The
split/arm-choice classification decides — before any resolver could be
consulted — that this is not an ambiguity at all.

### Reproduction

```python
G = 'root ::= pad list\nlist ::= gap*\ngap ::= item?\nitem ::= "a"\npad ::= "x"\n'
compiled = compile_text(G)
compiled.parse("x", cores=1)        # -> Root(Pad('x'), List(()))   no refusal
```

The same span, the other family, through `compiled.fold.apply` — the engine's
real model fold:

```text
baseline                        Root(Pad('x'), List(()))
flipped (one family at one pt)  Root(Pad('x'), List((Gap(),)))
same_value(baseline, flipped)   False      <- the engine's OWN observability test
is_arm_choice(bucket, ...)      False      <- so another_meaning skips the point
another_meaning(...)            None       <- "every derivation means the same thing"
```

An empty `list` versus a `list` holding one empty `Gap()` is a difference a
consumer reads straight off the public model. Round-tripping still holds (both
emit `"x"`), which is why this has gone unnoticed: `parse(text).to_text() ==
text` is satisfied by either answer.

### Mechanism

`normalize.QUANTIFIER_PREFIXES` (`src/lexic/parsing/earley/normalize.py:69-78`)
deliberately marks `__rep_*` and `__opt_*` arms as **not** authored choices:
"they encode different extents of one item." `is_arm_choice`
(`src/lexic/parsing/earley/kernel/tables/splits.py:119-129`) therefore reads
families naming one arm over different spans as a *split*, and
`another_meaning` skips splits with the comment "A SPLIT has a defined answer —
the first slot owns the text".

That reasoning is correct for a **non-nullable** item, where a different extent
means different text consumed. For a **nullable** item two different extents
consume the *same* text and build different models, so "the first slot owns the
text" decides nothing a consumer cannot see.

`ambiguity.py:11-13` anticipates the benign version — "two adjacent nullable
slots split a gap two ways to the same end. Refusing those refuses valid input
for a difference no consumer can observe." The distinction to draw is that a
nullable slot inside a **repetition** does not fold to the same end: it changes
the item count.

### Blast radius

- Any grammar with a variable-count quantifier over a nullable item. `gap*`
  over `item?` is the minimal witness; the established combinations are
  detailed below.
- The authored grammar really is infinitely ambiguous on `"x"` — one derivation
  per empty `gap` — so this is not a desugaring defect.
  `__rep_1 ::= "" | gap __rep_1` is the correct language-preserving shape.
- **Independent of everything Prototype 11/12 settled.** P11's interaction
  defect needs two points to interact; this is a single flip missed outright,
  because the point never presents itself as an arm choice. The §A mechanism in
  `PROTOTYPE_12.md` does not fix it, and `cyclic_meaning` does not reach it —
  the chart reports acyclic, so the zero-width cycle its binding-time analysis
  flags is never instantiated.

### Established scope

`proto/nullable_quantifier_ambiguity.py` now forces the public, PDA, and Earley
routes separately and evaluates alternate families with the real model fold.
All three routes silently choose one model for nullable atoms under `*`, `+`,
`{0,2}`, and `{1,2}`; the same holds for a grouped nullable atom and a directly
empty rule. An exact-count `{2}` has no count choice and is unaffected.

`?` is affected differently. Before `lift_optional_nullables`, its absent and
present families build different models. The lift removes the family and makes
the present model win, while the raw Earley default chooses the absent model.
The current lift therefore hides the ambiguity rather than resolving it under
the public root-value contract.

The general structural predicate is: **a quantifier admits more than one count
and its atom is nullable**. Such a helper family represents different
occurrence counts, not two allocations of consumed text, and cannot inherit the
ordinary split exemption. Whether it refuses still depends on the complete
target meanings: a parent may discard the count difference.

The 15 canonical ground-truth grammars contain zero such sites, but this is not
the parser-stage census. `@non-semantic` relaxation manufactures 71 optional
nullable `ws` references across six codegen grammars, and `ws` is a bound model
field. Removing `lift_optional_nullables` while continuing to recognize that
relaxed shape would therefore expose real alternative models throughout
ordinary JSON.

The clean implementation boundary is separate: recognize the pre-relaxation
`armed` grammar, while retaining the relaxed grammar only for binding,
synthesis, and constructor ergonomics. On all six exposed fixtures, the
current lifted relaxed grammar equals the armed grammar; parsing armed with the
existing relaxed fold returns the current public model through Earley and the
gated product. A token-bound artefact needs a separately concretized armed
parse moment. Authored quantified-nullable sites remain semantic families;
only compiler-manufactured constructor optionality stays out of recognition.
The correctness fix remains subject to the standing isolated parse-performance
gate and the user's final approval of any measured regression.

Owners: `parsing/earley/kernel/tables/splits.py` (`is_arm_choice`),
`parsing/earley/kernel/forest/support/ambiguity.py` (`another_meaning`),
`parsing/earley/normalize.py` (`QUANTIFIER_PREFIXES`).

---

## BUG 2 — `ambiguity_points` is only correct on an already-expanded chart

**Severity: latent.** `ambiguity_points(kernel, root)` returns an incomplete
answer — often zero — on a finished kernel whose Leo links have not been
expanded, and the correct answer on the **same kernel object** once something
forces expansion. It is an order-dependent read of a structure the caller is
never told it must prepare.

### Reproduction

```python
G = ('doc ::= entry+\nentry ::= key "=" value ";"\n'
     'value ::= num1 | num2\nnum1 ::= [0-9]\nnum2 ::= [0-9]\n'
     'key ::= [a-z] [a-z0-9]*\n')
kernel = Kernel(compile_tables(normalize(compile_text(G).grammar),
                               tier_for(4096)), "version=3;size=7;", True).run()
root = accept_handle(kernel)

len(ambiguity_points(kernel, root))   # 0   -- kernel.st.leo_links already holds 8
FastTree(kernel, {}).build(root)      # forces lazy Leo expansion
len(ambiguity_points(kernel, root))   # 2   -- same kernel object, no reparse
```

The links exist in both reads; the walk does not expand them. The wrong answer
is the one available *before* the forest is materialised — exactly when a
caller asking "is this ambiguous?" would want to ask.

### Blast radius

- **Shipped `parse` is not known to be affected.** `another_meaning` builds a
  `FastTree` before consulting the points, so the shipped path happens to
  satisfy the precondition by accident of ordering.
- Anything consulting the points as a standalone predicate — a fast pre-check,
  a refusal gate, a diagnostic — inherits a silent false negative. This was
  found because a Prototype 12 witness did exactly that and reported "no
  ambiguity" for several iterations.
- It matters at **§8** specifically: rewiring the ambiguity contract onto the
  product's typed root meaning invites a cheap pre-check, which is precisely
  the call that would read the points before materialising the forest.

### Fix direction

`ambiguity_points` must own complete readout: expand every deferred Leo key
before walking the links. An implicit precondition is rejected because the
call is specifically the public internal predicate future fast paths will ask
before constructing a tree. `proto/nullable_quantifier_ambiguity.py` supplies
the external reference helper and reproduces `0 -> 2` on the same kernel.

Owners: `parsing/earley/kernel/forest/support/ambiguity.py`,
`parsing/earley/kernel/loop/leo.py` (`expand_leo`).

---

## BUG 3 — PDA islands and Earley expose different resolver pairs and refusals

**Severity: public-contract divergence.** The same grammar, document, and
resolver receive an island-rooted pair through the predictive route and a
document-rooted pair through Earley. The refusal messages differ as well. This
violates `Resolver`'s contract that both engines given the same pair answer the
same way.

### Reproduction

`proto/resolver_pair.py` forces both shipped routes for `"(xy)z"` and asserts
the uncontaminated baseline:

```text
pda     pair_root=t     refusal="parsing: island 't' derives the same text two ways that mean different things — supply a resolver to choose between them"
earley  pair_root=root  refusal="parsing: ambiguous input — two derivations that mean different things; supply a resolver to choose between them"
```

Both routes preserve pair order: the first element is the derivation already
chosen and the second is the first differing derivation. Scope is the defect.
A context-sensitive resolver can observe which engine ran and can make the
public result diverge.

### Fix direction

One resolver scope must govern both engines. The design proves that complete
document pairs are constructible without retaining a shadow model on the
unambiguous path, and that is the selected public scope. Complete-document
scope requires occurrence-addressed
multi-island splicing; the fused PDA path requires one cold Earley recognition
only after root inequality and an actual resolver call. Refusal wording must be
shared by the selected public gate.

Owners: `parsing/pda/runtime/islands.py` (`island_parse`),
`parsing/earley/engine.py`, and `parsing/products.py`, against the resolver
contract in `parsing/earley/kernel/forest/support/ambiguity.py`.

---

## BUG 4 — forest enumeration truncates a suspended shared handle as a nullable cycle

**Severity: high on the resolver/derivation path.** A zero-width completed node
consumed at two slots of one derivation is shared, not recursively cyclic. The
shipped `DERIVATIONS` reader nevertheless substitutes an empty prefix at the
second consumption and emits malformed, incomplete derivations.

### Reproduction

`proto/shared_occurrence_ambiguity.py` recognizes the real duplicate-slot and
pending-frame shapes, then invokes the shipped forest enumerator:

```text
duplicate-slot  shipped_derivations=2  shipped_wellformed_meanings=0
                shipped_malformed_derivations=2  grammar_meanings=4
pending-frame   shipped_derivations=2  shipped_wellformed_meanings=0
                shipped_malformed_derivations=2  grammar_meanings=4
```

The arm-shared control returns four well-formed derivations and the expected
two meanings.

### Mechanism

`ForestCtx.open` records every handle whose prefix generator is suspended.
`PrefixSource` treats any re-entry into that set as a nullable cycle and emits
one empty prefix. During the lazy trampolined product, the first consumption of
a shared zero-width handle can still be suspended when the second slot requests
the same handle. The guard therefore confuses ordinary sharing with recursive
re-entry and constructs a node with no children under a rule whose operation
requires one.

### Fix direction

Cycle termination must distinguish a recursive derivation-path re-entry from a
second grammatical consumption of a suspended replayable stream. Preserve real
nullable-cycle termination while allowing the shared handle's derivations to
replay at each occurrence. Pin both failing shapes and the arm-shared control
before resolver-tree materialization depends on `DERIVATIONS`.

Owner: `parsing/earley/kernel/forest/forest.py` (`ForestCtx`, `PrefixSource`,
`ChildDerivs`, and `DERIVATIONS`).

---

## Status

None is fixed. No source file was touched: `git diff -- src tests` is empty.
All four reproduce against the current tip; the prototypes only drive and
compare shipped machinery.
