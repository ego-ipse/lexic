# `compile/pipeline` — grammar → classes

The compile chain's back half: three `IrAst → IrAst` passes, a binding view,
and a runtime `type()` build. Everything here consumes the canonical `IrAst`
`canonical_grammar()` produced and ends in the in-memory class set a
`CompiledGrammar` carries — no source emit, no file write.

## `passes.py` — the codegen passes

`build_codegen_grammar(ast)` applies three language-preserving passes in
order, producing **THE codegen grammar** — the one `IrAst` every class's
`__grammar__` and every field's slot is computed against:

- `hoist_groups` — a quantified ref-bearing inline group becomes a named
  helper rule (the positional fold needs every collection slot to be a ref);
- `hoist_arms` — every non-trivial alternation arm becomes its own
  `<rule>-arm<N>` rule, restoring the single-sequence-arm premise;
- `relax_non_semantic` — refs to `semantic=False` rules get `min=0`, so
  structural noise never blocks an instance parse.

`normalize()` later replaces items in place, so `kids[i] ↔ items[i]` holds
between the engine's parse trees and this grammar — the fold is positional,
with no wrapper rules and no name protocol.

## `binding.py` — the binding view

`compute_binding(codegen_grammar)` returns one `RuleBinding(rule_name,
class_name, parent_class_names, kind, fields)` per rule, parents first.
`classify_rule` derives `kind` fresh (`value_str` / `alternation` /
`sequence`); `bind_fields` names fields through the three-tier cascade
(rule-ref name → pattern library → positional) with the defaults-last
partition and trailing-`_` reserved-name mangling. The module also owns the
open supplied-class contract (`field_kwargs` / `check_supplied_class`) —
a caller may supply its own class for a rule, checked against the binding's
field-name kwargs.

## `synthesis.py` — runtime class synthesis

`synthesize(codegen_grammar, binding, stem)` builds each class with
`type(class_name, bases, ns)`: `__grammar__` (the class's own rule) and
`__binds__` (item slot → `(field, IrBind)`) written directly into the
namespace, `__module__`/`__qualname__` set explicitly, MI bases in binding
order. No annotation resolution at runtime — the record spine reads
`__binds__`.

See the package `README.md` for where this sits in the chain.
