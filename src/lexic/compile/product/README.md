# `compile/product` — building a product program

The compile half of the product ABI. `parsing/product/` owns what a program IS
and what executes it; this owns how one is BUILT.

The split is the repo's layering applied to one seam: the engine is a leaf that
reads compiled data, so everything that knows about grammars, reducers,
signatures and targets lives on this side and hands the engine plain tables.

## `lower.py`

Authored operations → flat int-coded tables. Three obligations:

- **Every authored enum becomes an exact `int`.** An `IntEnum` that survived
  would satisfy `isinstance(x, int)` and ride into a runtime table, paying an
  enum lookup on every completion. `verify_exact_ints` catches one afterwards;
  lowering is what stops it happening.
- **One instruction per rule completion.** A rule's completion is one authored
  operation, so it lowers to one `(opcode, operand)` pair and a range of length
  one. That granularity is right because a collection's begin, insert and
  finish belong to *different* rules — the container's and the entry's — not to
  one rule's script.
- **Operands index their own opcode's rows.** An authored operation's fields
  are all lane indices, so the record IS its int row. Rows are pooled per
  opcode and deduplicated; the operand is the row index. Multi-field operations
  stay one instruction and every table stays typed — no catch-all operand array
  widened to `object`.

The type→opcode table is open with a raising default: an operation nobody has
lowered refuses by name at compile time rather than reaching an engine.

It also owns three things the engine must never be handed loosely:

- **The constructor table.** `RecordOp` reaches it at frequent completions, so
  it may hold only binding-owned constructor symbols — the immutable class
  objects a declaration named. Lowering is its only writer and refuses a
  lambda, closure, factory, or a caller who pre-filled the operand record.
- **Statefulness.** Derived from the lowered instructions, not declared: a
  program is stateful exactly when it contains a collection operation.
- **Route specialization.** `lower_routes` turns each authored `RouteTable`
  into a uniform bypass, a singleton equality test, or a dictionary probe by
  actual cardinality. Nothing scans the authored pairs afterwards.

Lowering deliberately does **not** verify. `verify_program` stays one cold gate
that every execution path calls, rather than something a caller can skip by
constructing a program some other way.

## What joins this package later

Signature verification, lower × upper state composition, demand propagation,
bound-product caching, and the `ReductionMorphism` / `GrammarMorphism`
surfaces. Each arrives as its own module — this one does not grow into them.
