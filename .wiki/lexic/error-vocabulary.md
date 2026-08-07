# Error Vocabulary

**When to load:** writing a parser, emitter, or atom dispatch table; choosing which exception class to raise; implementing an engine/reducer error boundary.

See also: [[architecture]]

Source: `exceptions.py`. No bare `raise ValueError` or `raise Exception` for library-level failures.

## Exception classes

| Class | Raised by | Message format |
|---|---|---|
| `UnsupportedConstructError` | The Earley engine (no parse / ambiguous parse — every product entry: `parse`/`parse_reduced`, and the model routes `parse_model`/`token_model` reached by `CompiledGrammar.parse`), reduction bodies (unrecognised construct), `canonical_grammar`'s boundary checks (missing/wrong-shaped `Reducer`, non-`IrAst` reduction result, unknown start rule), atom dispatch tables (unknown atom type), the codegen passes (arm-name collision — `codegen/passes.py`), the instance fold (unknown kind/mode, kid-count mismatch — `parsing/fold.py`) | Rule-first: "rule `foo`: unsupported construct `…`" |
| `FieldValidationError` | IR-intrinsic per-field checked construction in `GrammarModel.__new__` (charclass membership + bounds, `Literal` membership, model/models `isinstance`, required presence); trusted parse paths (`_from_parts`/`fast_construct`) bypass it | Field-path-first |

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

There is no Lark and no `MetaGrammarParser` anymore — `parse_grammar` runs the flavour's own self-grammar through the Earley engine (`parse_reduced`). The engine itself raises `UnsupportedConstructError` when text doesn't parse or parses ambiguously (see `lexic.parsing`'s module docstring). `canonical_grammar` (the public parse+canonicalize+directive front half, superseding the retired `compile_grammar`) adds its own explicit boundary checks, each an `UnsupportedConstructError`: the flavour's `reducer` must be an actual `Reducer` instance, the reduction must produce an `IrAst`, and a resolved `start` rule must actually be defined in the (canonicalized) grammar.

