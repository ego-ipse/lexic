# Transpilation — grammars, and the documents they read

**When to load:** using or extending `transpile()` / the `RULES` table
vocabulary (`Make`, `Spelled`, `Flat`, `Split`, `Is`); converting grammars
between notations; explaining the document-transpilation contract.

See also: [[flavour-system]], [[ir-shapes]], [[public-api]]

Lexic transpiles on two planes: **grammars** convert between notations through
the canonical IR, and **documents** convert between languages on the model
plane, driven by an authored transform that is pure data.

## Grammars

Every notation converges on one canonical `IrAst`, and every flavour is an
emitter *from* that tree — so converting a grammar is a parse and an apply
(`getting_started/ex04_transpile_flavours.py`):

```python
from lexic.compile import parse_grammar
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR

ast = parse_grammar(gbnf_source, GBNF_FLAVOUR)     # GBNF text → IrAst
abnf_text = str(ABNF_FLAVOUR.apply(ast))           # the same grammar, in ABNF
```

Two notations describing the same language converge on the same canonical
tree: `canonicalize(parse(json.gbnf)) == canonicalize(parse(json.abnf))`.
Constructs a notation cannot spell (EBNF has no negation) are refused
explicitly, never approximated.

## Documents

Documents transpile on the model plane (`ex16`, `ex17`): parse under grammar
A, transform A's models into B's models, and B's own `to_text()` is the
pretty-printer —

```
text_A ──A.parse──► A-models ──T──► B-models ──.to_text()──► text_B
```

Only the transform is authored — and it is **pure data**: a table of per-rule
bodies in the two grammars' own vocabulary, no class objects, no functions,
portable through the IR notation like a grammar or a reducer:

```python
from lexic.compile import Make, Spelled, transpile
from lexic.ir import IrMap, IrRuleRef, IrTuple

RULES = IrMap(   # rows keyed by A's RULE NAMES; targets built by name
    IrTuple(IrRuleRef("number"), Make("number", IrTuple(Spelled()))),  # spelling carried whole
    IrTuple(IrRuleRef("member"), Make("fent")),   # bare Make splats transformed children
    # ... Flat()/Split() read and grow hoisted lists; Is()/IrRaise state the domain
)

to_yaml = transpile(json_grammar, yaml_grammar, RULES)   # bake once
yaml_text = to_yaml.run(json_text)                       # run many
```

## The contract, gated on every run

`transpile()` **bakes** the table against the two compiled grammars — rule
names resolve to the synthesized classes, and a `Make` aimed at a hoisted
list rule grows the chain (the inverse of lexic's own hoist passes). The
retained `Transpiler` drives the walk bottom-up (each body receives its
already-transpiled children) and gates the contract on every run:

- **Completeness** — a source class surviving into the product is a hole in
  the table, refused with the class named.
- **Membership and fidelity** — the emitted text parses under B, back to the
  very models the transform built.

A's models are the lossless account of the source (a JSON `Number` keeps its
exact spelling — no float type needed; `true` and `1` are different rules;
duplicate keys survive in order), and B's checked constructors are the type
system — a wrong transpilation refuses with `FieldValidationError` instead of
shipping. What the transform cannot express is a stated domain, refused
through `IrRaise` with words, never silently dropped.

Because rows are rule names over the *canonical* grammar, **one table serves
every formulation of the source language** — the same `RULES` bakes against
`json.gbnf` and `json.abnf` unchanged.

## The examples

`ex16` turns JSON into YAML that way; `ex17` turns a python subset into C++,
with the transform doing the one thing a transpiler genuinely is — here,
inferring declarations, semantic knowledge neither grammar carries:

```python
def scale(x):                #  →   int scale(int x) {
    y = x * 3                #  →       int y = x * 3;
    y = y + 1                #  →       y = y + 1;
    return y                 #  →       return y;
                             #  →   }
```
