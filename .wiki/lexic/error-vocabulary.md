# Error Vocabulary

**When to load:** writing a parser, emitter, or atom dispatch table; choosing which exception class to raise; implementing an engine/reducer error boundary.

See also: [[architecture]]

Source: `exceptions.py`. No bare `raise ValueError` or `raise Exception` for library-level failures.

## Exception classes

| Class | Raised by | Message format |
|---|---|---|
| `UnsupportedConstructError` | The Earley engine (no parse / ambiguous parse), the model routes reached by `CompiledGrammar.parse`, reducer bodies and `CompiledGrammar.reduce`, `canonical_grammar`'s boundary checks, atom dispatch tables, codegen passes, and the instance fold | Rule-first: "rule `foo`: unsupported construct `…`" |
| `FieldValidationError` | IR-intrinsic per-field checked construction in `GrammarModel.__new__` (charclass membership + bounds, `Literal` membership, model/models `isinstance`, required presence); trusted parse paths (`_from_values`/`fast_construct`) bypass it | Field-path-first |

All inherit from `LexicError(Exception)`.

## The refusal readout

A refused **parse** carries more than words. `UnsupportedConstructError.readout` is a `Refusal` (`exceptions.py`) — `pos`, `rule`, `expected`, `negated`, `undecidable` — or `None` on every other use of the class. It is what a caller needs to *draw* a refusal: a caret at the position, the rule that was being matched, the characters that would have continued.

- **Where it comes from.** The predictive route is the one that knows how far it got and what it wanted there, so `PdaFail` carries `pos` / `rule` / `expected` / `negated`, and the product seam (`parsing/products.py`) attaches them when the gated engine *also* declines. The gated engine still owns the verdict — the message is unchanged, so this is additive.
- **What `pos` means.** The offset the failing construct was attempted FROM, not the deepest character matched: a mismatch inside a literal reports the literal's start, and the optimizer merges adjacent exactly-once literals into one run.
- **`undecidable`.** `True` when the predictive route did not fail but BAILED (a `ProbeFork`) — the refusal is about ambiguity, not about a character the grammar cannot derive.
- **`negated`.** The expectation keeps the engine's polarity: a co-finite set is reported as an EXCLUSION rather than enumerated.
- **No readout when nothing was refused.** It is a property of a refusal, not of every parse.

`Refusal` is made of primitives on purpose: `exceptions.py` imports nothing from lexic (everything else imports it), so a `CharSet` cannot live there.

`GrammarAuthoringError` was deleted 2026-07-18 (260718-generated-files Task 0): a dead public stub — every planned raiser went with the retired schema-validation design, and nothing ever raised it.

## Dispatch table contract

Every dispatch table that handles atom types **must** have an explicit default that raises:

```python
HANDLER: dict[type[Atom], Handler] = {
    LiteralAtom: ...,
    RuleRefAtom: ...,
    # ...
}

def dispatch(atom: Atom) -> Result:
    handler = HANDLER.get(type(atom))
    if handler is None:
        raise UnsupportedConstructError(
            f"No handler registered for atom type {type(atom).__name__}"
        )
    return handler(atom)
```

A silent `pass` or `None` return is never acceptable. This is how unexpected atom types are caught early with actionable messages rather than silent wrong output.

## Grammar-parse boundary (`canonical_grammar`, `compile.py`)

**Ambiguity is refused on every route, and a resolver is the only thing that changes that.** A span whose derivations build two different VALUES raises `UnsupportedConstructError`; a *split* does not, because it has a defined answer. Passing `resolve=` hands both derivations to the caller's deterministic resolver instead of raising — so a caller who wants a choice made asks for it explicitly, and the engine never makes one silently. This is not a per-route promise: the char route, the token route and the reduce path all ask the same question.

There is no Lark and no `MetaGrammarParser` anymore — `parse_grammar` compiles the flavour's own self-grammar and calls `CompiledGrammar.reduce`. The engine raises `UnsupportedConstructError` when text does not parse or is ambiguous; `canonical_grammar` adds explicit checks that the flavour carries a `Reducer`, the reduction is an `IrAst`, and the resolved start rule exists.
