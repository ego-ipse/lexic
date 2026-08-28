# Prototype report — target-shaped products

**Date:** 2026-08-27  
**Tree:** branch `targeter`, source baseline `0faa7289`; all prototype code is
outside `src`.

## Questions tested

The prototypes test the two unresolved public-surface questions from
`REVIEW_1.md` and the type-feasibility gate in `TODO.md` §1:

- whether beginner selection and authored advanced morphisms can use one real
  target channel;
- whether omitted/default and supplied-target reduction preserve exact result
  inference;
- whether target binding is cached once and only the selected product runs;
- whether one honest carrier type survives PDA frames, Earley meanings,
  transactions, fragments, and a result-only bound runner;
- whether builders require carrier erasure or per-value wrappers;
- whether the current shipped reducer action vocabulary fits the proposed
  completion ABI;
- whether authored enum names may leak into flattened runtime opcodes.

## Artifacts and gates

- `proto/product_types.py` exercises real `CompiledGrammar`, `Reducer`,
  synthesized `GrammarModel`, `IrSelf`, and `IrTokenizer` classes.
- `proto/reducer_coverage.py` inventories and flat-lowers the expression-node
  classes reached by the shipped GBNF, ABNF, EBNF, and JSON reducers.
- `proto/opcode_cost.py` alternates plain-int, byte-identical control, leaked
  `IntEnum`, and in-loop enum-member rows in one process using CPU time.

The repository Pyright environment reports zero errors, warnings, or
information messages for all three files. The executable proof covers:

- native, GBNF, ABNF, and EBNF JSON compilations, whose canonical grammars are
  equal;
- refusal when the JSON signature is bound to unrelated arithmetic EBNF;
- recursive Python JSON values, nested occurrence-owned builders, speculative
  rollback, duplicate-set rollback, discarded island state, isolated Earley
  state, and typed fragment joining;
- decoded routing of `"model"` and `"m\\u006fdel"` to one route, plus one
  uniform extension route for dynamic keys;
- real synthesized `GrammarModel` values through the generic state/meaning/
  fragment records;
- a tokenizer-specific accumulator carrier finalized once into a real
  `IrTokenizer`;
- two calls through one target causing one target-program bind and no default-
  product bind.

The structural reducer inventory currently produces 174 GBNF, 162 ABNF, 98
EBNF, and 44 JSON postfix instructions. This proves closed class coverage only;
it does not prove the semantics or speed of the eventual expression
interpreter.

The opcode measurement over 12,000,000 comparisons produced:

| Row | Minimum process CPU |
|---|---:|
| lowered plain `int` | 0.262245325 s |
| byte-identical plain-`int` control | 0.262872491 s |
| stored `IntEnum` compared to `int` | 0.332624212 s |
| stored `IntEnum` compared to `Op.MEMBER` | 0.506861693 s |

The control difference is 0.24%. A leaked enum instance cost 26.8%; enum-member
lookup/comparison cost 93.3%. Authored records may use enums, but lowering must
write plain integers into every paid runtime table.

## Design rulings supported by the prototype

### Carrier and builder state

`Carry | BuilderHandle` is rejected. It widens every semantic slot, requires a
handle/value check on the value path, and is not honest for an unrestricted
target whose carrier could overlap the handle type.

Semantic frames and tables contain only `Carry`. Sequence and mapping handles
occupy separate typed frame lanes and index occurrence-owned builder arrays in
`ParseState[Carry]`. No semantic value is wrapped. A collection finish turns
its builder contents into `Carry`; only then can the value enter a parent,
Earley meaning, island result, or fragment.

The concrete morphism retains `TypedBoundProduct[Carry, Result]`; the internal
result-only `BoundProduct[Result]` ABC hides `Carry` only after binding. This
type-checks without erasure, casts, suppressions, or an empty catch-all
protocol. It is the compile/artifact seam behind public `reduce`, not another
user execution method.

### Two lowering layers, not two runtime products

The proposed collection/completion records do not by themselves cover real
reducer bodies. The common product therefore needs two compile-time lowering
layers:

1. a typed expression program which preserves a reducer's action algebra when
   the selected product requires those semantics, notably the default IR
   product; and
2. target completion/accumulation operations produced after a semantic
   signature and upper schema have fused those expressions into direct target
   events.

They are alternative rule lowerings inside one `ProductProgram`, not an
expression evaluation followed by target conversion. A specialized Python or
tokenizer rule must not run the default IR expression and then map its result.
Each contextual rule has one completion range.

Authored sequence and mapping operations are separate begin, append/insert,
and finish record types. A discriminator record with fields ignored on two of
three branches is rejected. Authored enums lower to plain integer opcodes and
capture modes before entering PDA/Earley tables.

### Public surface and binding

The beginner declaration is:

```python
fields = select({"version": KEEP, "model": {"type": KEEP}})
values = compiled.reduce(text, reducer, into=fields, cores=cores)
```

`select(...)` returns a real `ReductionMorphism[Selection]`; it does not create
a `Template.run` executor. Advanced callers author the same morphism contract.
`MapShape`, rule names, raw JSON key spellings, and `spanify` are absent from
the final beginner surface. Selection paths are decoded semantic keys.

The exact typing surface remains two overloads:

```python
@overload
def reduce(
    self, text: str, reducer: Reducer, *, cores: int = AUTO
) -> IrSelf: ...

@overload
def reduce[Result](
    self,
    text: str,
    reducer: Reducer,
    *,
    into: ReductionMorphism[Result],
    cores: int = AUTO,
) -> Result: ...
```

The overloads are absent at runtime and make no performance claim. The
implementation selects one cached bound product and runs it. Binding verifies
and lowers once per compiled grammar + reducer/signature + immutable target
identity. Repeated-document pools retain that bound product directly; they do
not repeat target verification or expose a second template executor. A single
document pays one cache lookup and one `into is None` choice before entering
the parser, never a target branch in the parser loop.

## Not proved here

These prototypes are deliberately not a miniature second parser. They do not
prove:

- semantic correctness of the flat expression interpreter;
- exact lowering of every operand and failure order in the shipped reducers;
- grammar × upper-schema composition or occurrence-demand propagation;
- PDA/Earley/island integration with the flat product;
- fragment laws for real parallel split shapes;
- absence of hot-loop expansion relative to the current generated-model
  opcodes;
- Qwen wall time, process CPU, allocation count, or RSS.

Those claims require the source phases and external measurement gates already
specified in `TODO.md`. The prototypes establish that implementation can begin
without relaxing the type constraints and identify the expression-program and
plain-integer requirements which must be present before broad source edits.
